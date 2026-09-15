# -*- coding: utf-8 -*-
"""
书斋 V66 - 编辑 Agent
处理全文查找替换意图（选段修复由 dispatcher.execute_edit_selection 直接调用）。
"""

import re, logging

from backend.agents.base_agent import BaseAgent
from backend.agents.dispatcher import (
    _FIND_REPLACE_PATTERNS,
)
from backend.services.project_service import state

logger = logging.getLogger(__name__)


class EditAgent(BaseAgent):
    """处理编辑相关意图：
    - find_replace: 全文查找替换
    """

    agent_id = "edit"
    agent_name = "编辑Agent"
    intent_keywords = ["find_replace"]

    def execute(self, params: dict, context: dict) -> dict:
        intent = params.get("_intent", "")
        self.log_event("edit_action", {"intent": intent})

        if intent == "find_replace":
            return self._find_replace(params, context)
        else:
            return {"reply": "编辑Agent: 未识别的子意图"}

    def _find_replace(self, params: dict, context: dict) -> dict:
        """全文查找替换"""
        message = params.get("message", "")
        find_text = params.get("find_text", "")
        replace_text = params.get("replace_text", "")
        if not find_text:
            for pat in _FIND_REPLACE_PATTERNS:
                m = re.search(pat, message)
                if m:
                    find_text = m.group(1).strip()
                    replace_text = m.group(2).strip()
                    break
        if not find_text:
            return {"reply": "请指定要查找和替换的内容，如'把陆远替换为路远'。"}
        try:
            if not state.project:
                return {"reply": "请先打开项目。"}
            total_count = 0
            affected_chapters = []
            for i in range(len(state.project.chapters)):
                content = state.project.get_content(i)
                if find_text in content:
                    count = content.count(find_text)
                    new_content = content.replace(find_text, replace_text)
                    state.project.set_content(new_content, i)
                    state.project.chapters[i]["word_count"] = len(new_content)
                    total_count += count
                    affected_chapters.append(f"第{i+1}章({count}处)")
            if total_count == 0:
                return {"reply": f"未找到「{find_text}」。"}
            else:
                state.project.save_all()
                return {
                    "reply": f"全文替换完成：共{total_count}处「{find_text}」->「{replace_text}」\n涉及：{', '.join(affected_chapters)}",
                    "action": {"type": "reload_current_chapter"},
                }
        except Exception as e:
            return {"reply": f"替换失败：{e}"}
