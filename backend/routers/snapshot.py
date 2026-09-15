# -*- coding: utf-8 -*-
"""叙事状态快照路由 — /api/snapshot/*"""
from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.project_service import state, get_ledger
from backend.api_models import err, ErrorCode

router = APIRouter(prefix="/api/snapshot", tags=["snapshot"])


class RestoreRequest(BaseModel):
    snapshot_id: str = ""
    file: str = ""


@router.post("/take")
async def take_snapshot():
    """创建当前叙事状态快照"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    ledger = get_ledger()
    if not ledger:
        return err(ErrorCode.PROJECT_NOT_OPEN, "真相账本未初始化")
    chapter_idx = max((c.get("index", 0) for c in state.project.chapters), default=0)
    snapshot = ledger.take_snapshot(chapter_idx)
    return {"ok": True, "data": snapshot}


@router.get("/list")
async def list_snapshots():
    """列出所有快照"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    ledger = get_ledger()
    if not ledger:
        return err(ErrorCode.PROJECT_NOT_OPEN, "真相账本未初始化")
    return {"ok": True, "data": ledger.list_snapshots()}


@router.post("/restore")
async def restore_snapshot(data: RestoreRequest):
    """从快照恢复 ledger 数据"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    ledger = get_ledger()
    if not ledger:
        return err(ErrorCode.PROJECT_NOT_OPEN, "真相账本未初始化")
    identifier = data.snapshot_id or data.file
    if not identifier:
        return err(ErrorCode.VALIDATION_ERROR, "需提供 snapshot_id 或 file")
    ok = ledger.restore_snapshot(identifier)
    return {"ok": ok, "data": {"restored": ok}}
