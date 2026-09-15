# -*- coding: utf-8 -*-
import logging
from fastapi import APIRouter

from backend.services.project_service import state, get_generator
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)

from ._models import CoverageRequest
from .outline import _get_effective_outline

router = APIRouter()

@router.post("/coverage-check")
def check_outline_coverage(req: CoverageRequest):
    """检测单章正文对大纲的覆盖率（纯评估，不触发续写）"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "no project")
    ch_idx = req.chapter_index
    chapters = state.project.chapters
    if ch_idx < 0 or ch_idx >= len(chapters):
        return err(ErrorCode.INTERNAL_ERROR, f"章节索引{ch_idx}超出范围（共{len(chapters)}章）")
    ch = chapters[ch_idx]
    content = state.project.get_content(ch_idx) or ""
    outline = _get_effective_outline(ch)
    if not outline:
        return err(ErrorCode.INTERNAL_ERROR, "该章节无大纲")
    if not content:
        return {**err(ErrorCode.CHAPTER_EMPTY, "该章节无正文"), "coverage_percent": 0}
    try:
        gen = get_generator()
        result = gen.evaluate_outline_coverage(content, outline)
        result["chapter_index"] = ch_idx
        result["chapter_title"] = ch.get("title", f"第{ch_idx+1}章")
        result["content_length"] = len(content)
        return result
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")

@router.post("/coverage-check-all")
def check_all_outline_coverage():
    """批量检测所有有正文+大纲的章节覆盖率"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "no project")
    chapters = state.project.chapters
    results = []
    try:
        gen = get_generator()
        for i, ch in enumerate(chapters):
            content = state.project.get_content(i) or ""
            outline = _get_effective_outline(ch)
            if not outline or not content:
                results.append({
                    "chapter_index": i,
                    "chapter_title": ch.get("title", f"第{i+1}章"),
                    "skipped": True,
                    "reason": "无大纲" if not outline else "无正文"
                })
                continue
            result = gen.evaluate_outline_coverage(content, outline)
            result["chapter_index"] = i
            result["chapter_title"] = ch.get("title", f"第{i+1}章")
            result["content_length"] = len(content)
            results.append(result)
        return {"ok": True, "results": results}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")
