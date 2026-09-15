# -*- coding: utf-8 -*-
import logging
from fastapi import APIRouter, Depends

from backend.services.project_service import state, get_ledger
from backend.api_models import paginated, PaginationParams

logger = logging.getLogger(__name__)

"""伏笔全生命周期管理"""

from backend.routers.project_models import HookAdd, HookAdvance, HookRecover, HookAbandon

router = APIRouter()

# ============================================================
# 伏笔全生命周期管理
# ============================================================
@router.post("/hooks/add")
def add_hook(data: HookAdd):
    if not state.project: return {"ok": False, "error": "no project"}
    # 伏笔对话框传 planted_chapter（1-based章号），右侧面板传 chapter_index，前者优先
    planted = data.planted_chapter if data.planted_chapter else data.chapter_index
    hook = state.project.add_hook(data.content, planted, data.status)
    if not hook or not hook.get("id"): return {"ok": False, "error": "伏笔写入失败"}
    deadline = data.deadline_chapter or data.expected_recovery_chapter
    if deadline or data.expected_recovery_chapter or data.note:
        ledger = get_ledger()
        if ledger:
            for h in ledger.foreshadowing:
                if h.id == hook["id"]:
                    if deadline:
                        h.deadline_chapter = deadline
                    if data.expected_recovery_chapter:
                        h.expected_recovery_chapter = data.expected_recovery_chapter
                    if data.note:
                        h.note = data.note
                    break
            ledger.save()
    return {"ok": True, "hook": hook}

@router.get("/hooks")
def list_hooks(current_chapter: int = 0, pagination: PaginationParams = Depends()):
    if not state.project: return {"ok": False, "error": "no project"}
    overdue = state.project.check_overdue_hooks(current_chapter)
    hooks = state.project.get_hooks()
    total = len(hooks)
    start = (pagination.page - 1) * pagination.page_size
    end = start + pagination.page_size
    return {
        **paginated(hooks[start:end], pagination.page, pagination.page_size, total),
        # 前端 loadForeshadows/loadHooksPanel/LocalDB 均读 hooks 键，必须同时返回（paginated 只有 data）
        "hooks": hooks,
        "overdue": overdue,
    }

@router.post("/hooks/advance")
def advance_hook(data: HookAdvance):
    if not state.project: return {"ok": False, "error": "no project"}
    state.project.advance_hook(data.id, data.chapter_index)
    return {"ok": True}

@router.post("/hooks/recover")
def recover_hook(data: HookRecover):
    if not state.project: return {"ok": False, "error": "no project"}
    state.project.recover_hook(data.id, data.chapter_index)
    return {"ok": True}

@router.post("/hooks/abandon")
def abandon_hook(data: HookAbandon):
    if not state.project: return {"ok": False, "error": "no project"}
    ledger = get_ledger()
    if ledger:
        ledger.abandon_hook(data.id, data.reason or "")
    # 原实现无 return，FastAPI 返回 null 导致前端 d.ok 永远为假、面板不刷新
    return {"ok": True}
