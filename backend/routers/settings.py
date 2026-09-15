# -*- coding: utf-8 -*-
"""结构化设定库路由 — /api/settings/*
提供道具/功法（Artifacts）和势力/组织（Factions）的 CRUD 接口
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

from backend.services.project_service import get_ledger
from backend.api_models import err, ErrorCode

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ArtifactPayload(BaseModel):
    artifact_id: str
    name: str
    type: str = ""
    grade: str = ""
    owner: str = ""
    description: str = ""
    destroyed: bool = False


class FactionPayload(BaseModel):
    faction_id: str
    name: str
    type: str = ""
    leader: str = ""
    members: List[str] = []
    description: str = ""
    status: str = "active"


# ── Artifacts ──

@router.get("/artifacts")
async def list_artifacts():
    """列出所有道具/功法"""
    ledger = get_ledger()
    if not ledger:
        return err(ErrorCode.PROJECT_NOT_OPEN, "项目未打开")
    return {"ok": True, "data": ledger.get_all_artifacts()}


@router.post("/artifacts")
async def upsert_artifact(payload: ArtifactPayload):
    """新增或更新道具/功法"""
    ledger = get_ledger()
    if not ledger:
        return err(ErrorCode.PROJECT_NOT_OPEN, "项目未打开")
    ledger.add_artifact(
        payload.artifact_id,
        payload.name,
        type=payload.type,
        grade=payload.grade,
        owner=payload.owner,
        description=payload.description,
        destroyed=payload.destroyed,
    )
    return {"ok": True, "data": {"id": payload.artifact_id}}


# ── Factions ──

@router.get("/factions")
async def list_factions():
    """列出所有势力/组织"""
    ledger = get_ledger()
    if not ledger:
        return err(ErrorCode.PROJECT_NOT_OPEN, "项目未打开")
    return {"ok": True, "data": ledger.get_all_factions()}


@router.post("/factions")
async def upsert_faction(payload: FactionPayload):
    """新增或更新势力/组织"""
    ledger = get_ledger()
    if not ledger:
        return err(ErrorCode.PROJECT_NOT_OPEN, "项目未打开")
    ledger.add_faction(
        payload.faction_id,
        payload.name,
        type=payload.type,
        leader=payload.leader,
        members=payload.members,
        description=payload.description,
        status=payload.status,
    )
    return {"ok": True, "data": {"id": payload.faction_id}}
