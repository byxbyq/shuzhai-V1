# -*- coding: utf-8 -*-
"""chapter 子包"""
from fastapi import APIRouter

from .crud import router as crud_router
from .snapshots import router as snapshots_router
from .status import router as status_router
from .planning_check import router as planning_router, planning_router as plan_router, check_router

# Note: planning_check.py defines planning_router and check_router directly
# We re-expose them for backward compatibility

main_router = APIRouter(prefix="/api/chapter")
main_router.include_router(crud_router)
main_router.include_router(snapshots_router)
main_router.include_router(status_router)
main_router.include_router(planning_router)

router = main_router

# Re-export models
from ._utils import (
    ChapterAdd, ChapterDelete, ChapterRename, ContentSave,
    ChapterOutlineSave, SnapshotRestore, SnapshotDiff,
    _smart_truncate, _strip_edit_annotations, _update_writing_stats
)
