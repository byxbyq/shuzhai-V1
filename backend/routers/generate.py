# -*- coding: utf-8 -*-
"""生成路由 - /api/generate/*   (薄转发层)

所有端点已拆分到 routers/generate/ 子包，此文件保留向后兼容。
"""
from .generate import router

# Re-export models
from .generate._models import (
    OutlineRequest, ChapterOutlineRequest, InspirationToBlueprintRequest,
    InspirationToNovelOutlineRequest, VolumeOutlineRequest, CancelGenerateRequest,
    ExtractStateRequest, NextChapterOutlineRequest, GenerateRequest,
    ConfirmRequest, CoverageRequest
)

# Re-export helpers
from .generate.outline import _get_effective_outline
from .generate.batch import _task_manager

__all__ = [
    "router",
    "OutlineRequest", "ChapterOutlineRequest", "InspirationToBlueprintRequest",
    "InspirationToNovelOutlineRequest", "VolumeOutlineRequest", "CancelGenerateRequest",
    "ExtractStateRequest", "NextChapterOutlineRequest", "GenerateRequest",
    "ConfirmRequest", "CoverageRequest",
    "_get_effective_outline", "_task_manager",
]
