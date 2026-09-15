# -*- coding: utf-8 -*-
import logging
from fastapi import APIRouter

from backend.services.project_service import state

logger = logging.getLogger(__name__)

"""实体改名"""

from backend.routers.project_models import RenameEntity

router = APIRouter()


@router.post("/rename-entity")
def rename_entity(data: RenameEntity):
    """全书实体批量改名 — 跨章节正文/大纲/设定/人物/伏笔"""
    if not state.project:
        return {"ok": False, "error": "没有打开的项目"}
    if not data.old_name or not data.new_name:
        return {"ok": False, "error": "缺少old_name或new_name"}

    changes = {"characters": 0, "world_settings": 0, "outline": 0, "content": 0, "hooks": 0}

    # 1. 人物档案改名
    if data.scope in ("all", "characters"):
        chars = getattr(state.project, 'characters', [])
        for c in chars:
            if isinstance(c, dict):
                if c.get('name') == data.old_name:
                    c['name'] = data.new_name
                    changes['characters'] += 1
                # 在人物描述中替换
                for k, v in c.items():
                    if isinstance(v, str) and data.old_name in v:
                        c[k] = v.replace(data.old_name, data.new_name)
                        changes['characters'] += 1
        char_settings = getattr(state.project, 'character_settings', {})
        if isinstance(char_settings, dict):
            if data.old_name in char_settings:
                char_settings[data.new_name] = char_settings.pop(data.old_name)
                changes['characters'] += 1
            for name, info in char_settings.items():
                if isinstance(info, dict):
                    for k, v in info.items():
                        if isinstance(v, str) and data.old_name in v:
                            info[k] = v.replace(data.old_name, data.new_name)

    # 2. 世界观设定改名
    if data.scope in ("all", "world_settings"):
        ws = getattr(state.project, 'world_settings', {})
        if isinstance(ws, dict):
            for k, v in list(ws.items()):
                if isinstance(v, str) and data.old_name in v:
                    ws[k] = v.replace(data.old_name, data.new_name)
                    changes['world_settings'] += 1
                elif isinstance(v, dict):
                    for k2, v2 in v.items():
                        if isinstance(v2, str) and data.old_name in v2:
                            v[k2] = v2.replace(data.old_name, data.new_name)
                            changes['world_settings'] += 1

    # 3. 大纲改名
    if data.scope in ("all", "outline"):
        outline = getattr(state.project, 'novel_outline', {})
        # 新格式：dict
        if isinstance(outline, dict):
            for k, v in list(outline.items()):
                if isinstance(v, str) and data.old_name in v:
                    outline[k] = v.replace(data.old_name, data.new_name)
                    changes['outline'] += 1
                elif isinstance(v, list):
                    for i, item in enumerate(v):
                        if isinstance(item, str) and data.old_name in item:
                            v[i] = item.replace(data.old_name, data.new_name)
                            changes['outline'] += 1
                        elif isinstance(item, dict):
                            for k2, v2 in list(item.items()):
                                if isinstance(v2, str) and data.old_name in v2:
                                    item[k2] = v2.replace(data.old_name, data.new_name)
                                    changes['outline'] += 1
        # 兼容旧格式：list
        elif isinstance(outline, list):
            for act in outline:
                if isinstance(act, dict):
                    for k, v in act.items():
                        if isinstance(v, str) and data.old_name in v:
                            act[k] = v.replace(data.old_name, data.new_name)
                            changes['outline'] += 1
        # 章节大纲
        chapters = getattr(state.project, 'chapters', [])
        for ch in chapters:
            if isinstance(ch, dict):
                outline_text = ch.get('outline', '')
                if outline_text and data.old_name in outline_text:
                    ch['outline'] = outline_text.replace(data.old_name, data.new_name)
                    changes['outline'] += 1

    # 4. 正文改名
    if data.scope in ("all", "content"):
        chapters = getattr(state.project, 'chapters', [])
        for i, ch in enumerate(chapters):
            try:
                content = state.project.get_content(i)
                if content and data.old_name in content:
                    new_content = content.replace(data.old_name, data.new_name)
                    state.project.set_content(new_content, i)
                    changes['content'] += 1
            except Exception:
                pass

    # 5. 伏笔改名
    if data.scope in ("all", "hooks"):
        from backend.services.project_service import get_ledger
        ledger = get_ledger()
        if ledger:
            for hook in ledger.foreshadowing:
                if data.old_name in hook.content:
                    hook.content = hook.content.replace(data.old_name, data.new_name)
                    changes['hooks'] += 1
                if data.old_name in hook.related_characters:
                    hook.related_characters = [data.new_name if c == data.old_name else c for c in hook.related_characters]

    state.project.save_all()
    total = sum(changes.values())
    return {"ok": True, "changes": changes, "total_changes": total}

