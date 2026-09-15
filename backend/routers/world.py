# -*- coding: utf-8 -*-
"""世界观+事实账本路由 - /api/world/* + /api/ledger/*"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

from backend.services.project_service import state, get_world, get_ledger
from backend.api_models import err, ErrorCode


# ═══════════════════════════════════════════════════════════════════
# Hyrum's Law 防护：显式声明可序列化的公共字段
# ═══════════════════════════════════════════════════════════════════

CHARACTER_PUBLIC_FIELDS = [
    "name", "location", "emotion", "health", "realm",
    "relationships", "possessions", "secrets_known",
    "last_seen_chapter", "is_alive", "arc_stage",
]

TIMELINE_PUBLIC_FIELDS = [
    "chapter", "event", "characters", "location",
    "time_marker", "importance",
]

HOOK_PUBLIC_FIELDS = [
    "id", "content", "planted_chapter", "planted_paragraph",
    "expected_recovery_chapter", "status", "related_characters",
    "related_items", "note", "arc_type", "strength", "hook_type",
]


def _public_dict(obj, fields: list) -> dict:
    """仅序列化白名单字段，防止内部字段泄露"""
    result = {}
    for k in fields:
        v = getattr(obj, k, None)
        if v is not None or k in ("is_alive", "importance", "strength"):
            result[k] = v
    return result


# ═══════════════════════════════════════════════════════════════════
# 世界观路由 - /api/world/*  (原 world_router.py)
# ═══════════════════════════════════════════════════════════════════
world_router = APIRouter(prefix="/api/world")

class ForceAdd(BaseModel):
    name: str
    territory: str = ""
    attitude: str = ""
    description: str = ""

class ForceUpdate(BaseModel):
    name: str = None
    territory: str = None
    attitude: str = None
    description: str = None

class ItemAdd(BaseModel):
    name: str
    nature: str = ""
    description: str = ""
    chapter: int = 0

class ItemUpdate(BaseModel):
    name: str = None
    nature: str = None
    description: str = None
    chapter: int = None
    status: str = None

class LocationAdd(BaseModel):
    name: str
    loc_type: str = ""
    description: str = ""
    chapter: int = 0

class LocationUpdate(BaseModel):
    name: str = None
    loc_type: str = None
    description: str = None
    chapter: int = None

class ConstraintAdd(BaseModel):
    rule: str

@world_router.get("/")
def get_world_api():
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    return {"ok": True, "world": {
        "magic_system": w.magic_system, "forces": w.forces,
        "locations": w.locations, "items": w.items,
        "hard_constraints": w.hard_constraints, "freeform": w.freeform,
    }, "prompt": w.to_prompt()}

@world_router.post("/force/add")
def add_force(data: ForceAdd):
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    w.add_force(data.name, data.territory, data.attitude, data.description)
    return {"ok": True}

@world_router.get("/force/{idx}")
def get_force(idx: int):
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    force = w.get_force(idx)
    if not force: return err(ErrorCode.NOT_FOUND, "势力不存在")
    return {"ok": True, "force": force}

@world_router.patch("/force/{idx}")
def update_force(idx: int, data: ForceUpdate):
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    updates = {k: v for k, v in data.dict().items() if v is not None}
    ok = w.update_force(idx, **updates)
    if not ok: return err(ErrorCode.NOT_FOUND, "势力不存在")
    return {"ok": True}

@world_router.delete("/force/{idx}")
def delete_force(idx: int):
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    ok = w.delete_force(idx)
    if not ok: return err(ErrorCode.NOT_FOUND, "势力不存在")
    return {"ok": True}

@world_router.post("/item/add")
def add_item(data: ItemAdd):
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    w.add_item(data.name, data.nature, data.description, data.chapter)
    return {"ok": True}

@world_router.get("/item/{idx}")
def get_item(idx: int):
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    item = w.get_item(idx)
    if not item: return err(ErrorCode.NOT_FOUND, "物品不存在")
    return {"ok": True, "item": item}

@world_router.patch("/item/{idx}")
def update_item(idx: int, data: ItemUpdate):
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    updates = {}
    for k, v in data.dict().items():
        if v is not None:
            if k == "chapter":
                updates["first_seen_chapter"] = v
            else:
                updates[k] = v
    ok = w.update_item(idx, **updates)
    if not ok: return err(ErrorCode.NOT_FOUND, "物品不存在")
    return {"ok": True}

@world_router.delete("/item/{idx}")
def delete_item(idx: int):
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    ok = w.delete_item(idx)
    if not ok: return err(ErrorCode.NOT_FOUND, "物品不存在")
    return {"ok": True}

@world_router.post("/location/add")
def add_location(data: LocationAdd):
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    w.add_location(data.name, data.loc_type, data.description, data.chapter)
    return {"ok": True}

@world_router.get("/location/{idx}")
def get_location(idx: int):
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    loc = w.get_location(idx)
    if not loc: return err(ErrorCode.NOT_FOUND, "地点不存在")
    return {"ok": True, "location": loc}

@world_router.patch("/location/{idx}")
def update_location(idx: int, data: LocationUpdate):
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    updates = {}
    for k, v in data.dict().items():
        if v is not None:
            if k == "loc_type":
                updates["type"] = v
            elif k == "chapter":
                updates["first_seen_chapter"] = v
            else:
                updates[k] = v
    ok = w.update_location(idx, **updates)
    if not ok: return err(ErrorCode.NOT_FOUND, "地点不存在")
    return {"ok": True}

@world_router.delete("/location/{idx}")
def delete_location(idx: int):
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    ok = w.delete_location(idx)
    if not ok: return err(ErrorCode.NOT_FOUND, "地点不存在")
    return {"ok": True}

@world_router.post("/constraint/add")
def add_constraint(data: ConstraintAdd):
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    w.add_constraint(data.rule)
    return {"ok": True}

@world_router.get("/stats")
def world_stats():
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    return {"ok": True, "stats": w.get_stats()}


# ═══════════════════════════════════════════════════════════════════
# 故事圣经钉选 - /api/world/pin/*  （第5批）
# ═══════════════════════════════════════════════════════════════════
class PinAdd(BaseModel):
    text: str
    source: str = ""

class PinAction(BaseModel):
    pin_id: str

@world_router.get("/pin/list")
def world_pin_list():
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    return {"ok": True, "pinned": w.list_pinned()}

@world_router.post("/pin/add")
def world_pin_add(data: PinAdd):
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    if not data.text.strip():
        return err(ErrorCode.VALIDATION_ERROR, "钉选内容不能为空")
    entry = w.pin(data.text.strip(), data.source)
    return {"ok": True, "entry": entry}

@world_router.post("/pin/remove")
def world_pin_remove(data: PinAction):
    w = get_world()
    if not w: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    if w.unpin(data.pin_id):
        return {"ok": True}
    return err(ErrorCode.NOT_FOUND, "钉选项不存在")


# ═══════════════════════════════════════════════════════════════════
# 事实账本路由 - /api/ledger/*  (原 ledger.py)
# ═══════════════════════════════════════════════════════════════════
ledger_router = APIRouter(prefix="/api/ledger")

class CharacterUpdate(BaseModel):
    name: str
    fields: dict

class HookAdd(BaseModel):
    content: str
    planted_chapter: int
    expected_recovery_chapter: int = 0
    related_characters: List[str] = []
    related_items: List[str] = []
    arc_type: str = ""             # short(2-3章) / medium(5-8章) / long(全书)
    strength: int = 2              # 1-5
    hook_type: str = ""            # 13式之一

class HookAction(BaseModel):
    hook_id: str
    reason: str = ""

@ledger_router.get("/stats")
def ledger_stats():
    l = get_ledger()
    if not l: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    return {"ok": True, "stats": l.get_stats()}

@ledger_router.get("/characters")
def ledger_characters():
    l = get_ledger()
    if not l: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    return {"ok": True, "characters": {k: _public_dict(v, CHARACTER_PUBLIC_FIELDS) for k, v in l.character_states.items()}}

@ledger_router.post("/character/update")
def ledger_character_update(data: CharacterUpdate):
    l = get_ledger()
    if not l: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    l.update_character(data.name, **data.fields)
    return {"ok": True}

@ledger_router.get("/timeline")
def ledger_timeline(chapter: int = None):
    l = get_ledger()
    if not l: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    # 返回结构化数组（前端 state.timeline 期望数组格式）
    events = l.timeline
    if chapter is not None:
        events = [e for e in events if e.chapter == chapter]
    return {"ok": True, "timeline": [_public_dict(e, TIMELINE_PUBLIC_FIELDS) for e in events]}

@ledger_router.get("/hooks")
def ledger_hooks():
    l = get_ledger()
    if not l: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    active = [_public_dict(h, HOOK_PUBLIC_FIELDS) for h in l.get_pending_hooks()]
    recovered = [_public_dict(h, HOOK_PUBLIC_FIELDS) for h in l.foreshadowing if h.status == "recovered"]
    abandoned = [_public_dict(h, HOOK_PUBLIC_FIELDS) for h in l.foreshadowing if h.status == "abandoned"]
    return {"ok": True, "active": active, "recovered": recovered, "abandoned": abandoned}

@ledger_router.post("/hook/add")
def ledger_hook_add(data: HookAdd):
    l = get_ledger()
    if not l: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    hid = l.add_hook(data.content, data.planted_chapter,
                     expected_recovery_chapter=data.expected_recovery_chapter,
                     related_characters=data.related_characters,
                     related_items=data.related_items)
    return {"ok": True, "hook_id": hid}

@ledger_router.post("/hook/recover")
def ledger_hook_recover(data: HookAction):
    l = get_ledger()
    if not l: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    return {"ok": l.recover_hook(data.hook_id, state.project.meta.get("current_chapter", 0) + 1 if state.project else 1)}

@ledger_router.post("/hook/activate")
def ledger_hook_activate(data: HookAction):
    l = get_ledger()
    if not l: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    return {"ok": l.activate_hook(data.hook_id)}

@ledger_router.post("/hook/abandon")
def ledger_hook_abandon(data: HookAction):
    l = get_ledger()
    if not l: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    return {"ok": l.abandon_hook(data.hook_id, data.reason)}

@ledger_router.get("/read-pull")
def ledger_read_pull(current_chapter: int = 0):
    """追读力评分 -- 量化读者继续阅读的动力"""
    l = get_ledger()
    if not l: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    if current_chapter == 0 and state.project:
        current_chapter = state.project.meta.get("current_chapter", 0) + 1
    result = l.get_read_pull(current_chapter)
    return {"ok": True, **result}


@ledger_router.get("/strand-stats")
def ledger_strand_stats(current_chapter: int = 0):
    """Strand Weave节奏分布 -- 三线比例监控+红线规则检查"""
    l = get_ledger()
    if not l: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    if current_chapter == 0 and state.project:
        current_chapter = state.project.meta.get("current_chapter", 0) + 1
    result = l.get_strand_stats(current_chapter)
    return {"ok": True, **result}
