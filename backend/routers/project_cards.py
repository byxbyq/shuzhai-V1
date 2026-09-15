# -*- coding: utf-8 -*-
import logging
from fastapi import APIRouter

from backend.services.project_service import state

logger = logging.getLogger(__name__)

"""灵感/构思卡片路由"""

from backend.routers.project_models import BrainstormCardsSave, PlanningCardsSave

router = APIRouter()

def get_brainstorm_cards():
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    cards = state.project.get_brainstorm_cards()
    graph = getattr(state.project, 'brainstorm_graph', None) or {}
    return {"ok": True, "cards": cards, "graph": graph}


@router.post("/brainstorm-cards")
def save_brainstorm_cards(data: BrainstormCardsSave):
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    if not isinstance(data.cards, list):
        return {"ok": False, "error": "cards 必须是数组"}
    state.project.set_brainstorm_cards(data.cards)
    if data.graph is not None:
        state.project.brainstorm_graph = data.graph
    state.project.save_all()
    return {"ok": True}


# ═══ 连线框画布（E模块）═══
@router.get("/planning-cards")
def get_planning_cards():
    """获取连线框画布数据"""
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    pc = state.project.get_planning_cards()
    return {"ok": True, "data": pc}


@router.post("/planning-cards")
def save_planning_cards(data: PlanningCardsSave):
    """保存连线框画布数据"""
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    payload = {
        "nodes": data.nodes if isinstance(data.nodes, list) else [],
        "edges": data.edges if isinstance(data.edges, list) else [],
        "meta": data.meta if isinstance(data.meta, dict) else {},
    }
    state.project.set_planning_cards(payload)
    return {"ok": True, "saved_at": payload["meta"].get("last_saved", "")}

