# -*- coding: utf-8 -*-
import logging
from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.preference_service import _load_prefs, _save_prefs, get_pref_guide

logger = logging.getLogger(__name__)

preference_router = APIRouter(prefix="/api/preference")

class PrefUpdate(BaseModel):
    category: str  # style_preferences / plot_preferences / character_preferences / pacing_preferences
    key: str
    value: str
    action: str = "set"  # set / append / remove

class TabooUpdate(BaseModel):
    content: str
    action: str = "add"  # add / remove

class PatternUpdate(BaseModel):
    content: str
    pattern_type: str = "liked"  # liked / disliked
    action: str = "add"  # add / remove

@preference_router.get("/")
def get_prefs():
    """获取全部偏好记忆"""
    return {"ok": True, "preferences": _load_prefs()}

@preference_router.post("/update")
def update_pref(data: PrefUpdate):
    """更新偏好项"""
    prefs = _load_prefs()
    cat = data.category
    if cat not in prefs:
        prefs[cat] = {}
    if data.action == "set":
        prefs[cat][data.key] = data.value
    elif data.action == "append":
        if not isinstance(prefs[cat].get(data.key), list):
            prefs[cat][data.key] = []
        prefs[cat][data.key].append(data.value)
    elif data.action == "remove":
        if data.key in prefs[cat]:
            if isinstance(prefs[cat][data.key], list):
                if data.value in prefs[cat][data.key]:
                    prefs[cat][data.key].remove(data.value)
            else:
                del prefs[cat][data.key]
    _save_prefs(prefs)
    return {"ok": True, "preferences": prefs}

@preference_router.post("/taboo")
def update_taboo(data: TabooUpdate):
    """添加/移除禁忌词"""
    prefs = _load_prefs()
    if data.action == "add" and data.content not in prefs["taboos"]:
        prefs["taboos"].append(data.content)
    elif data.action == "remove" and data.content in prefs["taboos"]:
        prefs["taboos"].remove(data.content)
    _save_prefs(prefs)
    return {"ok": True, "taboos": prefs["taboos"]}

@preference_router.post("/pattern")
def update_pattern(data: PatternUpdate):
    """记录喜欢/不喜欢的模式"""
    prefs = _load_prefs()
    key = f"{data.pattern_type}_patterns"
    if data.action == "add" and data.content not in prefs[key]:
        prefs[key].append(data.content)
    elif data.action == "remove" and data.content in prefs[key]:
        prefs[key].remove(data.content)
    _save_prefs(prefs)
    return {"ok": True, key: prefs[key]}

@preference_router.get("/guide")
def get_pref_guide_endpoint():
    """生成偏好指南文本（用于注入生成prompt）"""
    return get_pref_guide()


# ═══════════════════════════════════════════════════════════════════
# 大纲模板路由 - /api/templates/*  (原 templates.py)
# ═══════════════════════════════════════════════════════════════════
