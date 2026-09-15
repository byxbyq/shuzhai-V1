# -*- coding: utf-8 -*-
"""
书斋 V66 - 云同步 Agent
处理云同步相关意图。
"""

import logging

from backend.agents.base_agent import BaseAgent
from backend.agents.dispatcher import (
    _api_get,
    _api_post,
    _get_base_url,
)

logger = logging.getLogger(__name__)


class SyncAgent(BaseAgent):
    """处理云同步相关意图：
    - sync_push: 云同步上传
    - sync_pull: 云同步拉取
    - sync_config: 配置云同步
    """

    agent_id = "sync"
    agent_name = "同步Agent"
    intent_keywords = ["sync_push", "sync_pull", "sync_config"]

    def execute(self, params: dict, context: dict) -> dict:
        intent = params.get("_intent", "")
        self.log_event("sync_action", {"intent": intent})

        if intent == "sync_push":
            return self._sync_push(params, context)
        elif intent == "sync_pull":
            return self._sync_pull(params, context)
        elif intent == "sync_config":
            return self._sync_config(params, context)
        else:
            return {"reply": "同步Agent: 未识别的子意图"}

    def _sync_push(self, params: dict, context: dict) -> dict:
        """云同步上传"""
        try:
            cfg_data = _api_get(_get_base_url() + "/api/sync/config", timeout=10)
            if not cfg_data.get("config", {}).get("webdav_url"):
                return {
                    "reply": "还未配置WebDAV同步地址。请先说「配置云同步」。",
                    "action": {"type": "open_sync"},
                }
            cfg = cfg_data["config"]
            sdata = _api_post(_get_base_url() + "/api/sync/push", cfg, timeout=120)
            return {"reply": f"{sdata.get('message', '上传成功')}" if sdata.get("ok") else f"上传失败：{sdata.get('error', '')}"}
        except Exception as e:
            return {"reply": f"云同步上传出错：{e}"}

    def _sync_pull(self, params: dict, context: dict) -> dict:
        """云同步拉取"""
        return {
            "reply": "云同步拉取会覆盖当前项目，建议在云同步面板手动操作。",
            "action": {"type": "open_sync"},
        }

    def _sync_config(self, params: dict, context: dict) -> dict:
        """配置云同步"""
        return {
            "reply": "我来打开云同步配置面板。",
            "action": {"type": "open_sync"},
        }
