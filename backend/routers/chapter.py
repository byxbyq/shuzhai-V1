# -*- coding: utf-8 -*-
"""章节路由 - /api/chapter/*   (薄转发层)

所有端点已拆分到 routers/chapter/ 子包，此文件保留向后兼容。
"""
from .chapter import main_router as router
from .chapter.planning_check import planning_router, check_router

# Re-export models
from .chapter._utils import (
    ChapterAdd, ChapterDelete, ChapterRename, ContentSave,
    ChapterOutlineSave, SnapshotRestore, SnapshotDiff,
    _smart_truncate, _strip_edit_annotations, _update_writing_stats
)

__all__ = [
    "router", "planning_router", "check_router",
    "ChapterAdd", "ChapterDelete", "ChapterRename", "ContentSave",
    "ChapterOutlineSave", "SnapshotRestore", "SnapshotDiff",
    "_smart_truncate", "_strip_edit_annotations", "_update_writing_stats",
]
