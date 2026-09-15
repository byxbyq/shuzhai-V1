# -*- coding: utf-8 -*-
import re
import logging
from fastapi import APIRouter

from backend.services.project_service import state, get_generator
from backend.api_models import err, ErrorCode
import asyncio

logger = logging.getLogger(__name__)


from backend.routers.validate_models import ConsistencyRequest

# ═══════════════════════════════════════════
# 统一全局一致性检查
# ═══════════════════════════════════════════

router = APIRouter()

@router.post("/consistency")
async def validate_consistency(data: ConsistencyRequest):
    """统一全局一致性检查：检查世界观、人物、章节大纲、正文之间的对齐"""
    return await asyncio.to_thread(_do_validate_consistency, data)

def _do_validate_consistency(data: ConsistencyRequest):
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "no project")

    # ── 收集四层数据 ──
    world_settings = getattr(state.project, "world_settings", {}) or {}
    character_settings = getattr(state.project, "character_settings", {}) or {}
    characters = getattr(state.project, "characters", []) or []
    chapters = getattr(state.project, "chapters", []) or []

    # 正文（可选，有就阶段2，没有就阶段1）
    content = data.content
    chapter_index = data.index

    # ── 世界观转文本 ──
    world_text = ""
    if isinstance(world_settings, dict):
        lines = []
        for k, v in world_settings.items():
            if isinstance(v, dict):
                lines.append(f"- {k}：{v.get('description', v.get('val', str(v)))}")
            else:
                lines.append(f"- {k}：{v}")
        world_text = "\n".join(lines)
    elif isinstance(world_settings, str):
        world_text = world_settings

    # ── 人物档案转文本 ──
    char_lines = []
    if isinstance(character_settings, dict):
        for name, info in character_settings.items():
            if isinstance(info, dict):
                desc = info.get("description", "")
                char_lines.append(f"- {name}：{desc}")
            else:
                char_lines.append(f"- {name}：{info}")
    if characters:
        for ch in characters:
            if isinstance(ch, dict):
                name = ch.get("name", "")
                identity = ch.get("identity", "")
                faction = ch.get("faction", "")
                char_lines.append(f"- {name}（{faction}）：{identity}")
    char_text = "\n".join(char_lines) if char_lines else ""

    # ── 章节大纲转文本（只收集已有的，不报缺失）──
    chapter_outlines_list = []
    for i, ch in enumerate(chapters):
        if isinstance(ch, dict):
            outline = ch.get("outline", "")
            title = ch.get("title", f"第{i+1}章")
            if outline and outline.strip():
                chapter_outlines_list.append(f"【{title}】\n{outline}")
    chapter_outlines_text = "\n\n".join(chapter_outlines_list)
    chapter_outlines_count = len(chapter_outlines_list)

    # ── 当前章节大纲 ──
    current_chapter_outline = ""
    if 0 <= chapter_index < len(chapters):
        current_chapter_outline = chapters[chapter_index].get("outline", "") if isinstance(chapters[chapter_index], dict) else ""

    # ── 判断检查阶段 ──
    has_content = bool(content and content.strip())
    has_chapter_outlines = chapter_outlines_count > 0
    has_multiple_chapter_outlines = chapter_outlines_count >= 2

    # ── 构建检查项（动态，根据数据多少）──
    check_items = []

    # 阶段1：设定层（始终检查，只要有数据）
    if char_text.strip():
        check_items.append(("characters_world", "角色↔世界观一致性", "人物档案中的角色设定（身份/能力/关系）是否与世界观设定中的规则/体系一致？例如角色的能力是否在世界观体系内？列出不一致之处。无问题返回\"角色与世界观数据一致\""))
    if world_text.strip():
        check_items.append(("world_outline", "世界观↔章节大纲一致性", "世界观设定中的核心设定（时间/地点/规则/体系）与章节大纲中的世界观描述是否一致？列出矛盾之处。无问题返回\"世界观与章节大纲一致\""))

    # 章节大纲之间的衔接（只有2个及以上才检查）
    if has_multiple_chapter_outlines:
        check_items.append(("chapter_chapter", "章节大纲之间衔接", "已有的章节大纲之间是否有矛盾或断裂？前后章节的剧情是否衔接？注意：只检查已有的章节大纲之间，不因缺失未生成的章节而报错。无问题返回\"章节大纲衔接正常\""))

    # 阶段2：正文相关（有正文才检查）
    if has_content:
        if current_chapter_outline.strip():
            check_items.append(("content_chapter_outline", "正文↔章节大纲对齐", "正文↔章节大纲比对（**只报告重大偏离**）：\n1.关键情节遗漏：章节大纲中的**核心情节**（主要冲突、关键转折、重要场景），正文是否完全遗漏？（措辞调整、细节略写不算遗漏）\n2.重大剧情偏离：正文是否包含了与章节大纲**明显矛盾**的自行发挥情节？（合理的细节补充、对话润色不算偏离）\n3.角色状态矛盾：正文中的角色状态是否与章节大纲**严重不一致**？\n**以下不算问题**：措辞调整、对话润色、描写细化、合理的细节补充、略写过渡细节\n无问题返回\"正文与章节大纲对齐\""))
        if char_text.strip():
            check_items.append(("content_characters", "正文↔人物档案对齐", "正文中的角色行为/性格/能力是否与人物档案一致？角色是否做出了与档案矛盾的行为？列出不一致之处。无问题返回\"正文与人物档案一致\""))
        if world_text.strip():
            check_items.append(("content_world", "正文↔世界观对齐", "正文中的设定（地点/规则/能力体系）是否与世界观设定一致？是否有违反世界观规则的描写？列出不一致之处。无问题返回\"正文与世界观数据一致\""))

    if not check_items:
        return err(ErrorCode.INTERNAL_ERROR, "数据不足，无法检查一致性（至少需要章节大纲+一项其他设定）")

    # ── 构建prompt ──
    stage_label = "阶段2：全文一致性检查" if has_content else "阶段1：设定层一致性检查"
    prompt = f"""你是小说设定一致性审核专家。请进行{stage_label}。

【世界观设定】
{world_text if world_text.strip() else '（无世界观设定）'}

【人物档案】
{char_text if char_text.strip() else '（无人物档案）'}

【已有章节大纲（共{chapter_outlines_count}章）】
{chapter_outlines_text[:3000] if has_chapter_outlines else '（暂无章节大纲）'}
"""

    if has_content:
        prompt += f"""
【当前章节正文（第{chapter_index+1}章，共{len(content)}字）】
{content[:12000]}
"""

    prompt += f"""
### 检查项（共{len(check_items)}项，逐项检查，用XML标签输出）

"""
    for i, (tag, title, desc) in enumerate(check_items, 1):
        prompt += f"{i}. <{tag}>{title}：{desc}。</{tag}>\n\n"

    prompt += """
重要要求：
1. 每项检查结果必须包裹在对应的XML标签内
2. 如无问题返回对应的"xxx一致"或"无xxx"
3. 发现问题时列出具体不一致内容，不要笼统说"有不一致"
4. 不要在标签外输出多余内容
5. 注意：章节大纲可能只生成了部分，不要因为"缺少后续章节"而报错，只检查已有的数据
6. 在每项XML标签内的结果开头，必须用符号标明结论：✓ 表示无问题，⚠ 表示有问题。例如：<content_chapter_outline>✓ 正文与章节大纲对齐：正文完整覆盖了所有要点...</content_chapter_outline>
7. 如果某项检查结论是无问题（✓），则该项的详细描述中不要出现"不一致""偏离""矛盾"等负面词汇"""

    try:
        gen = get_generator()
        raw_result = gen.ai.generate(prompt)
        results = {}
        tags = [item[0] for item in check_items]
        for tag in tags:
            match = re.search(f'<{tag}>([\\s\\S]*?)</{tag}>', raw_result)
            if match:
                results[tag] = match.group(1).strip()
            else:
                results[tag] = None

        # 子项标签映射
        sub_labels = {item[0]: item[1] for item in check_items}

        parsed_count = sum(1 for v in results.values() if v is not None)

        # 根据子项结论重建干净的result文本，避免AI自相矛盾
        issue_count = 0
        clean_parts = []
        for tag in tags:
            if results.get(tag):
                text = results[tag]
                is_issue = text.startswith('⚠')
                if is_issue:
                    issue_count += 1
                label = sub_labels.get(tag, tag)
                clean_parts.append(f"{'⚠' if is_issue else '✓'} {label}\n{text}")
        if clean_parts:
            clean_result = f"[全局一致性]阶段{2 if has_content else 1}：全文一致性{'⚠ ' + str(issue_count) + '项不一致' if issue_count > 0 else '✓ 全部一致'}\n\n" + "\n\n".join(clean_parts)
        else:
            clean_result = raw_result

        return {
            "ok": True,
            "result": clean_result,
            "results": results,
            "sub_labels": sub_labels,
            "parsed_count": parsed_count,
            "total": len(tags),
            "stage": 2 if has_content else 1,
            "raw": raw_result if parsed_count < len(tags) - 1 else None
        }
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")

