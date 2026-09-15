# -*- coding: utf-8 -*-
"""
书斋 V65 - AI对话中枢路由
POST /api/agent/chat

用户用自然语言发指令，AI识别意图并调度后端API执行，返回结构化结果。

v2 更新：引入 TraceContext 调用链追踪，每次请求创建一条 trace。
"""

import logging
from fastapi import APIRouter
from pydantic import BaseModel

from backend.agents.intent_classifier import parse_intent
from backend.agents.dispatcher import execute_intent, execute_edit_selection
from backend.agents.trace import TraceContext, clear_current_trace
from backend.prompt_sanitizer import sanitize_light

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent")


class AgentRequest(BaseModel):
    message: str
    context: dict = None  # {current_chapter_index, current_step, ...}
    selected_text: str = ""  # 编辑器中选中的文字（用于选段修复）


@router.post("/chat")
def agent_chat(data: AgentRequest):
    """AI对话中枢：自然语言 -> 意图识别 -> API调度 -> 结果返回"""
    message = sanitize_light((data.message or "").strip())
    if not message:
        return {"ok": False, "error": "消息为空"}

    context = data.context or {}
    selected_text = sanitize_light((data.selected_text or "").strip())

    # ── 创建请求级调用链追踪 ──
    trace = TraceContext.new_root("agent_chat")
    trace.log_event("request_start", {"message": message[:100]})

    try:
        # 如果有选中文字，直接走选段修复（不走意图识别，省一次AI调用）
        if selected_text and len(selected_text) > 10:
            intent = "edit_selection"
            params = {"message": message}
            intermediate_reply = "好的，我来修改选中的文字。"
        else:
            # 第一步：识别意图
            intent_span = trace.new_span("parse_intent")
            try:
                intent_data = parse_intent(message, context)
                intent = intent_data.get("intent", "general_chat")
                params = intent_data.get("params", {})
                intermediate_reply = intent_data.get("reply", "")
                trace.log_event("intent_parsed", {"intent": intent})
            finally:
                trace.activate()

        # 第二步：执行意图（选段修复需要传selected_text）
        if intent == "edit_selection":
            result = execute_edit_selection(message, selected_text, context)
        else:
            result = execute_intent(intent, params, context, message)

        # 提取 trace（execute_intent 内部可能已创建，合并）
        response = {
            "ok": True,
            "reply": result.get("reply", ""),
            "intent": intent,
            "data": result.get("data"),
            "action": result.get("action"),
            "intermediate_reply": intermediate_reply,
            "_trace_id": trace.trace_id,
        }

        trace.log_event("request_completed", {
            "intent": intent,
            "has_reply": bool(result.get("reply")),
            "has_action": bool(result.get("action")),
        })
        return response

    except Exception as e:
        logger.error("Agent error: %s", e, exc_info=True)
        trace.log_event("request_failed", {"error": str(e)})
        return {
            "ok": False,
            "error": f"处理失败：{str(e)}",
            "reply": f"处理时出错：{str(e)}",
            "_trace_id": trace.trace_id,
        }
    finally:
        clear_current_trace()