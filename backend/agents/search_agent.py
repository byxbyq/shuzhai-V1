# -*- coding: utf-8 -*-
"""书斋 V66 - 搜索 Agent
处理用户的网络搜索请求：联网搜索 → AI 消化合成 → 返回结构化回答。
"""
import logging
from backend.agents.base_agent import BaseAgent
from backend.agents.intent_classifier import call_ai
from backend.web_search import search

logger = logging.getLogger(__name__)

_SEARCH_SYNTHESIS_PROMPT = """你是书斋V66的AI创作助手，请根据以下联网搜索结果回答用户问题。

要求：
1. 用简洁清晰的语言直接回答问题
2. 如果搜索结果充分，提炼关键信息作答
3. 如果搜索结果不足或不相关，如实说明，不要编造
4. 回答末尾列出参考来源（序号+标题）

用户问题：{query}

联网搜索结果：
{context}

请回答："""


class SearchAgent(BaseAgent):
    """网络搜索助手——联网查资料、核实信息，AI合成回答。"""

    agent_id = "search"
    agent_name = "搜索Agent"
    intent_keywords = ["search", "搜索", "查", "找资料", "搜一下", "搜搜"]

    def can_handle(self, intent: str) -> bool:
        return intent == "search"

    def execute(self, intent: str, params: dict, context: dict, message: str) -> dict:
        query = params.get("query") or message or ""

        if not query or len(query.strip()) < 2:
            return {
                "reply": "你想搜索什么？请告诉我关键词。",
                "type": "search_prompt",
            }

        try:
            results = search(query.strip(), max_results=5)
        except Exception as e:
            logger.warning("SearchAgent search error: %s", e)
            return {
                "reply": f"搜索失败：{e}。请检查网络连接后重试。",
                "type": "search_error",
            }

        if not results:
            return {
                "reply": f"未找到与「{query}」相关的结果，试试换个关键词？",
                "type": "search_no_results",
            }

        # 组装搜索上下文
        context_parts = []
        for i, r in enumerate(results, 1):
            line = f"[{i}] {r['title']}\n{r['snippet'][:300]}\n来源：{r['url']}"
            context_parts.append(line)
        context_text = "\n\n".join(context_parts)

        # 用 AI 消化搜索结果为自然语言回答
        try:
            prompt = _SEARCH_SYNTHESIS_PROMPT.format(
                query=query, context=context_text
            )
            reply = call_ai(prompt)
        except Exception as e:
            logger.warning("SearchAgent AI synthesis error: %s", e)
            # AI 合成失败时回退到原始搜索结果列表
            lines = [f"搜索「{query}」的结果：\n"]
            for i, r in enumerate(results, 1):
                lines.append(f"**{i}. [{r['title']}]({r['url']})**")
                if r["snippet"]:
                    lines.append(f"> {r['snippet'][:200]}")
                lines.append("")
            return {
                "reply": "\n".join(lines),
                "type": "search_results_raw",
                "results": results,
            }

        return {
            "reply": reply,
            "type": "search_synthesis",
            "results": results,
        }
