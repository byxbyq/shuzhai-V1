# -*- coding: utf-8 -*-
import json
import re
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List

from backend.services.project_service import state, get_generator
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)


from backend.routers.validate_models import AllInOneRequest
from backend.services.validate_prompts import (
    _build_drift_prompt, _build_twist_prompt, _build_duplicate_prompt,
    _build_style_prompt, _build_timeline_prompt, _build_conflict_prompt,
    _build_quality_prompt, _build_memory_prompt,
)

# ═══════════════════════════════════════════
# 批量检查端点（耗时操作）
# ═══════════════════════════════════════════

router = APIRouter()


class BatchValidateRequest(BaseModel):
    check_types: List[str] = ["drift", "duplicate", "conflict", "style", "timeline", "twist"]
    chapter_indices: Optional[List[int]] = None


def _result_indicates_issue(result: str, check_type: str) -> bool:
    """根据检查结果文本判断是否存在问题"""
    if not result:
        return False
    # AI 调用失败视为无问题（避免误报）
    if result.startswith("[错误]") or "生成失败" in result:
        return False
    no_issue_markers = {
        "drift": ["无偏离"],
        "duplicate": ["无重复"],
        "timeline": ["无矛盾"],
        "conflict": ["无冲突"],
    }
    markers = no_issue_markers.get(check_type)
    if markers:
        return not any(m in result for m in markers)
    # twist / style / quality / memory 也扫描负面关键词
    negative_keywords = ["生硬", "突兀", "不合理", "不自然", "不协调", "不一致", "有问题", "需改进", "质量差", "偏离", "矛盾", "冲突"]
    return any(kw in result for kw in negative_keywords)


def _parse_issue_text(text: str) -> dict:
    """
    从 AI 返回的纯文本检查结果中结构化提取问题列表。
    返回: {"issues": [...], "parse_failed": bool}
    每个 issue 包含: {type, location, suggestion, severity, description}
    """
    if not text or not text.strip():
        return {"issues": [], "parse_failed": False}

    # 清理：去掉首尾空白，去除第一行的"发现问题"/"无xxx"等结论行
    lines = text.strip().split('\n')
    # 跳过纯结论行（如"发现问题"、"无偏离"、"无重复"等）
    first_line = lines[0].strip() if lines else ""
    conclusion_markers = ["发现问题", "无偏离", "无重复", "无矛盾", "无冲突", "完整", "衔接自然",
                          "设定一致", "欠字", "超字", "达标", "三定律检测", "✓", "⚠",
                          "无数据跳过", "无一致性问题", "无连贯性问题",
                          "无风格问题", "无字数问题", "无完整性问题", "通过", "OK",
                          "合格", "正常", "无异常", "一切正常"]
    start_idx = 0
    if any(first_line.startswith(m) or first_line == m for m in conclusion_markers):
        start_idx = 1

    body_lines = lines[start_idx:]
    body = '\n'.join(body_lines).strip()

    if not body:
        return {"issues": [], "parse_failed": False}

    issues = []

    # ── 策略 a：【问题】/【位置】/【建议】标记格式 ──
    if '【问题】' in body:
        # 按【问题】分割成多个问题块
        chunks = body.split('【问题】')
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            issue = {"type": "", "location": "", "suggestion": "", "severity": "medium", "description": ""}
            # 提取问题描述（到下一个【位置】之前）
            if '【位置】' in chunk:
                parts = chunk.split('【位置】', 1)
                issue["description"] = parts[0].strip()
                rest = parts[1]
                if '【建议】' in rest:
                    loc_parts = rest.split('【建议】', 1)
                    issue["location"] = loc_parts[0].strip()
                    issue["suggestion"] = loc_parts[1].strip()
                else:
                    issue["location"] = rest.strip()
            elif '【建议】' in chunk:
                parts = chunk.split('【建议】', 1)
                issue["description"] = parts[0].strip()
                issue["suggestion"] = parts[1].strip()
            else:
                issue["description"] = chunk.strip()
            # 尝试从描述中推断严重程度
            if any(w in issue["description"] for w in ["严重", "重大", "致命"]):
                issue["severity"] = "high"
            elif any(w in issue["description"] for w in ["轻微", "建议", "可优化"]):
                issue["severity"] = "low"
            issue["type"] = issue["description"][:30] if issue["description"] else ""
            issues.append(issue)
        if issues:
            return {"issues": issues, "parse_failed": False}

    # ── 策略 b：- 问题：/ - 位置：等列表项格式 ──
    list_patterns = [
        ('问题', 'description'),
        ('位置', 'location'),
        ('建议', 'suggestion'),
        ('严重程度', 'severity'),
    ]
    # 检查是否有列表项标记
    has_list_items = any(f"- {label}" in body or f"-{label}" in body or f"• {label}" in body
                         for label, _ in list_patterns)
    if has_list_items:
        current_issue = {"type": "", "location": "", "suggestion": "", "severity": "medium", "description": ""}
        lines_list = body.split('\n')
        current_field = None
        for line in lines_list:
            line_stripped = line.strip()
            matched = False
            for label, field in list_patterns:
                # 匹配 "- 问题：xxx" / "-问题：xxx" / "• 问题：xxx" 等格式
                m = re.match(r'^[\-•\*]\s*' + label + r'\s*[：:]\s*(.*)', line_stripped)
                if m:
                    val = m.group(1).strip()
                    if field == 'description' and current_issue["description"]:
                        # 新的问题，先保存上一个
                        if current_issue["description"]:
                            current_issue["type"] = current_issue["description"][:30]
                            issues.append(current_issue)
                        current_issue = {"type": "", "location": "", "suggestion": "", "severity": "medium", "description": ""}
                    current_issue[field] = val
                    current_field = field
                    matched = True
                    break
            if not matched and current_field and line_stripped and not line_stripped.startswith('-'):
                # 续行
                current_issue[current_field] += '\n' + line_stripped
        # 保存最后一个
        if current_issue["description"]:
            current_issue["type"] = current_issue["description"][:30]
            issues.append(current_issue)
        if issues:
            return {"issues": issues, "parse_failed": False}

    # ── 策略 c：按空行分段，每段作为一个 issue ──
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', body) if p.strip()]
    if len(paragraphs) >= 1 and body.strip():
        for para in paragraphs:
            if not para.strip():
                continue
            # 跳过明显的标题行
            if para.startswith('###') or para.startswith('##'):
                continue
            issue = {
                "type": para[:30],
                "location": "",
                "suggestion": "",
                "severity": "medium",
                "description": para
            }
            # 尝试从段落中提取位置信息
            loc_match = re.search(r'(?:位置|地点|场景|段落)[：:]\s*([^\n。]+)', para)
            if loc_match:
                issue["location"] = loc_match.group(1).strip()
            issues.append(issue)
        if issues:
            return {"issues": issues, "parse_failed": False}

    # ── 策略 d：都失败，返回原始文本 ──
    return {"issues": [], "parse_failed": True, "raw": text}


@router.post("/all-in-one")
def validate_all_in_one(data: AllInOneRequest):
    """19维合并检查：一次AI调用完成10维问题检查 + 6维责编评分 + 3维市场评分

    优势：
    1. 节省token：只需一次AI调用
    2. 避免冲突：AI全局考虑，不会给出矛盾的修改建议
    3. 效率更高：适合每章生成后自动触发
    """
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "no project")

    content = data.content
    memory = data.memory or ""
    ctx = data.context or {}
    if memory:
        ctx["memory"] = memory

    chapter_index = ctx.get("chapterIndex", 0)
    if data.index >= 0:
        chapter_index = data.index

    # 获取项目数据
    gen = get_generator()
    if not gen:
        return err(ErrorCode.INTERNAL_ERROR, "generator未初始化")

    # 获取章节大纲
    chapter_outline = ctx.get("chapterOutline", "")
    if not chapter_outline.strip():
        ch_outlines = []
        for ch in state.project.chapters:
            ol = ch.get("outline", "") if isinstance(ch, dict) else ""
            if ol and isinstance(ol, str) and ol.strip():
                ch_title = ch.get("title", "") if isinstance(ch, dict) else ""
                ch_outlines.append(f"【{ch_title}】\n{ol}")
        if ch_outlines:
            chapter_outline = "\n\n".join(ch_outlines)

    # 获取世界观
    world_settings = getattr(state.project, "world_settings", {}) or {}
    world_text = ""
    if isinstance(world_settings, dict):
        wlines = []
        for k, v in world_settings.items():
            if isinstance(v, dict):
                wlines.append(f"- {k}：{v.get('description', v.get('val', str(v)))}")
            else:
                wlines.append(f"- {k}：{v}")
        world_text = "\n".join(wlines)
    elif isinstance(world_settings, str):
        world_text = world_settings

    # 获取人物
    characters = getattr(state.project, "characters", []) or []
    char_lines = []
    for ch in characters:
        if isinstance(ch, dict):
            name = ch.get("name", "")
            identity = ch.get("identity", ch.get("role", ""))
            ability = ch.get("ability", "")
            char_lines.append(f"- {name}：身份={identity}，能力={ability}")
    char_text = "\n".join(char_lines)

    # 获取前一章内容（从磁盘读取，避免内存 chapters 数组 content 为空）
    prev_content = ""
    if chapter_index > 0 and chapter_index < len(state.project.chapters):
        try:
            prev_content = state.project.get_content(chapter_index - 1) or ""
        except Exception:
            pass

    # 构建记忆部分
    mem_section = ""
    if memory:
        mem_section = f"\n\n【全文记忆参考】\n{memory}\n"

    # 构建19维检查prompt
    prompt = f"""你是小说审核专家。请对以下正文进行完整的19维质量检查，一次性返回所有结果。

【第{chapter_index + 1}章大纲】
{chapter_outline if chapter_outline else '（未提供）'}

【世界观设定】
{world_text if world_text.strip() else '（未提供）'}

【人物档案】
{char_text if char_text.strip() else '（未提供）'}

{f"【前一章正文】" + chr(10) + prev_content if prev_content else ""}

【正文内容（共{len(content)}字）】
{content[:12000]}
{mem_section}

═══════════════════════════════════════
第一部分：10维问题检查
═══════════════════════════════════════
请逐项检查，每项用XML标签输出结果：

1. <drift>偏差检查（正文↔章节大纲比对）：正文是否完整覆盖章节大纲所有要点？是否有自行发挥？无问题返回"无偏离"</drift>

2. <twist>转折检查：分析正文的转折设计是否合理自然</twist>

3. <duplicate>重复检查：检查正文是否有重复内容。无重复返回"无重复"</duplicate>

4. <timeline>时间线检查：正文时间线是否与章节大纲一致？无问题返回"无矛盾"</timeline>

5. <conflict>冲突检查：正文中的角色状态/能力/关系是否与章节大纲矛盾？无冲突返回"无冲突"</conflict>

6. <style>风格检查：评价正文的文笔风格一致性</style>

7. <wordcount>字数治理：正文实际字数为{len(content)}字。对比章节大纲中的字数目标，评估是否达标</wordcount>

8. <completeness>完整性检查：本章是否具备完整章节应有的结构要素？无缺失返回"完整"</completeness>

9. <continuity>连贯性检查：本章与前一章的衔接是否自然？{'有前一章内容作为参考' if prev_content else '（本章是第一章）'}。无问题返回"衔接自然"</continuity>

10. <consistency>一致性检查：正文中的角色设定/世界观是否与人物档案/世界观设定一致？无问题返回"设定一致"</consistency>

═══════════════════════════════════════
第二部分：6维责编评分
═══════════════════════════════════════
请对以下6个维度进行1-5分评分：

11. <editorial_scores>包含JSON格式的评分：
{{
  "dimensions": [
    {{"name": "人物塑造力", "score": 1-5, "description": "一句话理由"}},
    {{"name": "情感穿透力", "score": 1-5, "description": "一句话理由"}},
    {{"name": "情节反转密度", "score": 1-5, "description": "一句话理由"}},
    {{"name": "主题深度", "score": 1-5, "description": "一句话理由"}},
    {{"name": "文体魅力", "score": 1-5, "description": "一句话理由"}},
    {{"name": "爽点密度", "score": 1-5, "description": "一句话理由"}}
  ]
}}
</editorial_scores>

═══════════════════════════════════════
第三部分：3维市场评分
═══════════════════════════════════════
请对以下3个维度进行1-5分评分：

12. <market_scores>包含JSON格式的评分：
{{
  "dimensions": [
    {{"name": "追读意愿", "score": 1-5, "description": "一句话理由"}},
    {{"name": "类型适配度", "score": 1-5, "description": "一句话理由"}},
    {{"name": "传播潜力", "score": 1-5, "description": "一句话理由"}}
  ]
}}
</market_scores>

═══════════════════════════════════════
重要要求：
1. 所有结果必须按上述XML标签格式输出
2. 评分部分必须是有效的JSON格式
3. 如果某项检查无问题，返回对应的"无xxx"
4. 问题描述要具体，便于后续定位和修复
"""

    try:
        raw = gen.ai.generate(prompt)

        # 解析结果
        result = {
            "ok": True,
            "checks": {},  # 10维问题检查结果
            "editorial": None,  # 6维责编评分
            "market": None,  # 3维市场评分
            "raw": raw
        }

        # 解析10维检查
        check_tags = ['drift', 'twist', 'duplicate', 'timeline', 'conflict',
                      'style', 'wordcount', 'completeness', 'continuity', 'consistency']
        for tag in check_tags:
            pattern = f'<{tag}>(.*?)</{tag}>'
            match = re.search(pattern, raw, re.DOTALL)
            if match:
                content_text = match.group(1).strip()
                result["checks"][tag] = {
                    "content": content_text,
                    "ok": content_text.startswith("无") or "无问题" in content_text
                }

        # 解析责编评分
        editorial_match = re.search(r'<editorial_scores>(.*?)</editorial_scores>', raw, re.DOTALL)
        if editorial_match:
            try:
                editorial_json = editorial_match.group(1).strip()
                result["editorial"] = json.loads(editorial_json)
            except Exception:
                # 尝试提取JSON
                m = re.search(r'\{[\s\S]*\}', editorial_match.group(1))
                if m:
                    try:
                        result["editorial"] = json.loads(m.group(0))
                    except Exception as e:
                        logger.debug("责编评分JSON解析失败: %s", e)

        # 解析市场评分
        market_match = re.search(r'<market_scores>(.*?)</market_scores>', raw, re.DOTALL)
        if market_match:
            try:
                market_json = market_match.group(1).strip()
                result["market"] = json.loads(market_json)
            except Exception:
                m = re.search(r'\{[\s\S]*\}', market_match.group(1))
                if m:
                    try:
                        result["market"] = json.loads(m.group(0))
                    except Exception as e:
                        logger.debug("市场评分JSON解析失败: %s", e)
                    except:
                        pass

        return result

    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"19维检查失败: {str(e)}")


@router.post("/batch")
def validate_batch(data: BatchValidateRequest):
    """批量检查多个章节的多项维度，逐章逐项调用现有检查逻辑"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "no project")

    # 确定待检查章节：未指定或空列表则遍历所有有内容的章节
    if not data.chapter_indices:
        indices = []
        for i in range(len(state.project.chapters)):
            try:
                content = state.project.get_content(i)
            except Exception:
                content = ""
            if content and len(content.strip()) > 100:
                indices.append(i)
    else:
        indices = [i for i in data.chapter_indices if 0 <= i < len(state.project.chapters)]

    # 复用现有的 prompt 构建函数
    builders = {
        "drift": _build_drift_prompt,
        "twist": _build_twist_prompt,
        "duplicate": _build_duplicate_prompt,
        "style": _build_style_prompt,
        "timeline": _build_timeline_prompt,
        "conflict": _build_conflict_prompt,
        "quality": _build_quality_prompt,
        "memory": _build_memory_prompt,
    }

    # 检查是否包含 all-in-one（19维合并检查）
    has_all_in_one = 'all-in-one' in data.check_types

    # 准备章节大纲上下文
    chapter_outline = ""

    gen = get_generator()
    results = []
    issues_found = 0

    for idx in indices:
        try:
            content = state.project.get_content(idx)
        except Exception:
            content = ""
        if not content or not content.strip():
            continue  # 内容为空则跳过
        title = state.project.chapters[idx].get("title", "") if 0 <= idx < len(state.project.chapters) else ""
        # 从项目数据中提取该章的章节大纲
        ch_outline = ""
        if 0 <= idx < len(state.project.chapters):
            ch_outline = state.project.chapters[idx].get("outline", "")
            if not ch_outline:
                ch_outline = ""
        ctx = {
            "stage": "content",
            "chapterIndex": idx,
            "chapterOutline": ch_outline,
        }
        checks_result = {}

        # 处理 all-in-one（19维合并检查）
        if has_all_in_one:
            try:
                # 构建请求
                req = AllInOneRequest(
                    content=content,
                    context=ctx,
                    index=idx,
                    memory=""
                )
                # 调用 all-in-one 端点
                result = validate_all_in_one(req)
                if result.get('ok'):
                    # 将19维结果拆分存入 checks_result
                    checks_result['all-in-one'] = {
                        'ok': True,
                        'checks': result.get('checks', {}),
                        'editorial': result.get('editorial'),
                        'market': result.get('market'),
                        'result': '19维合并检查完成'
                    }
                else:
                    checks_result['all-in-one'] = result
            except Exception as e:
                checks_result['all-in-one'] = err(ErrorCode.INTERNAL_ERROR, f"19维检查失败: {str(e)}")

        # AIζ
        ai_flavor_types = [ct for ct in data.check_types if ct == 'ai-flavor']
        ai_prompt_types = [ct for ct in data.check_types if ct != 'ai-flavor' and ct in builders]

        # 1. AIζ
        for ct in ai_flavor_types:
            try:
                from backend.services.audit import detect_ai_flavor
                result = detect_ai_flavor(content)
                has_issue = result.get('score', 0) > 0
                if has_issue:
                    issues_found += 1
                checks_result[ct] = {
                    "ok": not has_issue,
                    "result": result.get('summary', ''),
                    "score": result.get('score', 0),
                    "level": result.get('level', ''),
                    "issues": result.get('issues', [])
                }
            except Exception as e:
                checks_result[ct] = err(ErrorCode.INTERNAL_ERROR, f"Уʧ: {str(e)}")

        # 2. ϲһpromptAI
        if ai_prompt_types:
            try:
                # ȡpromptϲ
                prompts = []
                for ct in ai_prompt_types:
                    builder = builders[ct]
                    prompt = builder(content, ctx)
                    prompts.append(f"### {ct.upper()}\n{prompt}")

                # ϲΪһprompt
                combined_prompt = (
                    "һλרС˵༭Ա¡"
                    "¶άȽ棬ÿظʽ\n\n"
                    + "\n\n".join(prompts) +
                    "\n\n JSONʽ£\n"
                    "{"
                )

                # ÿJSONֶ
                json_fields = []
                for ct in ai_prompt_types:
                    json_fields.append(f'"{ct}": {{"ok": true, "result": "", "paragraphs": []}}')
                combined_prompt += ", ".join(json_fields) + "}"

                result_text = gen.ai.generate(combined_prompt)

                # нΪ
                import json as _json
                import re as _re
                parsed = None
                for pattern in [r"```json\s*\n(.*?)\n```", r"```json\s*\n([\s\S]+)", r"\{[\s\S]*\}"]:
                    m = _re.search(pattern, result_text, _re.DOTALL)
                    if m:
                        try:
                            parsed = _json.loads(m.group(1) if pattern != r"\{[\s\S]*\}" else m.group(0))
                            break
                        except Exception as e:
                            logger.debug("AI提示词结果JSON解析失败: %s", e)
                            continue

                if parsed is None:
                    try:
                        parsed = _json.loads(result_text)
                    except Exception as e:
                        logger.debug("AI提示词结果整体解析失败: %s", e)
                        parsed = None

                #
                if parsed:
                    for ct in ai_prompt_types:
                        item = parsed.get(ct, {})
                        if isinstance(item, dict):
                            ok = item.get("ok", True)
                            result = item.get("result", "")
                            paragraphs = item.get("paragraphs", [])
                        else:
                            ok = not _result_indicates_issue(str(item), ct)
                            result = str(item)
                            paragraphs = []

                        has_issue = not ok
                        if has_issue:
                            issues_found += 1
                        checks_result[ct] = {
                            "ok": ok,
                            "result": result,
                            "paragraphs": paragraphs
                        }
                else:
                    # ʧܣнΪ
                    for ct in ai_prompt_types:
                        checks_result[ct] = {"ok": True, "result": result_text[:500]}
            except Exception as e:
                for ct in ai_prompt_types:
                    checks_result[ct] = err(ErrorCode.INTERNAL_ERROR, f"Уʧ: {str(e)}")
        results.append({
            "chapter_index": idx,
            "title": title,
            "checks": checks_result,
        })

    return {
        "ok": True,
        "results": results,
        "summary": {
            "total": len(results),
            "issues_found": issues_found,
        },
    }

