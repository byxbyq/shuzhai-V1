# -*- coding: utf-8 -*-
"""工作流路由 - /api/workflow"""
import os, json
import logging
from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.project_service import state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflow")

def _get_workflow_file():
    """获取当前项目的工作流状态文件路径"""
    if state and state.project:
        return os.path.join(state.project.project_dir, "workflow_state.json")
    # 没有打开的项目时用全局的（兼容老逻辑）
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "workflow_state.json")

class WorkflowState(BaseModel):
    currentStep: int = 1
    completedSteps: list = []
    stepStatus: dict = None

def _load_workflow():
    wf_file = _get_workflow_file()
    if os.path.exists(wf_file):
        try:
            with open(wf_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("加载工作流状态失败: %s", e)
    return {"currentStep": 1, "completedSteps": [], "stepStatus": {}}

def _save_workflow(wf_state):
    wf_file = _get_workflow_file()
    os.makedirs(os.path.dirname(wf_file), exist_ok=True)
    with open(wf_file, "w", encoding="utf-8") as f:
        json.dump(wf_state, f, ensure_ascii=False, indent=2)

@router.get("")
def get_workflow():
    return {"ok": True, "workflow": _load_workflow()}

@router.post("")
def save_workflow(data: WorkflowState):
    wf_state = {
        "currentStep": data.currentStep,
        "completedSteps": data.completedSteps,
        "stepStatus": data.stepStatus or {}
    }
    _save_workflow(wf_state)
    return {"ok": True}
