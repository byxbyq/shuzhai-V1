# -*- coding: utf-8 -*-
import re
import logging
from fastapi import APIRouter

from backend.services.project_service import state, get_generator
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)


from backend.routers.validate_models import ValidateRequest
from backend.services.validate_prompts import _build_memory_section
from backend.routers.validate_batch import _parse_issue_text

# ═══════════════════════════════════════════
# 19维合并检查 — 一次AI调用检查所有维度
# ═══════════════════════════════════════════

router = APIRouter()


@router.post("/all")
def validate_all(data: ValidateRequest):
    """合并检查：一次AI调用完成所有维度的检查，大幅节省token"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "no project")
    stage = (data.context or {}).get("stage", "content")
    content = data.content
    memory = data.memory or ""
    ctx = data.context or {}
    if memory:
        ctx["memory"] = memory

    # 构建合并prompt
    chapter_index = ctx.get("chapterIndex", 0)
    mem_section = _build_memory_section(ctx)

    # 后端安全网：如果前端未传章节大纲，从后端项目数据中获取
    chapter_outline = ctx.get("chapterOutline", "")
    if not chapter_outline.strip() and stage != "chapter-outline":
        ch_outlines = []
        for ch in state.project.chapters:
            ol = ch.get("outline", "") if isinstance(ch, dict) else ""
            if ol and isinstance(ol, str) and ol.strip():
                ch_title = ch.get("title", "") if isinstance(ch, dict) else ""
                ch_outlines.append(f"【{ch_title}】\n{ol}")
        if ch_outlines:
            chapter_outline = "\n\n".join(ch_outlines)
    ctx["chapterOutline"] = chapter_outline

    # 根据stage构建不同检查项
    if stage == "chapter-outline":
        checks_block = f"""### 检查项（请逐项检查，每项用XML标签输出结果）

1. <drift>偏差检查：严格审查章节大纲，找出逻辑漏洞、剧情矛盾和遗漏。同时检查是否包含违反设定的禁忌词汇（灵力、经脉、丹田、筑基、金丹、元婴、灵根、法力、神识、灵气——这些是诸天伪界修仙体系，白墨绝不使用）。如发现禁忌词汇或设定偏离，列出具体问题。无问题返回"无偏离"</drift>

2. <twist>转折检查：分析章节大纲的转折设计是否合理自然。给出评价</twist>

3. <duplicate>重复检查：检查章节大纲是否有重复内容（章节内部不同场景之间相同描写、与前几章已写过的具体情节完全重复）。无重复返回"无重复"</duplicate>

4. <timeline>时间线检查：检查章节大纲内部的时间线是否连贯合理。无问题返回"无矛盾"</timeline>

5. <conflict>冲突检查：检查章节大纲是否存在设定冲突（角色身份/位置/能力/关系矛盾）。无冲突返回"无冲突"</conflict>

6. <style>风格检查：评价章节大纲的文笔风格一致性。指出不一致之处</style>"""
        context_block = f"""【第{chapter_index + 1}章大纲】
{content}"""
    else:
        # 正文阶段：正文↔章节大纲两方比对
        chapter_outline = ctx.get("chapterOutline", "")
        # 获取前一章内容（连贯性检查需要）
        prev_content = ""
        if chapter_index > 0 and chapter_index <= len(state.project.chapters):
            try:
                prev_content = state.project.get_content(chapter_index - 1) or ""
            except Exception:
                pass
        # 获取世界观和人物设定（一致性检查需要）
        world_settings = getattr(state.project, "world_settings", {}) or {}
        world_text = ""
        if isinstance(world_settings, dict):
            for k, v in world_settings.items():
                if v and str(v).strip():
                    world_text += f"  {k}: {v}\n"
        elif isinstance(world_settings, list):
            for item in world_settings:
                if isinstance(item, dict):
                    world_text += f"  {item.get('name','')}: {item.get('value','')}\n"
                elif item:
                    world_text += f"  - {item}\n"
        characters_data = getattr(state.project, "characters", []) or []
        char_text = ""
        if isinstance(characters_data, list):
            for ch in characters_data:
                if isinstance(ch, dict):
                    char_text += f"  {ch.get('name','')}: 身份={ch.get('identity',ch.get('role',''))}, 能力={ch.get('ability','')}\n"
        checks_block = f"""### 检查项（请逐项检查，每项用XML标签输出结果）

1. <drift>偏差检查（正文↔章节大纲比对）：1)正文→章节大纲：正文是否完整覆盖章节大纲所有要点？是否有遗漏？2)正文→章节大纲：正文是否有不在章节大纲中的自行发挥？无问题返回"无偏离"</drift>

2. <twist>转折检查：分析正文的转折设计是否合理自然，评价转折的合理性和冲击力</twist>

3. <duplicate>重复检查：检查正文是否有重复内容。无重复返回"无重复"</duplicate>

4. <timeline>时间线检查（正文↔章节大纲比对）：正文时间线是否与章节大纲一致？无问题返回"无矛盾"</timeline>

5. <conflict>冲突检查（正文↔章节大纲比对）：正文中的角色状态/能力/关系是否与章节大纲矛盾？无冲突返回"无冲突"</conflict>

6. <style>风格检查：评价正文的文笔风格一致性，指出风格不一致的地方</style>

7. <wordcount>字数治理检查：正文实际字数为{len(content)}字。对比章节大纲中的字数目标，评估是否达标。低于目标80%标记为"欠字"，超过目标120%标记为"超字"。给出字数调整建议</wordcount>

8. <completeness>完整性检查：本章正文是否具备完整章节应有的结构要素？包括：开头是否有引入、是否有明确的场景转换、结尾是否有收束或悬念、是否缺少必要的人物互动或冲突描写。列出缺失的要素，无缺失返回"完整"</completeness>

9. <continuity>连贯性检查：本章正文与前一章的衔接是否自然？角色位置/状态是否延续、时间线是否连贯、有无断裂感。{'有前一章内容作为参考' if prev_content else '（本章是第一章，无需连贯性检查）'}。**联动三定律**：如有前文参考，检测正文中出现在前文已建立设定之外的发明（新角色/新物品/新能力），标记为[疑似幻觉发明]。无问题返回"衔接自然"</continuity>

10. <consistency>一致性检查：{'注意：当前未提供角色档案和世界观设定，请直接返回"无数据跳过"。' if not char_text.strip() and not world_text.strip() else '正文中的角色设定（身份/能力/关系）是否与人物档案一致？世界观描述（地点/规则/体系）是否与世界观设定一致？**联动三定律**：检测是否违反设定物理性（如角色能力超出档案范围、地点不存在于世界观中）。列出矛盾之处。无问题返回"设定一致"'}</consistency>"""
        context_block = f"""【第{chapter_index + 1}章大纲】
{chapter_outline if chapter_outline else '（未提供）'}

【世界观设定】
{world_text if world_text.strip() else '（未提供）'}

【人物档案】
{char_text if char_text.strip() else '（未提供）'}

{f"【前一章正文】" + chr(10) + prev_content if prev_content else ""}

【正文内容（共{len(content)}字）】
{content[:12000]}"""

    # 根据stage确定期望的tags（与prompt中的检查项一致）
    expected_tags = ['drift', 'twist', 'duplicate', 'timeline', 'conflict', 'style']
    if stage != "chapter-outline":
        expected_tags.extend(['wordcount', 'completeness', 'continuity', 'consistency'])

    prompt = f"""你是小说审核专家。请对以下内容进行{len(expected_tags)}项检查，一次性返回所有结果。

{context_block}
{mem_section}

{checks_block}

重要要求：
1. 每项检查结果必须包裹在对应的XML标签内
2. 如果某项检查无问题，在标签内返回对应的"无xxx"
3. 不要在标签外输出多余内容
4. 【关键】标签内的文本不得包含任何XML标签样式的字符串（如"<drift>"），会导致解析错误。如需引用标签名请用【drift】替代
5. 保持每项检查的独立性和专业性
6. 【输出格式】每项检查结果必须按以下结构化格式输出（方便自动解析）：
   - 第一行：结论（"无xxx" 或 "发现问题"）
   - 如发现问题，第二行起每行一个具体问题，格式为：
     【问题】简述问题（一句话，不超过50字）
     【位置】必须标注段落编号（按空行分段，如"第3段"、"第2-4段"、"第1段-第3段"），可附带场景描述（如"第3段 课堂场景"）
     【建议】修改建议（一句话，不超过50字）
   - 示例：
     <drift>发现问题
     【问题】正文遗漏大纲中"苏晚给纸条"的关键情节
     【位置】第5段 课堂场景结束后
     【建议】在下课和天台之间补一段苏晚递纸条的过渡场景</drift>
6. 无问题的检查项也必须按格式输出，例如：
   <timeline>无矛盾</timeline>
7. 【防幻觉三定律】偏差检查必须额外执行以下三定律检测：
   - 定律一「大纲即法律」：正文/章节大纲必须严格覆盖大纲要点，不得遗漏、不得自行发挥不在大纲中的情节。发现自行发挥的情节必须列出。
   - 定律二「设定即物理」：正文不得违反已建立的世界观设定和人物设定（能力、身份、关系、位置）。发现违反物理性的设定必须列出。
   - 定律三「发明需识别」：正文中出现的、不在大纲和设定中的新角色/新物品/新能力/新地点，必须标记为[疑似幻觉发明]，由人工裁定是否保留。
   三定律的检测结果写入<drift>标签内，格式为「三定律检测：[列出违反项，无违反返回"三定律通过"]」"""

    try:
        gen = get_generator()
        raw_result = gen.ai.generate(prompt)
        # 解析XML标签
        results = {}
        tags = expected_tags
        for tag in tags:
            match = re.search(f'<{tag}>([\\s\\S]*?)</{tag}>', raw_result)
            if match:
                results[tag] = match.group(1).strip()
            else:
                results[tag] = None  # 标记为缺失，前端需要补查

        parsed_count = sum(1 for v in results.values() if v is not None)
        truncated = (len(tags) - parsed_count) >= 2  # 缺失≥2个标签视为截断
        # 对每个检查项结果进行结构化解析
        structured_results = {}
        for tag in tags:
            text = results.get(tag)
            structured = _parse_issue_text(text) if text else {"issues": [], "parse_failed": False}
            structured_results[tag] = {
                "text": text,
                "structured": structured
            }
        return {
            "ok": True,
            "results": structured_results,
            "parsed_count": parsed_count,
            "total": len(tags),
            "truncated": truncated,
            "raw": raw_result if parsed_count < 4 else None,  # 解析失败严重时返回原文供调试
            "stage": stage
        }
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")

