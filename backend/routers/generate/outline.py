# -*- coding: utf-8 -*-
import logging
from fastapi import APIRouter

from backend.services.project_service import state, get_generator
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)

from ._models import OutlineRequest, ChapterOutlineRequest, VolumeOutlineRequest, NextChapterOutlineRequest

router = APIRouter()

def _get_current_vol_position(chapter_index: int) -> bool:
    """获取当前章节所在卷是否为最后一卷"""
    try:
        volumes = state.project.volumes or []
        if volumes:
            ch_num = chapter_index + 1
            for vi, vol in enumerate(volumes):
                vol_chs = vol.get('chapters', [])
                if ch_num in vol_chs:
                    return vi == len(volumes) - 1
    except Exception:
        pass
    return False

# ═══════════════════════════════════════════
# 后台任务管理器（线程池 + 任务状态追踪）
# ═══════════════════════════════════════════

@router.post("/outline")
def generate_outline(data: OutlineRequest):
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    gen = get_generator()
    result = gen.generate_outline(data.title, data.genre, data.length, volume_index=data.volume_index)
    return {"ok": True, "outline": result}

def _get_effective_outline(ch: dict) -> str:
    """获取章节的有效大纲：优先 outline 字段，太短则从 blueprint 拼接"""
    outline = ch.get("outline", "").strip()
    # outline 有实质内容（不只是标题），直接用
    if len(outline) > 50:
        return outline
    # outline 太短，从 blueprint 拼接
    bp = ch.get("blueprint", {})
    if not bp:
        return outline
    import json as _json
    parts = []
    section_map = [
        ("intro", "【起】"),
        ("development", "【承】"),
        ("climax", "【转】"),
        ("ending", "【合】"),
    ]
    for key, tag in section_map:
        section = bp.get(key)
        if section:
            parts.append(f"{tag}{_json.dumps(section, ensure_ascii=False)}")
    return "\n".join(parts) if parts else outline

@router.post("/chapter-outline")
def generate_chapter_outline(data: ChapterOutlineRequest):
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    try:
        gen = get_generator()

        # 注入故事弧定位
        chapter_index = data.chapter_index
        total = len(state.project.chapters or [])
        progress = (chapter_index + 1) / total if total > 0 else 0
        ch_num = chapter_index + 1

        current_vol_is_last = _get_current_vol_position(chapter_index)

        is_extended = False
        if chapter_index > 0 and state.project.chapters and chapter_index < len(state.project.chapters):
            prev_ch = state.project.chapters[chapter_index - 1]
            if prev_ch.get('blueprint', {}).get('extended'):
                is_extended = True

        if is_extended:
            arc_stage = "【当前卷收尾】这是当前卷的后期，可以收束本卷的主要冲突，但全书故事仍在继续。可以留新的悬念引出下一卷。" if (current_vol_is_last and progress > 0.85) else "【故事延续中】故事正在连载中，保持张力和悬念。本卷要有阶段性成果，但为后续发展留空间。"
        elif current_vol_is_last and progress > 0.85:
            arc_stage = "【结局阶段】故事走向收尾，解决主要冲突，回收剩余伏笔，交代角色结局。"
        elif progress <= 0.15:
            arc_stage = "【开局阶段】这是故事开头，需要建立世界观、引入主角、设定初始冲突。节奏可以稍慢，重在铺垫。"
        elif progress <= 0.4:
            arc_stage = "【发展阶段】故事正在展开，冲突逐步升级，角色关系深化。保持节奏推进，不要过早进入高潮。"
        elif progress <= 0.7:
            arc_stage = "【上升阶段】冲突加剧，stakes提高，角色面临更大挑战。为高潮做铺垫，伏笔开始回收。"
        elif progress <= 0.9:
            arc_stage = "【高潮阶段】故事进入最紧张的部分，主要冲突爆发，角色做出关键抉择。节奏紧凑，张力拉满。"
        else:
            arc_stage = "【结局阶段】故事走向收尾，解决主要冲突，回收剩余伏笔，交代角色结局。"

        # 在context中注入故事弧定位
        arc_context = "\n\n## 【故事弧定位】\n" + arc_stage + "\n"
        enhanced_context = (data.context or "") + arc_context

        result = gen.generate_chapter_outline(data.title, enhanced_context, chapter_index=chapter_index)
        # result 是 {raw, blueprint, outline_text} 结构
        ol_text = result.get("outline_text") or result.get("raw", "")
        bp = result.get("blueprint")
        # 保存到后端
        chapter_index = data.chapter_index
        if chapter_index >= 0:
            save_data = {"index": chapter_index, "outline": ol_text}
            if bp:
                save_data["blueprint"] = bp
            try:
                from backend.services.chapter_service import save_chapter_outline as _save
                _save(save_data)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("save_chapter_outline failed: %s", e)
        return {
            "ok": True,
            "outline": ol_text,
            "blueprint": bp,
            "raw": result.get("raw", "")
        }
    except Exception as e:
        import traceback; traceback.print_exc()
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")

@router.post("/volume-outline/{vol_index}")
def generate_volume_outline(vol_index: int, data: VolumeOutlineRequest = None):
    """AI生成本卷纲要（summary/theme/key_events/character_arcs）"""
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    try:
        volumes = state.project.get_volumes()
        if vol_index < 0 or vol_index >= len(volumes):
            return err(ErrorCode.INTERNAL_ERROR, "卷索引无效")
        vol = volumes[vol_index]
        inspiration = data.inspiration if data and data.inspiration else ""

        # 收集上下文
        ctx_parts = []
        # 灵感碎片（优先）
        if inspiration:
            ctx_parts.append("【灵感碎片】\n" + inspiration[:2000])

        # 全书大纲
        novel_outline = state.project.get_novel_outline()
        if novel_outline and isinstance(novel_outline, dict):
            parts = []
            if novel_outline.get('theme'):
                parts.append("【主题】" + novel_outline['theme'])
            if novel_outline.get('core_conflict'):
                parts.append("【核心冲突】" + novel_outline['core_conflict'])
            if novel_outline.get('story_arc'):
                parts.append("【故事走向】" + novel_outline['story_arc'])
            if novel_outline.get('world_anchor'):
                parts.append("【世界观锚点】" + str(novel_outline['world_anchor'])[:500])
            if novel_outline.get('character_arcs'):
                arc_lines = []
                for arc in novel_outline['character_arcs'][:8]:
                    if isinstance(arc, dict):
                        arc_lines.append(f"  - {arc.get('character','')}: {arc.get('arc','')}")
                    elif isinstance(arc, str):
                        arc_lines.append(f"  - {arc}")
                if arc_lines:
                    parts.append("【角色弧光】\n" + "\n".join(arc_lines))
            if novel_outline.get('ending'):
                parts.append("【结局指引】" + novel_outline['ending'])
            if novel_outline.get('tone'):
                parts.append("【基调】" + novel_outline['tone'])
            nol_text = "\n".join(parts)
            if nol_text:
                ctx_parts.append("【全书大纲】\n" + nol_text[:2000])

        # 世界观设定
        try:
            from backend.generator import WorldBuilder
            wb = WorldBuilder(state.project.world_settings or {})
            world_text = wb.to_prompt()
            if world_text:
                ctx_parts.append("【世界观设定】\n" + world_text[:1500])
            ws = getattr(state.project, 'world_settings', None) or {}
            if ws and isinstance(ws, dict):
                ws_lines = [f"- {k}：{v}" for k, v in ws.items() if v and str(v).strip()]
                if ws_lines:
                    ctx_parts.append("【自由格式世界观设定】\n" + "\n".join(ws_lines[:1000]))
        except Exception:
            pass

        # 人物设定
        try:
            chars = state.project.characters or []
            if chars:
                char_lines = []
                for c in chars[:10]:
                    name = c.get('name', '')
                    identity = c.get('identity', '')
                    faction = c.get('faction', '')
                    goal = c.get('goal', '')
                    desc = f"- {name}"
                    if identity: desc += f"（{identity}）"
                    if faction: desc += f" 阵营：{faction}"
                    if goal: desc += f" 目标：{goal}"
                    char_lines.append(desc)
                if char_lines:
                    ctx_parts.append("【人物设定】\n" + "\n".join(char_lines[:1500]))
        except Exception:
            pass

        # 前卷纲要
        prev_outline = {}
        if vol_index > 0:
            try:
                prev_outline = state.project.get_volume_outline(vol_index - 1)
            except Exception: pass
        if prev_outline.get("summary"):
            ctx_parts.append("【前一卷概要】" + prev_outline.get("summary", "")[:500])

        # 当前卷的基础信息
        ch_list = []
        chapters = state.project.chapters or []
        for ci in (vol.get("chapters") or []):
            idx = ci - 1
            if 0 <= idx < len(chapters):
                ch_list.append(chapters[idx].get("title", "第%d章" % ci))
        ctx_parts.append("【本卷信息】\n卷标题: %s\n包含章节: %s" % (vol.get("title", ""), "、".join(ch_list)))

        context = "\n\n".join(ctx_parts)

        prompt = """你是一位资深小说编辑。请根据以上信息，为本卷生成纲要。"""
        if inspiration:
            prompt += """请重点参考【灵感碎片】中的想法，结合全书大纲和世界观设定，将灵感转化为结构化的卷纲要。"""
        prompt += """请严格按照以下JSON格式输出（不要输出其他内容）：

{
  "theme": "本卷核心主题（一句话，12字以内）",
  "summary": "本卷故事概要（100-200字，包含本卷的起承转合）",
  "key_events": ["关键事件1", "关键事件2", "关键事件3"],
  "character_arcs": ["角色弧线描述1", "角色弧线描述2"]
}

要求：
- theme：提炼本卷最核心的矛盾或主题
- summary：简述本卷从开局到收束的完整故事脉络
- key_events：3-5个推动剧情的关键事件节点
- character_arcs：主要角色在本卷中的成长或转变"""

        gen = get_generator()
        # chat() 只接受 messages 列表，不支持 context 参数
        # 将 context 和 prompt 合并为 messages
        full_prompt = context + "\n\n" + prompt if context else prompt
        raw = gen.chat([{"role": "user", "content": full_prompt}]) if hasattr(gen, 'chat') else ""

        # 解析JSON
        import json, re
        obj = {"theme": "", "summary": "", "key_events": [], "character_arcs": []}
        try:
            # 尝试提取JSON块
            m = re.search(r'\{[\s\S]*\}', raw)
            if m:
                obj = json.loads(m.group())
        except Exception: pass

        state.project.set_volume_outline(vol_index, {
            "theme": obj.get("theme", ""),
            "summary": obj.get("summary", ""),
            "key_events": obj.get("key_events", []),
            "character_arcs": obj.get("character_arcs", [])
        })
        state.project.save_all()

        return {"ok": True, "data": obj}
    except Exception as e:
        import traceback; traceback.print_exc()
        return err(ErrorCode.INTERNAL_ERROR, f"生成失败: {str(e)}")

@router.post("/next-chapter-outline")
def generate_next_chapter_outline(data: NextChapterOutlineRequest):
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "no project")
    current_idx = data.current_chapter_index
    next_idx = current_idx + 1  # 下一章的索引

    # 故事弧定位（针对下一章）
    total = len(state.project.chapters or [])
    progress = (next_idx + 1) / total if total > 0 else 0
    ch_num = next_idx + 1

    current_vol_is_last = False
    try:
        volumes = state.project.volumes or []
        if volumes:
            for vi, vol in enumerate(volumes):
                vol_chs = vol.get('chapters', [])
                if ch_num in vol_chs:
                    current_vol_is_last = (vi == len(volumes) - 1)
                    break
    except Exception:
        pass

    is_extended = False
    if current_idx >= 0 and state.project.chapters and current_idx < len(state.project.chapters):
        prev_ch = state.project.chapters[current_idx]
        if prev_ch.get('blueprint', {}).get('extended'):
            is_extended = True

    if is_extended:
        arc_stage = "【当前卷收尾】这是当前卷的后期，可以收束本卷的主要冲突，但全书故事仍在继续。" if (current_vol_is_last and progress > 0.85) else "【故事延续中】故事正在连载中，保持张力和悬念。"
    elif current_vol_is_last and progress > 0.85:
        arc_stage = "【结局阶段】故事走向收尾，解决主要冲突，回收剩余伏笔，交代角色结局。"
    elif progress <= 0.15:
        arc_stage = "【开局阶段】这是故事开头，需要建立世界观、引入主角、设定初始冲突。"
    elif progress <= 0.4:
        arc_stage = "【发展阶段】故事正在展开，冲突逐步升级，角色关系深化。"
    elif progress <= 0.7:
        arc_stage = "【上升阶段】冲突加剧，角色面临更大挑战。伏笔开始回收。"
    elif progress <= 0.9:
        arc_stage = "【高潮阶段】故事进入最紧张的部分，主要冲突爆发，角色做出关键抉择。"
    else:
        arc_stage = "【结局阶段】故事走向收尾，解决主要冲突，回收剩余伏笔。"

    novel_outline = state.project.get_outline_text()
    prev_content = ""
    if current_idx > 0:
        prev_content = state.project.get_content(current_idx - 1)
    current_outline = ""
    if current_idx < len(state.project.chapters):
        current_outline = state.project.chapters[current_idx].get("outline", "")
    prompt = f"""基于以下信息，为下一章生成详细的章节大纲（5-8个情节要点）：

【故事弧定位】
{arc_stage}


【全书大纲】
{novel_outline[:2000]}

【前一章内容摘要】
{prev_content[:1500]}

【当前章已有大纲】
{current_outline}

请生成下一章的详细大纲，每个要点包含：
1. 场景/地点
2. 涉及角色
3. 关键事件
4. 情绪基调
5. 与前后文的关联

返回格式：每行一个要点，用"- "开头。"""
    try:
        gen = get_generator()
        result = gen.ai.generate(prompt)
        return {"ok": True, "outline": result}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")
