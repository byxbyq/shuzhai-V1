# -*- coding: utf-8 -*-
"""
书斋 V66 - 记忆/伏笔 Agent
处理伏笔、记忆、时间线相关意图。
"""

import logging

from backend.agents.base_agent import BaseAgent
from backend.agents.dispatcher import (
    _resolve_chapter_index,
    _api_get,
    _api_post,
    _get_base_url,
)

logger = logging.getLogger(__name__)


class MemoryAgent(BaseAgent):
    """处理记忆/伏笔/时间线相关意图：
    - get_memory: 获取记忆概览
    - add_hook: 添加伏笔
    - recover_hook: 回收伏笔
    - get_timeline: 时间线
    - memory_search: 记忆搜索
    """

    agent_id = "memory"
    agent_name = "记忆Agent"
    intent_keywords = [
        "get_memory", "add_hook", "recover_hook",
        "get_timeline", "memory_search", "abandon_hook",
    ]

    def execute(self, params: dict, context: dict) -> dict:
        intent = params.get("_intent", "")
        self.log_event("memory_action", {"intent": intent})

        if intent == "get_memory":
            return self._get_memory(params, context)
        elif intent == "add_hook":
            return self._add_hook(params, context)
        elif intent == "recover_hook":
            return self._recover_hook(params, context)
        elif intent == "get_timeline":
            return self._get_timeline(params, context)
        elif intent == "memory_search":
            return self._memory_search(params, context)
        elif intent == "abandon_hook":
            return self._abandon_hook(params, context)
        else:
            return {"reply": "记忆Agent: 未识别的子意图"}

    def _get_memory(self, params: dict, context: dict) -> dict:
        """获取记忆概览"""
        try:
            hooks_data = _api_get(_get_base_url() + "/api/ledger/hooks", timeout=10)
            mem_data = _api_get(_get_base_url() + "/api/memory/stats", timeout=10)
            text = ""
            if hooks_data.get("ok"):
                active = hooks_data.get("active", [])
                recovered = hooks_data.get("recovered", [])
                abandoned = hooks_data.get("abandoned", [])
                text += f"伏笔状态：活跃{len(active)}个，已回收{len(recovered)}个，废弃{len(abandoned)}个\n"
                for h in active[:5]:
                    text += f"  * {h.get('content', '')[:50]}（第{h.get('planted_chapter', 0)+1}章埋）\n"
            if mem_data.get("ok"):
                text += f"\n记忆库：共{mem_data.get('total', 0)}条记忆"
            return {"reply": text or "暂无记忆数据。", "data": {"hooks": hooks_data, "memory": mem_data}}
        except Exception as e:
            return {"reply": f"获取记忆数据失败：{e}"}

    def _add_hook(self, params: dict, context: dict) -> dict:
        """添加伏笔"""
        message = params.get("message", "")
        content = params.get("hook_content") or message
        try:
            rdata = _api_post(
                _get_base_url() + "/api/ledger/hook/add",
                {"content": content, "planted_chapter": _resolve_chapter_index(params, context), "expected_recovery_chapter": 0, "related_characters": [], "related_items": []},
                timeout=10,
            )
            return {"reply": "伏笔已添加" if rdata.get("ok") else f"添加失败：{rdata.get('error', '')}"}
        except Exception as e:
            return {"reply": f"添加伏笔出错：{e}"}

    def _recover_hook(self, params: dict, context: dict) -> dict:
        """回收伏笔"""
        hook_id = params.get("hook_id")
        message = params.get("message", "")
        if not hook_id:
            try:
                hdata = _api_get(_get_base_url() + "/api/ledger/hooks", timeout=10)
                if hdata.get("ok"):
                    active = hdata.get("active", [])
                    text = f"当前有{len(active)}个活跃伏笔：\n"
                    for h in active[:8]:
                        hid = h.get("id", h.get("hook_id", "?"))
                        text += f"  [{hid}] {h.get('content', '')[:50]}（第{h.get('planted_chapter', 0)+1}章埋）\n"
                    text += "\n告诉我要回收哪个，比如「回收伏笔 xxx」"
                    return {"reply": text}
                else:
                    return {"reply": "暂无伏笔数据。"}
            except Exception as e:
                return {"reply": f"获取伏笔出错：{e}"}
        else:
            try:
                rdata = _api_post(
                    _get_base_url() + "/api/ledger/hook/recover",
                    {"hook_id": hook_id, "reason": message or "手动回收"},
                    timeout=10,
                )
                return {"reply": "伏笔已回收" if rdata.get("ok") else f"回收失败：{rdata.get('error', '')}"}
            except Exception as e:
                return {"reply": f"回收伏笔出错：{e}"}

    def _abandon_hook(self, params: dict, context: dict) -> dict:
        """废弃伏笔：优先 hook_id，否则按内容关键词匹配活跃伏笔"""
        hook_id = params.get("hook_id")
        keyword = (params.get("hook_content") or "").strip()
        reason = params.get("reason") or "手动废弃"
        try:
            if not hook_id:
                if not keyword:
                    return {"reply": "请说清要废弃哪个伏笔，如'废弃伏笔xxx'。"}
                hdata = _api_get(_get_base_url() + "/api/ledger/hooks", timeout=10)
                if not hdata.get("ok"):
                    return {"reply": "获取伏笔列表失败。"}
                for h in hdata.get("active", []):
                    content = h.get("content", "")
                    if keyword in content or content in keyword:
                        hook_id = h.get("id", h.get("hook_id"))
                        break
                if not hook_id:
                    names = "、".join(h.get("content", "")[:20] for h in hdata.get("active", [])[:8]) or "（无活跃伏笔）"
                    return {"reply": f"找不到包含「{keyword}」的伏笔。现有活跃伏笔：{names}"}
            rdata = _api_post(
                _get_base_url() + "/api/ledger/hook/abandon",
                {"hook_id": hook_id, "reason": reason},
                timeout=10,
            )
            if rdata.get("ok"):
                return {
                    "reply": "伏笔已废弃。",
                    "action": {"type": "reload_hooks"},
                }
            return {"reply": f"废弃失败：{rdata.get('error', '')}"}
        except Exception as e:
            return {"reply": f"废弃伏笔出错：{e}"}

    def _get_timeline(self, params: dict, context: dict) -> dict:
        """时间线"""
        try:
            tl_data = _api_get(_get_base_url() + "/api/ledger/timeline", timeout=10)
            if tl_data.get("ok"):
                events = tl_data.get("timeline", [])
                text = f"时间线共{len(events)}个事件：\n"
                for ev in events[:10]:
                    text += f"  第{ev.get('chapter', 0)+1}章 - {ev.get('event', ev.get('description', ''))[:60]}\n"
                if len(events) > 10:
                    text += f"  ...还有{len(events)-10}个事件"
                return {"reply": text, "data": tl_data}
            else:
                return {"reply": "暂无时间线数据。"}
        except Exception as e:
            return {"reply": f"获取时间线出错：{e}"}

    def _memory_search(self, params: dict, context: dict) -> dict:
        """记忆搜索"""
        message = params.get("message", "")
        query = params.get("search_query") or message
        try:
            mdata = _api_post(
                _get_base_url() + "/api/memory/search",
                {"query": query, "k": 5},
                timeout=30,
            )
            if mdata.get("ok"):
                results = mdata.get("results", [])
                text = f"找到{mdata.get('count', 0)}条相关记忆：\n"
                for r in results[:5]:
                    text += f"  [{r.get('memory_type', '')}] {r.get('content', '')[:60]}（相似度{r.get('score', 0):.2f}）\n"
                return {"reply": text, "data": mdata}
            else:
                return {"reply": f"搜索失败：{mdata.get('error', '')}"}
        except Exception as e:
            return {"reply": f"记忆搜索出错：{e}"}
