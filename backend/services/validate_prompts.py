# -*- coding: utf-8 -*-
import json
import os
import logging

from backend.services.project_service import state

logger = logging.getLogger(__name__)


"""Prompt 构建器 — 为各类型验证检查生成 AI Prompt"""


def _build_memory_section(ctx):
    memory = ctx.get("memory", "")
    if memory:
        return f"\n\n【全文记忆参考】\n{memory}\n\n请结合以上记忆进行检查。"
    return ""


def _build_timeline_section(ctx):
    """从 timeline.json 提取有偏差的章节，生成精简时间线对照摘要（最多5条）。"""
    try:
        if not state.project:
            return ""
        timeline_path = os.path.join(state.project.project_dir, "timeline.json")
        if not os.path.exists(timeline_path):
            return ""
        with open(timeline_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        volumes = data.get("volumes", {})
        if not volumes:
            return ""
        lines = []
        for vi, vol in volumes.items():
            vol_title = vol.get("title", f"卷{int(vi)+1}")
            chapters = vol.get("chapters", {})
            for ci, ch in chapters.items():
                planned = (ch.get("planned") or "").strip()
                actual = (ch.get("actual") or "").strip()
                divergences = ch.get("divergences") or []
                if not planned and not actual:
                    continue
                if planned != actual or divergences:
                    ch_title = ch.get("title", "")
                    label = f"第{int(ci)+1}章" + (f"({ch_title})" if ch_title else "")
                    planned_short = planned[:80].replace("\n", " ") + ("..." if len(planned) > 80 else "")
                    actual_short = actual[:80].replace("\n", " ") + ("..." if len(actual) > 80 else "")
                    if divergences:
                        dev_text = "; ".join(d.get("desc", "")[:40] for d in divergences[:2])
                        lines.append(f"- {label} 计划:{planned_short} → 实际:{actual_short}（偏差:{dev_text}）")
                    else:
                        lines.append(f"- {label} 计划:{planned_short} → 实际:{actual_short}")
                if len(lines) >= 5:
                    break
            if len(lines) >= 5:
                break
        if not lines:
            return ""
        return "\n\n【时间线对照】（计划 vs 实际，仅列出有偏差的章节）\n" + "\n".join(lines)
    except Exception:
        return ""


def _build_drift_prompt(content, ctx):
    stage = ctx.get("stage", "content")
    mem = _build_memory_section(ctx)
    tls = _build_timeline_section(ctx)
    if stage == "settings":
        return f"检查以下设定项是否与已有设定矛盾：\n\n{content}{mem}{tls}\n\n如有矛盾请指出，否则返回'无矛盾'。"
    elif stage == "chapter-outline":
        chapter_index = ctx.get("chapterIndex", 0)
        return f"""你是小说大纲审核专家。请严格审查章节大纲，找出所有逻辑漏洞、遗漏和矛盾。

【当前是第{chapter_index + 1}章】

【当前章节大纲】
{content}
{mem}{tls}

请逐项检查：
1. **剧情遗漏**：章节大纲是否有明显的剧情遗漏或不完整之处？
2. **剧情矛盾**：章节大纲内部是否有前后矛盾的内容？
3. **时间线问题**：章节大纲中的事件顺序是否连贯合理？
4. **角色状态**：章节大纲中角色所处的状态（位置、身份、关系）是否合理？

输出格式：
- 如无问题：返回"无偏离"
- 如有问题：按上述4项逐一列出，每项用"### 标题"开头，下面用"- "列出具体问题
- 每个具体问题必须标注位置，格式：【位置】段落编号（如"第3段"、"第2-4段"），可附带场景描述"""
    else:
        # 正文阶段：正文↔章节大纲两方比对
        chapter_outline = ctx.get("chapterOutline", "")
        prev_outline = ctx.get("prevChapterOutline", "")
        chapter_index = ctx.get("chapterIndex", 0)
        prev_section = ""
        if prev_outline:
            prev_section = f"""
【前一章大纲参考】
{prev_outline}"""
        return f"""你是小说审核专家。请进行正文↔章节大纲比对，找出所有偏离、遗漏和矛盾。

【当前是第{chapter_index + 1}章】

【第{chapter_index + 1}章大纲】
{chapter_outline if chapter_outline else '（未提供）'}
{prev_section}

【正文内容（共{len(content)}字）】
{content[:12000]}
{mem}{tls}

请逐项检查，**只报告重大偏离**：
1. **关键情节遗漏**：章节大纲中规划的**核心情节**（主要冲突、关键转折、重要场景），正文是否完全遗漏？（注意：措辞调整、细节略写不算遗漏）
2. **重大剧情偏离**：正文是否包含了与章节大纲**明显矛盾**的自行发挥情节？（注意：合理的细节补充、对话润色不算偏离）
3. **角色状态矛盾**：正文中的角色状态（位置/身份/关系）是否与章节大纲**严重不一致**？{f"4. **章节衔接断裂**：正文开头是否与前一章结尾**明显不连贯**？" if prev_outline else ""}

**重要**：以下情况**不算问题**，不要报告：
- 措辞调整、对话润色、描写细化
- 合理的细节补充和情节推进
- 略写不重要的过渡细节
- 正常的写作风格差异

输出格式：
- 如无重大偏离：返回"无偏离"
- 如有重大偏离：按上述各项逐一列出，每项用"### 标题"开头，下面用"- "列出具体问题
- 每个具体问题必须标注位置，格式：【位置】段落编号（按空行分段，如"第3段"、"第2-4段"），可附带场景描述"""


def _build_twist_prompt(content, ctx):
    mem = _build_memory_section(ctx)
    return f"分析以下内容的转折设计是否合理自然：\n\n{content}{mem}\n\n评价转折的合理性和冲击力，给出建议。\n\n输出格式：\n- 如无问题：返回'转折合理'\n- 如有问题：列出具体问题，每个问题必须标注【位置】段落编号（按空行分段，如'第3段'、'第2-4段'），可附带场景描述"


def _build_duplicate_prompt(content, ctx):
    stage = ctx.get("stage", "content")
    all_items = ""
    if stage == "chapter-outline":
        all_items = ""
    elif stage == "settings":
        all_items = "\n".join([f"{s.get('key','')}: {s.get('val','')}" for s in ctx.get("allSettings", [])])
    elif stage == "content":
        # 正文阶段：获取前一章内容用于跨章重复检测
        chapter_index = ctx.get("chapterIndex", 0)
        if chapter_index > 0 and state.project:
            try:
                prev_items = []
                # 只取前一章的摘要（前2000字），避免prompt过长
                for pi in range(max(0, chapter_index - 1), chapter_index):
                    try:
                        prev_content = state.project.get_content(pi)
                        if prev_content and prev_content.strip():
                            prev_title = state.project.chapters[pi].get("title", f"第{pi+1}章") if 0 <= pi < len(state.project.chapters) else f"第{pi+1}章"
                            prev_items.append(f"【{prev_title}】\n{prev_content[:2000]}")
                    except Exception:
                        pass
                if prev_items:
                    all_items = "\n\n".join(prev_items)
            except Exception:
                pass
    mem = _build_memory_section(ctx)
    note = ""
    if stage == "chapter-outline":
        note = "\n\n注意：\n1. 章节内部不同场景之间出现相同或高度相似的描写\n2. 章节内容与前几章已写过的具体情节完全重复\n\n如有重复请指出具体重复内容，否则返回'无重复'。\n输出格式：每个重复问题必须标注【位置】段落编号（如'第3段'、'第2-4段'）。"
    elif stage == "content":
        note = "\n\n检查要点：\n1. 当前章节内部是否有重复或高度相似的描写（相同段落、相同对话、相同场景）\n2. 当前章节是否与前一章有完全重复的具体情节（不是概述性回顾）\n3. 注意：简要回顾前情（一两句话）属于正常衔接，不算重复\n\n如有重复请指出具体重复内容，否则返回'无重复'。\n输出格式：每个重复问题必须标注【位置】段落编号（按空行分段，如'第3段'、'第2-4段'），可附带场景描述。"
    else:
        note = "\n\n如有重复请指出具体重复内容，否则返回'无重复'。\n输出格式：每个重复问题必须标注【位置】段落编号（如'第3段'、'第2-4段'）。"
    return f"检查以下内容是否有重复：\n\n{content}\n\n已有内容：\n{all_items if all_items else '（无前文参考）'}{mem}{note}"


def _build_style_prompt(content, ctx):
    mem = _build_memory_section(ctx)
    return f"评价以下内容的文笔风格一致性：\n\n{content}{mem}\n\n指出风格不一致的地方。\n\n输出格式：\n- 如无问题：返回'风格一致'\n- 如有问题：列出具体问题，每个问题必须标注【位置】段落编号（按空行分段，如'第3段'、'第2-4段'），可附带场景描述"


def _build_timeline_prompt(content, ctx):
    stage = ctx.get("stage", "content")
    mem = _build_memory_section(ctx)
    if stage == "chapter-outline":
        chapter_index = ctx.get("chapterIndex", 0)
        return f"""检查第{chapter_index + 1}章大纲内部的时间线是否连贯合理。

【第{chapter_index + 1}章大纲】
{content}
{mem}

检查要点：
1. 章节大纲中的事件是否发生在正确的时间点
2. 与前文事件的时间间隔是否合理
3. 是否有时间跳跃或倒叙未标注

如有问题请指出，否则返回'无矛盾'。\n输出格式：每个时间线问题必须标注【位置】段落编号（如'第3段'、'第2-4段'），可附带时间点描述。"""
    # 正文阶段：对照章节大纲检查时间线
    chapter_outline = ctx.get("chapterOutline", "")
    chapter_index = ctx.get("chapterIndex", 0)
    return f"""检查第{chapter_index + 1}章正文的时间线是否与章节大纲一致。

【第{chapter_index + 1}章大纲】
{chapter_outline if chapter_outline else '（未提供）'}

【正文内容】
{content[:12000]}
{mem}

检查要点：
1. 正文中的事件顺序是否与章节大纲一致
2. 与前文事件的时间间隔是否合理
3. 是否有时间跳跃或倒叙未标注

如有问题请指出，否则返回'无矛盾'。\n输出格式：每个时间线问题必须标注【位置】段落编号（按空行分段，如'第3段'、'第2-4段'），可附带时间点描述。"""


def _build_conflict_prompt(content, ctx):
    stage = ctx.get("stage", "content")
    mem = _build_memory_section(ctx)
    tls = _build_timeline_section(ctx)
    if stage == "chapter-outline":
        chapter_index = ctx.get("chapterIndex", 0)
        return f"""检查第{chapter_index + 1}章大纲是否存在设定冲突。

【第{chapter_index + 1}章大纲】
{content}
{mem}{tls}

检查要点：
1. 角色在章节大纲中的身份/位置是否合理
2. 章节大纲中的能力/道具使用是否与设定矛盾
3. 章节大纲中的角色关系是否合理

如有冲突请指出，否则返回'无冲突'。\n输出格式：每个冲突问题必须标注【位置】段落编号（如'第3段'、'第2-4段'），可附带场景描述。"""
    # 正文阶段：对照章节大纲检查设定冲突
    chapter_outline = ctx.get("chapterOutline", "")
    chapter_index = ctx.get("chapterIndex", 0)
    return f"""检查第{chapter_index + 1}章正文是否存在设定冲突（正文↔章节大纲比对）。

【第{chapter_index + 1}章大纲】
{chapter_outline if chapter_outline else '（未提供）'}

【正文内容】
{content[:12000]}
{mem}{tls}

检查要点：
1. 正文中的角色身份/位置是否与章节大纲一致（如大纲写在内门，正文不应在外门）
2. 正文中的能力/道具使用是否与章节大纲设定矛盾
3. 正文中的角色关系是否与章节大纲矛盾
4. 正文是否引入了与已有设定冲突的新元素

如有冲突请指出，否则返回'无冲突'。\n输出格式：每个冲突问题必须标注【位置】段落编号（按空行分段，如'第3段'、'第2-4段'），可附带场景描述。"""


def _build_quality_prompt(content, ctx):
    mem = _build_memory_section(ctx)
    return f"综合评价以下内容的质量（完整性、表达清晰度、吸引力）：\n\n{content}{mem}\n\n给出评分和改进建议。\n\n输出格式：\n- 先给出质量评分（1-10分）和总体评价\n- 然后列出具体问题，每个问题必须标注【位置】段落编号（按空行分段，如'第3段'、'第2-4段'），可附带场景描述"


def _build_memory_prompt(content, ctx):
    mem = _build_memory_section(ctx)
    return f"检查以下内容是否与全文记忆一致（角色关系、已发生事件、已揭示信息等）：\n\n{content}{mem}\n\n指出不一致之处。\n\n输出格式：\n- 如无问题：返回'记忆一致'\n- 如有问题：列出具体不一致之处，每个问题必须标注【位置】段落编号（按空行分段，如'第3段'、'第2-4段'），可附带场景描述"


# ═══════════════════════════════════════════
# 局部修复端点
# ═══════════════════════════════════════════


