# -*- coding: utf-8 -*-
import logging
from fastapi import APIRouter

from backend.services.project_service import state, get_world

logger = logging.getLogger(__name__)

"""章节大纲/设定路由"""

from backend.routers.project_models import OutlineSave, NovelOutlineSave, SettingsUpdate

router = APIRouter()

@router.get("/outline")
def get_outline():
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    text = state.project.get_outline_text()
    return {"ok": True, "outline": text, "length": len(text)}

@router.post("/outline")
def save_outline(data: OutlineSave):
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    state.project.save_outline_text(data.outline)
    return {"ok": True}

@router.get("/settings")
def get_settings():
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    w = get_world()
    # world_settings优先从world_meta.json读取，fallback到project.json
    ws_from_meta = {}
    if w:
        if hasattr(w, 'freeform') and w.freeform:
            ws_from_meta.update(w.freeform)
        if hasattr(w, 'world_settings') and w.world_settings:
            ws_from_meta.update(w.world_settings)
    # project.json的world_settings作为fallback
    final_ws = ws_from_meta if ws_from_meta else (state.project.world_settings or {})
    return {
        "ok": True,
        "world_settings": final_ws,
        "character_settings": state.project.character_settings,
        "characters": getattr(state.project, 'characters', []),
        "narrative_style": w.narrative_style if w else {},
        "era": w.era if w else {},
        "world_rules": w.world_rules if w else [],
        "structured_settings": {
            "magic_system": w.magic_system,
            "forces": w.forces,
            "locations": w.locations,
            "items": w.items,
            "constraints": w.hard_constraints,
            "freeform": w.freeform,
            "narrative_style": w.narrative_style,
            "era": w.era,
            "world_rules": w.world_rules,
        } if w else {},
    }

@router.post("/settings")
def update_settings(data: SettingsUpdate):
    if not state.project: return {"ok": False}
    if data.world_settings is not None:
        state.project.world_settings = data.world_settings
    if data.character_settings is not None:
        state.project.character_settings = data.character_settings
    if data.characters is not None:
        state.project.characters = data.characters
    # 结构化世界观字段写入 world_meta.json
    w = get_world()
    if w:
        changed = False
        if data.narrative_style is not None:
            for k, v in data.narrative_style.items():
                w.narrative_style[k] = (v or '').strip() if v else ''
            changed = True
        if data.era is not None:
            for k, v in data.era.items():
                w.era[k] = (v or '').strip() if v else ''
            changed = True
        if data.world_rules is not None and len(data.world_rules) > 0:
            w.world_rules = data.world_rules
            changed = True
        if data.world_settings is not None:
            w.world_settings = data.world_settings
            changed = True
        if changed:
            w.save()
    state.project._save_meta()
    return {"ok": True}
# Novel Outline
# ── Novel Outline (structured) ──

@router.get("/novel-outline")
def get_novel_outline():
    """获取结构化全书大纲"""
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    outline = state.project.get_novel_outline()
    return {"ok": True, "novel_outline": outline}

@router.post("/novel-outline")
def save_novel_outline(data: NovelOutlineSave):
    """保存结构化全书大纲（dict格式）"""
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    if not isinstance(data.novel_outline, dict):
        return {"ok": False, "error": "novel_outline 必须是对象（dict）"}
    state.project.set_novel_outline(data.novel_outline)
    state.project.save_all()
    return {"ok": True}


@router.put("/novel-outline")
def put_novel_outline(data: NovelOutlineSave):
    """PUT 方式保存（用于迁移脚本）"""
    return save_novel_outline(data)
