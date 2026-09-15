# -*- coding: utf-8 -*-
"""偏好服务 - 提供用户写作偏好的读取和格式化，供多个router复用"""

import os
import json

from backend.services.project_service import state

PREF_FILE = "user_preferences.json"


def _pref_path() -> str:
    if not state.project:
        return ""
    return os.path.join(state.project.project_dir, PREF_FILE)


def _load_prefs() -> dict:
    path = _pref_path()
    if not path or not os.path.exists(path):
        return {
            "style_preferences": {},
            "plot_preferences": {},
            "character_preferences": {},
            "pacing_preferences": {},
            "taboos": [],
            "liked_patterns": [],
            "disliked_patterns": [],
            "revision_history": [],
        }
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_prefs(prefs: dict):
    path = _pref_path()
    if not path:
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)


def get_pref_guide() -> dict:
    """生成偏好指南文本（用于注入生成prompt）"""
    prefs = _load_prefs()
    lines = ["## 用户偏好指南"]
    if prefs.get("style_preferences"):
        lines.append("### 风格偏好")
        for k, v in prefs["style_preferences"].items():
            lines.append(f"- {k}: {v}")
    if prefs.get("plot_preferences"):
        lines.append("### 剧情偏好")
        for k, v in prefs["plot_preferences"].items():
            lines.append(f"- {k}: {v}")
    if prefs.get("pacing_preferences"):
        lines.append("### 节奏偏好")
        for k, v in prefs["pacing_preferences"].items():
            lines.append(f"- {k}: {v}")
    if prefs.get("taboos"):
        lines.append("### 禁忌词/元素")
        for t in prefs["taboos"]:
            lines.append(f"- 禁用: {t}")
    if prefs.get("liked_patterns"):
        lines.append("### 用户喜欢的模式")
        for p in prefs["liked_patterns"]:
            lines.append(f"- {p}")
    if prefs.get("disliked_patterns"):
        lines.append("### 用户不喜欢的模式")
        for p in prefs["disliked_patterns"]:
            lines.append(f"- 避免: {p}")
    if len(lines) == 1:
        return {"ok": True, "guide": "", "empty": True}
    return {"ok": True, "guide": "\n".join(lines), "empty": False}
