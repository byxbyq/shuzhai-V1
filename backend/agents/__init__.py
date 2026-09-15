# -*- coding: utf-8 -*-
"""
书斋 V65 - Agent 子包

v2 更新：引入 Agent 架构重构，包含：
- BaseAgent: Agent 抽象基类（状态机、调用链追踪、意图匹配）
- AgentRegistry: Agent 注册表（替代硬编码 if/elif 链）
- TraceContext: 调用链追踪上下文
- 示例 Agent: OutlineAgent, ChapterAgent, ValidateAgent, WorldAgent, CharacterAgent
"""

from backend.agents.router import router
from backend.agents.base_agent import BaseAgent, AgentState
from backend.agents.agent_registry import AgentRegistry, get_registry
from backend.agents.trace import TraceContext, get_current_trace, generate_trace_id, generate_span_id
from backend.agents.dispatcher import execute_intent, execute_edit_selection

__all__ = [
    # 原有导出
    "router",
    "execute_intent",
    "execute_edit_selection",
    # 新增：Agent 基类
    "BaseAgent",
    "AgentState",
    # 新增：注册表
    "AgentRegistry",
    "get_registry",
    # 新增：调用链追踪
    "TraceContext",
    "get_current_trace",
    "generate_trace_id",
    "generate_span_id",
]