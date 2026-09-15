# -*- coding: utf-8 -*-
"""章节服务 - 提供章节相关的业务逻辑，供多个router复用"""

from backend.services.project_service import state


def save_chapter_outline(data: dict) -> dict:
    """保存章节大纲文本、blueprint和锁定状态到项目数据"""
    if not state.project:
        return {"ok": False, "error": "no project"}
    try:
        idx = data.get("index", -1)
        outline_text = data.get("outline", "")
        blueprint = data.get("blueprint")
        if idx >= 0 and idx < len(state.project.chapters):
            if outline_text:
                state.project.chapters[idx]["outline"] = outline_text
            if blueprint:
                state.project.chapters[idx]["blueprint"] = blueprint
            # 章节定稿锁定状态
            if "locked" in data:
                state.project.chapters[idx]["locked"] = bool(data["locked"])
            state.project.save_all()
            return {"ok": True}
        return {"ok": False, "error": "invalid chapter index"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
