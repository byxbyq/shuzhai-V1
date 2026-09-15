# -*- coding: utf-8 -*-
"""generate 子包"""
import threading
from typing import Any
from fastapi import APIRouter
from pydantic import BaseModel

from backend.task_manager import task_manager, TaskStatus
from backend.api_models import err, ErrorCode

from .outline import router as outline_router
from .inspiration import router as inspiration_router
from .batch import router as batch_router
from .confirmation import router as confirmation_router
from .coverage import router as coverage_router

router = APIRouter(prefix="/api/generate")
router.include_router(outline_router)
router.include_router(inspiration_router)
router.include_router(batch_router)
router.include_router(confirmation_router)
router.include_router(coverage_router)

# Re-export models for backward compatibility
from ._models import (
    OutlineRequest, ChapterOutlineRequest, InspirationToBlueprintRequest,
    InspirationToNovelOutlineRequest, VolumeOutlineRequest, CancelGenerateRequest,
    ExtractStateRequest, NextChapterOutlineRequest, GenerateRequest,
    ConfirmRequest, CoverageRequest
)

# Re-export helpers
from .outline import _get_effective_outline
from .batch import _task_manager


# ═══════════════════════════════════════════
# P0-2 Phase 2：异步端点（后台任务模式）
# ═══════════════════════════════════════════

class AsyncGenerateRequest(BaseModel):
    """异步生成请求：task_type 指定操作类型，params 透传参数"""
    task_type: str   # outline / chapter_outline / volume_outline / next_outline / inspiration_blueprint / inspiration_novel / gate
    params: dict = {}


def _do_generate_task(info: Any, cancel_event: threading.Event, task_type: str, params: dict):
    """后台线程中执行的生成逻辑，支持取消令牌与进度上报。"""
    from backend.services.project_service import state, get_generator

    if not state.project:
        return {"ok": False, "error": "没有打开的项目"}

    tid = info.task_id

    # ── 大纲生成 ──
    if task_type == "outline":
        task_manager.update_progress(tid, 10, "正在生成大纲...")
        if cancel_event.is_set(): return {"ok": False, "cancelled": True}
        gen = get_generator()
        result = gen.generate_outline(
            params.get("title", ""),
            params.get("genre", ""),
            params.get("length", 10),
            volume_index=params.get("volume_index"),
        )
        return {"ok": True, "outline": result}

    # ── 章节大纲 ──
    elif task_type == "chapter_outline":
        from .outline import _get_current_vol_position
        chapter_index = params.get("chapter_index", 0)
        total = len(state.project.chapters or [])
        progress_ratio = (chapter_index + 1) / total if total > 0 else 0
        current_vol_is_last = _get_current_vol_position(chapter_index)
        is_extended = (
            chapter_index > 0
            and state.project.chapters
            and chapter_index < len(state.project.chapters)
            and state.project.chapters[chapter_index - 1].get("blueprint", {}).get("extended")
        )
        if is_extended:
            arc_stage = (
                "【当前卷收尾】" if (current_vol_is_last and progress_ratio > 0.85)
                else "【故事延续中】"
            )
        elif current_vol_is_last and progress_ratio > 0.85:
            arc_stage = "【结局阶段】"
        elif progress_ratio <= 0.15:
            arc_stage = "【开局阶段】"
        elif progress_ratio <= 0.4:
            arc_stage = "【发展阶段】"
        elif progress_ratio <= 0.7:
            arc_stage = "【上升阶段】"
        elif progress_ratio <= 0.9:
            arc_stage = "【高潮阶段】"
        else:
            arc_stage = "【结局阶段】"

        task_manager.update_progress(tid, 20, f"正在生成第{chapter_index+1}章大纲...")
        if cancel_event.is_set(): return {"ok": False, "cancelled": True}

        arc_context = "\n\n## 【故事弧定位】\n" + arc_stage + "\n"
        enhanced_context = (params.get("context", "") or "") + arc_context

        gen = get_generator()
        result = gen.generate_chapter_outline(
            params.get("title", ""), enhanced_context, chapter_index=chapter_index
        )
        ol_text = result.get("outline_text") or result.get("raw", "")
        bp = result.get("blueprint")
        if chapter_index >= 0:
            save_data = {"index": chapter_index, "outline": ol_text}
            if bp:
                save_data["blueprint"] = bp
            try:
                from backend.services.chapter_service import save_chapter_outline as _save
                _save(save_data)
            except Exception:
                pass
        return {"ok": True, "outline": ol_text, "blueprint": bp, "raw": result.get("raw", "")}

    # ── 卷大纲 ──
    elif task_type == "volume_outline":
        vol_index = params.get("vol_index", 0)
        task_manager.update_progress(tid, 10, f"正在生成第{vol_index+1}卷纲要...")
        if cancel_event.is_set(): return {"ok": False, "cancelled": True}

        volumes = state.project.volumes or []
        if vol_index < 0 or vol_index >= len(volumes):
            return {"ok": False, "error": "卷索引无效"}
        vol = volumes[vol_index]
        inspiration = params.get("inspiration", "")

        ctx_parts = []
        if inspiration:
            ctx_parts.append("【灵感碎片】\n" + inspiration[:2000])

        novel_outline = state.project.get_novel_outline()
        if novel_outline and isinstance(novel_outline, dict):
            parts = []
            if novel_outline.get("theme"): parts.append("【主题】" + novel_outline["theme"])
            if novel_outline.get("core_conflict"): parts.append("【核心冲突】" + novel_outline["core_conflict"])
            if novel_outline.get("story_arc"): parts.append("【故事走向】" + novel_outline["story_arc"])
            if novel_outline.get("world_anchor"): parts.append("【世界观锚点】" + str(novel_outline["world_anchor"])[:500])
            if novel_outline.get("character_arcs"):
                arc_lines = []
                for arc in novel_outline["character_arcs"][:8]:
                    if isinstance(arc, dict): arc_lines.append(f"  - {arc.get('character','')}: {arc.get('arc','')}")
                    elif isinstance(arc, str): arc_lines.append(f"  - {arc}")
                if arc_lines: parts.append("【角色弧光】\n" + "\n".join(arc_lines))
            if novel_outline.get("ending"): parts.append("【结局指引】" + novel_outline["ending"])
            if novel_outline.get("tone"): parts.append("【基调】" + novel_outline["tone"])
            nol_text = "\n".join(parts)
            if nol_text: ctx_parts.append("【全书大纲】\n" + nol_text[:2000])

        try:
            from backend.generator import WorldBuilder
            wb = WorldBuilder(state.project.world_settings or {})
            world_text = wb.to_prompt()
            if world_text: ctx_parts.append("【世界观设定】\n" + world_text[:1500])
        except Exception:
            pass

        chars = state.project.characters or []
        if chars:
            char_lines = []
            for c in chars[:10]:
                name = c.get("name", "")
                identity = c.get("identity", "")
                desc = f"- {name}"
                if identity: desc += f"（{identity}）"
                char_lines.append(desc)
            if char_lines: ctx_parts.append("【人物设定】\n" + "\n".join(char_lines[:1500]))

        if vol_index > 0:
            try:
                prev = state.project.get_volume_outline(vol_index - 1)
                if prev.get("summary"): ctx_parts.append("【前一卷概要】" + prev["summary"][:500])
            except Exception:
                pass

        ch_list = []
        chapters = state.project.chapters or []
        for ci in (vol.get("chapters") or []):
            idx = ci - 1
            if 0 <= idx < len(chapters):
                ch_list.append(chapters[idx].get("title", f"第{ci}章"))
        ctx_parts.append(f"【本卷信息】\n卷标题: {vol.get('title','')}\n包含章节: {'、'.join(ch_list)}")

        context = "\n\n".join(ctx_parts)
        prompt = "你是一位资深小说编辑。请根据以上信息，为本卷生成纲要。"
        if inspiration:
            prompt += "请重点参考【灵感碎片】中的想法，结合全书大纲和世界观设定，将灵感转化为结构化的卷纲要。"
        prompt += """请严格按照以下JSON格式输出：
{"theme":"本卷核心主题","summary":"本卷故事概要（100-200字）","key_events":["事件1","事件2","事件3"],"character_arcs":["弧线1","弧线2"]}"""

        if cancel_event.is_set(): return {"ok": False, "cancelled": True}
        task_manager.update_progress(tid, 50, "AI生成卷纲要中...")
        gen = get_generator()
        full_prompt = context + "\n\n" + prompt if context else prompt
        raw = gen.chat([{"role": "user", "content": full_prompt}]) if hasattr(gen, "chat") else ""

        import json as _json, re as _re
        obj = {"theme": "", "summary": "", "key_events": [], "character_arcs": []}
        try:
            m = _re.search(r"\{[\s\S]*\}", raw)
            if m: obj = _json.loads(m.group())
        except Exception:
            pass

        state.project.set_volume_outline(vol_index, obj)
        state.project.save_all()
        return {"ok": True, "data": obj}

    # ── 下一章大纲 ──
    elif task_type == "next_outline":
        current_idx = params.get("current_chapter_index", 0)
        next_idx = current_idx + 1
        total = len(state.project.chapters or [])
        progress_ratio = (next_idx + 1) / total if total > 0 else 0
        arc_stage = "【发展阶段】"

        task_manager.update_progress(tid, 30, f"正在规划第{next_idx+1}章大纲...")
        if cancel_event.is_set(): return {"ok": False, "cancelled": True}

        novel_outline = state.project.get_outline_text()
        prev_content = state.project.get_content(current_idx - 1) if current_idx > 0 else ""
        current_outline = (
            state.project.chapters[current_idx].get("outline", "")
            if current_idx < len(state.project.chapters)
            else ""
        )
        prompt = f"""基于以下信息，为下一章生成详细章节大纲（5-8个情节要点）：
【故事弧定位】{arc_stage}
【全书大纲】{novel_outline[:2000]}
【前一章内容摘要】{prev_content[:1500]}
【当前章已有大纲】{current_outline}
请生成下一章的详细大纲，每个要点包含场景/地点、涉及角色、关键事件、情绪基调、与前后文的关联。
返回格式：每行一个要点，用"- "开头。"""
        task_manager.update_progress(tid, 50, "AI生成下一章大纲中...")
        gen = get_generator()
        result = gen.ai.generate(prompt)
        return {"ok": True, "outline": result}

    # ── 灵感→蓝图 ──
    elif task_type == "inspiration_blueprint":
        from .outline import _get_current_vol_position
        inspiration = params.get("inspiration", "").strip()
        chapter_index = params.get("chapter_index", 0)
        total = len(state.project.chapters or [])
        progress_ratio = (chapter_index + 1) / total if total > 0 else 0
        current_vol_is_last = _get_current_vol_position(chapter_index)
        is_extended = (
            chapter_index > 0 and state.project.chapters
            and chapter_index < len(state.project.chapters)
            and state.project.chapters[chapter_index - 1].get("blueprint", {}).get("extended")
        )
        if is_extended:
            arc_stage = "【当前卷收尾】" if (current_vol_is_last and progress_ratio > 0.85) else "【故事延续中】"
        elif current_vol_is_last and progress_ratio > 0.85:
            arc_stage = "【结局阶段】"
        elif progress_ratio <= 0.15:
            arc_stage = "【开局阶段】"
        elif progress_ratio <= 0.4:
            arc_stage = "【发展阶段】"
        elif progress_ratio <= 0.7:
            arc_stage = "【上升阶段】"
        elif progress_ratio <= 0.9:
            arc_stage = "【高潮阶段】"
        else:
            arc_stage = "【结局阶段】"

        task_manager.update_progress(tid, 20, f"正在将灵感转化为第{chapter_index+1}章蓝图...")
        if cancel_event.is_set(): return {"ok": False, "cancelled": True}

        base_context = params.get("context", "")
        arc_context = "\n\n## 【故事弧定位】\n" + arc_stage + "\n"
        inspiration_context = (
            base_context + arc_context
            + "\n## 【核心灵感碎片 — 本章必须围绕此主线展开】\n" + inspiration
            + "\n\n## 要求\n1. 以上述灵感碎片为核心主线，扩展为完整的章节大纲\n"
            "2. 灵感碎片中的场景、事件、人物关系必须成为本章的关键情节\n"
            "3. 在灵感基础上补充起承转合的完整结构\n"
            "4. 保持与全书大纲和前后章节的衔接\n"
            "5. 不要遗漏灵感碎片中的任何关键元素"
        )
        gen = get_generator()
        result = gen.generate_chapter_outline(
            params.get("title", ""), inspiration_context, chapter_index=chapter_index
        )
        ol_text = result.get("outline_text") or result.get("raw", "")
        bp = result.get("blueprint")
        if chapter_index >= 0:
            save_data = {"index": chapter_index, "outline": ol_text}
            if bp:
                save_data["blueprint"] = bp
            if bp and isinstance(bp, dict):
                bp["inspiration_source"] = inspiration[:200]
            try:
                from backend.services.chapter_service import save_chapter_outline as _save
                _save(save_data)
            except Exception:
                pass
        return {"ok": True, "outline": ol_text, "blueprint": bp, "raw": result.get("raw", "")}

    # ── 灵感→全书大纲 ──
    elif task_type == "inspiration_novel":
        task_manager.update_progress(tid, 20, "正在将灵感转化为全书大纲...")
        if cancel_event.is_set(): return {"ok": False, "cancelled": True}
        gen = get_generator()
        result = gen.generate_outline(
            params.get("title", ""),
            params.get("genre", ""),
            params.get("length", 30),
            inspiration=params.get("inspiration", ""),
        )
        return {"ok": True, "outline": result}

    # ── 章节生成（gate 模式） ──
    elif task_type == "gate":
        chapter_index = params.get("chapter_index", 0)
        task_manager.update_progress(tid, 10, f"正在生成第{chapter_index+1}章...")
        if cancel_event.is_set(): return {"ok": False, "cancelled": True}
        gen = get_generator()
        gen.reload_world()
        result = gen.generate_and_validate(
            params.get("title", ""),
            params.get("outline", ""),
            params.get("context", ""),
            chapter_index=chapter_index,
            max_retries=3,
            skill_rules=params.get("skill_rules", "") or "",
            use_distilled_memory=params.get("use_distilled_memory", True),
        )
        return result

    else:
        return {"ok": False, "error": f"未知的 task_type: {task_type}"}


# ═══════════════════════════════════════════
# 异步端点
# ═══════════════════════════════════════════

@router.post("/start")
def generate_start(data: AsyncGenerateRequest):
    """异步提交生成任务，立即返回 task_id。"""
    task_id = task_manager.submit("generate", _do_generate_task, data.task_type, data.params)
    return {"ok": True, "task_id": task_id}


@router.get("/status/{task_id}")
def generate_status(task_id: str):
    """查询异步生成任务的状态与进度。"""
    info = task_manager.get_status(task_id)
    if info is None:
        return err(ErrorCode.NOT_FOUND, f"任务不存在: {task_id}")
    return {"ok": True, **info.to_dict()}


@router.post("/cancel/{task_id}")
def generate_cancel(task_id: str):
    """取消正在执行的异步生成任务。"""
    ok = task_manager.cancel(task_id)
    if not ok:
        return err(ErrorCode.INTERNAL_ERROR, f"取消失败（任务不存在或已完成）")
    return {"ok": True, "cancelled": task_id}
