# -*- coding: utf-8 -*-
"""时间线路由 - /api/timeline/*

提供时间线（计划 vs 实际对照）的读取、手工编辑和 AI 对照功能。
"""

import logging

from fastapi import APIRouter
from backend.models.timeline_models import (
    PlannedUpdate, ActualUpdate, AnnotationUpdate,
    DivergenceStatusUpdate, DivergenceUpdate, DivergenceAdd,
    CompareRequest, DivergenceFixRequest,
)

from backend.services.project_service import state
from backend.timeline_service import TimelineService
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


# ═══════════════════════════════════════════════
# 请求模型
# ═══════════════════════════════════════════════



# ═══════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════

def _get_timeline_service() -> TimelineService:
    if not state.project:
        raise Exception("没有打开的项目")
    return TimelineService(state.project.project_dir)



def _fix_para_index(timeline_data, project):
    """为没有 para_index 的偏离项自动计算段落索引。"""
    if not timeline_data or not project:
        return
    volumes = timeline_data.get("volumes", {})
    for vol_key, vol in volumes.items():
        chapters = vol.get("chapters", {})
        for ch_key, ch in chapters.items():
            divergences = ch.get("divergences", [])
            if not divergences:
                continue
            # 获取章节正文（ch_key 是章节编号，不一定是数组索引）
            try:
                ch_num = int(ch_key)
                arr_idx = None
                for i, ch in enumerate(project.chapters or []):
                    if ch.get("index") == ch_num:
                        arr_idx = i
                        break
                if arr_idx is None:
                    arr_idx = ch_num - 1  # fallback
                content = project.get_content(arr_idx) if 0 <= arr_idx < len(project.chapters) else ""
            except Exception:
                content = ""
            if not content:
                continue
            paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
            if not paragraphs:
                continue
            # 为每个没有 para_index 的偏离项计算索引
            for d in divergences:
                if d.get('para_index') is not None:
                    continue
                search_text = d.get("item", "") or d.get("note", "")
                if not search_text:
                    continue
                best_idx = -1
                best_score = 0
                # 提取关键词（2-4字符的中文词组）
                keywords = set()
                text = search_text[:100]
                for i in range(len(text) - 1):
                    for length in [2, 3, 4]:
                        if i + length <= len(text):
                            word = text[i:i+length]
                            # 只保留包含中文的关键词
                            if any('\u4e00' <= c <= '\u9fff' for c in word):
                                keywords.add(word)
                # 用关键词匹配段落
                for pi, para in enumerate(paragraphs):
                    score = sum(1 for kw in keywords if kw in para)
                    if score > best_score:
                        best_score = score
                        best_idx = pi
                if best_idx >= 0 and best_score >= 2:
                    d["para_index"] = best_idx


def _ensure_structure():
    """确保时间线结构与项目当前卷/章结构一致。"""
    svc = _get_timeline_service()
    project = state.project

    # 收集卷信息
    volumes = []
    try:
        vols = project.volumes or []
    except Exception:
        vols = []
    for v in vols:
        vol_idx = v.get("index", v.get("volume_index", 0))
        volumes.append({"index": vol_idx, "title": v.get("title", "")})

    # 收集章节信息（按卷分组）
    chapters = []
    try:
        chs = project.chapters or []
    except Exception:
        chs = []

    # 构建章节索引到卷索引的映射（从 volumes 中读取）
    ch_to_vol = {}
    try:
        vols = project.volumes or []
        for v in vols:
            vol_idx = v.get("index", v.get("volume_index", 0))
            ch_list = v.get("chapters", [])
            for ci in ch_list:
                ch_to_vol[ci] = vol_idx
    except Exception:
        pass

    for ch_idx, ch in enumerate(chs):
        ch_num = ch.get("index", 0)
        vol_idx = ch_to_vol.get(ch_num)
        if vol_idx is None:
            vol_idx = ch.get("volume_index")
        if vol_idx is None:
            vol_idx = ch_idx // 20  # 默认每20章一卷
        chapters.append({
            "index": ch_num,
            "title": ch.get("title", ""),
            "volume_index": vol_idx,
            "array_index": ch_idx,
            "has_content": bool((project.get_content(ch_idx) or "").strip()),
        })

    svc.ensure_structure(volumes, chapters)
    return svc, chapters


# ═══════════════════════════════════════════════
# 路由
# ═══════════════════════════════════════════════

@router.get("")
def get_timeline():
    """获取完整时间线树，并确保结构与项目当前卷/章一致。"""
    try:
        svc, chapters = _ensure_structure()
        data = svc.get_timeline()
        # 附带章节状态信息（有内容/无内容）
        ch_info = {}
        for ch in chapters:
            ci = str(ch["index"])
            ch_info[ci] = {
                "title": ch["title"],
                "volume_index": ch["volume_index"],
                "has_content": ch["has_content"],
                "array_index": ch["array_index"],
            }
        # 自动修复：为没有 para_index 的偏离项计算段落索引
        from backend.services.project_service import state as proj_state
        _fix_para_index(data, proj_state.project)
        return {"ok": True, "timeline": data, "chapters": ch_info}
    except Exception as e:
        # 项目未打开时返回空时间线，而非错误
        if "没有打开的项目" in str(e):
            logger.info("时间线：项目未打开，返回空时间线")
            return {"ok": True, "timeline": {"volumes": {}}, "chapters": {}}
        logger.exception("获取时间线失败")
        return err(ErrorCode.INTERNAL_ERROR, str(e))


@router.get("/{volume_index}/{chapter_index}")
def get_chapter_timeline(volume_index: int, chapter_index: int):
    """获取某一章的时间线对照数据。"""
    try:
        svc = _get_timeline_service()
        node = svc.get_chapter(volume_index, chapter_index)
        if node is None:
            return {"ok": True, "data": None}
        return {"ok": True, "data": node}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, str(e))


@router.put("/{volume_index}/{chapter_index}/planned")
def update_planned(volume_index: int, chapter_index: int, body: PlannedUpdate):
    """更新某章的「计划」列。"""
    try:
        svc = _get_timeline_service()
        svc.update_planned(volume_index, chapter_index, body.planned)
        return {"ok": True}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, str(e))


@router.put("/{volume_index}/{chapter_index}/actual")
def update_actual(volume_index: int, chapter_index: int, body: ActualUpdate):
    """更新某章的「实际」列和分歧列表。"""
    try:
        svc = _get_timeline_service()
        svc.update_actual(volume_index, chapter_index, body.actual, body.divergences)
        return {"ok": True}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, str(e))


@router.put("/{volume_index}/{chapter_index}/annotation")
def update_annotation(volume_index: int, chapter_index: int, body: AnnotationUpdate):
    """更新手工注释。"""
    try:
        svc = _get_timeline_service()
        svc.update_annotation(volume_index, chapter_index, body.annotation)
        return {"ok": True}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, str(e))


@router.put("/{volume_index}/{chapter_index}/divergence-status")
def update_divergence_status(volume_index: int, chapter_index: int,
                             body: DivergenceStatusUpdate):
    """更新某条分歧的处理状态。"""
    try:
        svc = _get_timeline_service()
        svc.update_divergence_status(
            volume_index, chapter_index,
            body.divergence_index, body.status
        )
        return {"ok": True}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, str(e))


@router.put("/{volume_index}/{chapter_index}/divergence")
def update_divergence(volume_index: int, chapter_index: int,
                      body: DivergenceUpdate):
    """更新某条分歧的完整内容。"""
    try:
        svc = _get_timeline_service()
        data = {}
        if body.type:
            data["type"] = body.type
        if body.item:
            data["item"] = body.item
        if body.note:
            data["note"] = body.note
        if body.status:
            data["status"] = body.status
        svc.update_divergence(
            volume_index, chapter_index,
            body.divergence_index, data
        )
        return {"ok": True}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, str(e))


@router.delete("/{volume_index}/{chapter_index}/divergence/{divergence_index}")
def delete_divergence(volume_index: int, chapter_index: int,
                      divergence_index: int):
    """删除某条分歧。"""
    try:
        svc = _get_timeline_service()
        ok = svc.delete_divergence(volume_index, chapter_index, divergence_index)
        return {"ok": ok}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, str(e))


@router.post("/{volume_index}/{chapter_index}/divergence")
def add_divergence(volume_index: int, chapter_index: int,
                   body: DivergenceAdd):
    """新增一条分歧。"""
    try:
        svc = _get_timeline_service()
        idx = svc.add_divergence(
            volume_index, chapter_index,
            {"type": body.type, "item": body.item, "note": body.note, "status": body.status}
        )
        return {"ok": True, "index": idx}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, str(e))

# ═══════════════════════════════════════════════
# AI 对照 / 修复端点（委托到 timeline_ai_service）
# ═══════════════════════════════════════════════

@router.post("/{volume_index}/{chapter_index}/compare")
def ai_compare(volume_index: int, chapter_index: int, body: CompareRequest):
    """触发 AI 对照：计划 vs 实际。委托到 timeline_ai_service。"""
    from backend.services.timeline_ai_service import do_ai_compare
    return do_ai_compare(volume_index, chapter_index, body)


@router.post("/{volume_index}/{chapter_index}/compare-all")
def ai_compare_all(volume_index: int, chapter_index: int):
    """AI 全量对照所有章节。委托到 timeline_ai_service。"""
    from backend.services.timeline_ai_service import do_ai_compare_all
    return do_ai_compare_all(volume_index, chapter_index)


@router.post("/{volume_index}/{chapter_index}/fix-divergence")
def ai_fix_divergence(volume_index: int, chapter_index: int, body: DivergenceFixRequest):
    """AI 修复单个偏离。委托到 timeline_ai_service。"""
    from backend.services.timeline_ai_service import do_ai_fix_divergence
    return do_ai_fix_divergence(volume_index, chapter_index, body)


@router.post("/{volume_index}/{chapter_index}/fix-all-divergences")
def ai_fix_all_divergences(volume_index: int, chapter_index: int):
    """AI 修复全部偏离。委托到 timeline_ai_service。"""
    from backend.services.timeline_ai_service import do_ai_fix_all_divergences
    return do_ai_fix_all_divergences(volume_index, chapter_index)


@router.post("/{volume_index}/{chapter_index}/finalize")
def finalize_chapter(volume_index: int, chapter_index: int):
    """定稿章节。委托到 timeline_ai_service。"""
    from backend.services.timeline_ai_service import do_finalize_chapter
    return do_finalize_chapter(volume_index, chapter_index)
