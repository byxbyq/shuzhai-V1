# -*- coding: utf-8 -*-
"""
书斋 V65 - 意图识别模块
负责将用户自然语言消息解析为结构化意图。
"""

import json, re
from backend.ai_client import AIClient
from backend.agents.prompts import INTENT_PROMPT


def call_ai(prompt: str) -> str:
    """调用AI，返回文本"""
    ai = AIClient()
    return ai.generate(prompt)


def parse_intent(message: str, context: dict) -> dict:
    """用AI识别用户意图"""
    ctx_info = ""
    if context:
        ci = context.get("current_chapter_index", -1)
        if ci >= 0:
            ctx_info = f"\n（当前上下文：用户正在编辑第{ci+1}章）"
        # 创作向导上下文
        ws = context.get("wizard_stage", "")
        if ws and ws != "done":
            ctx_info += f"\n（当前处于创作向导阶段：{ws}，用户正在回答向导问题）"

    prompt = INTENT_PROMPT + f"\n\n用户指令：{message}{ctx_info}"
    raw = call_ai(prompt)

    # 剥离think标签和markdown
    raw = re.sub(r'<think\b.*?</think\b\s*>', '', raw, flags=re.DOTALL)
    raw = re.sub(r'```json\s*', '', raw)
    raw = re.sub(r'```\s*', '', raw).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
        # 兜底：通用对话
        return {
            "intent": "general_chat",
            "params": {},
            "reply": "我没太理解你的意思，可以再说清楚一点吗？比如「检查第1章连贯性」「导出pdf」「这周写了多少字」"
        }
