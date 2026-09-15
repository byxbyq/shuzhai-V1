# -*- coding: utf-8 -*-
"""State Memory 蒸馏摘要路由"""
import logging
from fastapi import APIRouter

from backend.services.project_service import state

logger = logging.getLogger(__name__)

router = APIRouter()

# ═══════════════════════════════════════════════════════════════════
# state_memory 蒸馏摘要路由
# ═══════════════════════════════════════════════════════════════════

@router.get("/state-memory")
def state_memory(before_chapter: int = 999):
    """读取 state_memory/ 目录下所有 chapter_index < before_chapter 的蒸馏摘要，
    按章节序号拼接返回，供 buildMemoryContext 使用。
    """
    import os
    import json

    if not state.project:
        return {"ok": False, "error": "没有打开的项目", "text": ""}

    mem_dir = os.path.join(state.project.project_dir, "state_memory")
    if not os.path.exists(mem_dir):
        return {"ok": True, "text": "", "chapters": []}

    index_path = os.path.join(mem_dir, "_index.json")
    if not os.path.exists(index_path):
        return {"ok": True, "text": "", "chapters": []}

    with open(index_path, "r", encoding="utf-8") as f:
        index_data = json.load(f)

    parts = []
    chapters = []

    for entry in index_data:
        ci = entry.get("chapter_index", 0)
        if ci >= before_chapter:
            continue

        file_name = entry.get("file", f"{ci:03d}.json")
        file_path = os.path.join(mem_dir, file_name)
        if not os.path.exists(file_path):
            continue

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        chapters.append(ci)

        # 构造该章的摘要文本
        lines = [f"【第{ci}章摘要】"]

        chars = data.get("characters", [])
        if chars:
            char_lines = []
            for c in chars:
                name = c.get("name", "?")
                bits = []
                if c.get("location"):
                    bits.append("位置:" + c["location"])
                if c.get("mood"):
                    bits.append("心绪:" + c["mood"])
                if c.get("realm"):
                    bits.append("境界:" + c["realm"])
                if c.get("items"):
                    bits.append("持有:" + ",".join(c["items"]))
                if c.get("alive") is False:
                    bits.append("已死亡")
                char_lines.append(name + (" (" + " | ".join(bits) + ")" if bits else ""))
            lines.append("角色: " + "; ".join(char_lines))

        events = data.get("events", [])
        if events:
            lines.append("事件: " + " | ".join(events))

        fs = data.get("foreshadowing", {})
        if fs:
            planted = fs.get("planted", [])
            resolved = fs.get("resolved", [])
            if planted:
                lines.append("新伏笔: " + "; ".join(
                    p.get("content", "?") + ("(预计第" + str(p.get("expected_chapter", "?")) + "章)" if p.get("expected_chapter") else "")
                    for p in planted
                ))
            if resolved:
                lines.append("回收伏笔: " + "; ".join(
                    r.get("content", "?") + "(" + r.get("method", "?") + ")"
                    for r in resolved
                ))

        settings = data.get("new_settings", [])
        if settings:
            lines.append("新设定: " + "; ".join(settings))

        bridge = data.get("bridge", {})
        if bridge.get("from_prev"):
            lines.append("承接: " + bridge["from_prev"])
        if bridge.get("to_next"):
            lines.append("遗留: " + bridge["to_next"])

        parts.append("\n".join(lines))

    text = "\n\n".join(parts)
    return {"ok": True, "text": text, "chapters": chapters}
