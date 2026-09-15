# -*- coding: utf-8 -*-
"""
书斋 V66 - 导出/工具 Agent
处理导出、快照对比、拆书相关意图。
（分镜意图已移交 StoryboardAgent，SB-8）
"""

import logging

from backend.agents.base_agent import BaseAgent
from backend.agents.dispatcher import (
    _resolve_chapter_index,
    _api_get,
    _get_base_url,
)

logger = logging.getLogger(__name__)


class ExportAgent(BaseAgent):
    """处理导出/工具相关意图：
    - export_book: 导出书籍
    - snapshot_diff: 版本对比
    - deconstruct: 拆书
    """

    agent_id = "export"
    agent_name = "导出Agent"
    intent_keywords = [
        "export_book", "snapshot_diff",
        "deconstruct",
    ]

    def execute(self, params: dict, context: dict) -> dict:
        intent = params.get("_intent", "")
        self.log_event("export_action", {"intent": intent})

        if intent == "export_book":
            return self._export_book(params, context)
        elif intent == "snapshot_diff":
            return self._snapshot_diff(params, context)
        elif intent == "deconstruct":
            return self._deconstruct(params, context)
        else:
            return {"reply": "导出Agent: 未识别的子意图"}

    def _export_book(self, params: dict, context: dict) -> dict:
        """导出书籍"""
        fmt = params.get("format", "txt")
        if fmt not in ("txt", "epub", "pdf"):
            fmt = "txt"
        return {
            "reply": f"正在导出{fmt.upper()}格式，浏览器会自动开始下载。",
            "action": {"type": "export", "format": fmt},
        }

    def _snapshot_diff(self, params: dict, context: dict) -> dict:
        """版本对比"""
        idx = _resolve_chapter_index(params, context)
        try:
            snap_data = _api_get(_get_base_url() + f"/api/chapter/snapshots?index={idx}", timeout=10)
            if snap_data.get("ok"):
                snaps = snap_data.get("snapshots", [])
                if len(snaps) < 2:
                    return {"reply": f"第{idx+1}章只有{len(snaps)}个快照，需要至少2个才能对比。"}
                else:
                    return {
                        "reply": f"第{idx+1}章有{len(snaps)}个快照，最新两个：{snaps[-1].get('time','') if isinstance(snaps[-1],dict) else snaps[-1]} 和 {snaps[-2].get('time','') if isinstance(snaps[-2],dict) else snaps[-2]}",
                        "action": {"type": "open_snapshot_diff", "chapter_index": idx},
                    }
            else:
                return {"reply": f"获取快照失败：{snap_data.get('error', '')}"}
        except Exception as e:
            return {"reply": f"获取快照出错：{e}"}

    def _deconstruct(self, params: dict, context: dict) -> dict:
        """拆书学习"""
        return {
            "reply": "拆书学习需要在拆书页面操作。我来帮你打开。",
            "action": {"type": "open_deconstruct"},
        }
