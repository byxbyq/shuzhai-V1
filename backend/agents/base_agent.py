# -*- coding: utf-8 -*-
"""
书斋 V65 - Agent 抽象基类
定义所有 Agent 的统一接口，包括状态管理、意图匹配、调用链追踪。
"""

import uuid
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional

from backend.agents.trace import get_current_trace

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Agent 状态机"""
    IDLE = "idle"           # 空闲，等待执行
    RUNNING = "running"     # 正在执行
    COMPLETED = "completed" # 已完成
    FAILED = "failed"       # 执行失败


class BaseAgent(ABC):
    """Agent 抽象基类。

    所有业务 Agent 都继承此类，实现统一的：
    - 意图匹配（通过 intent_keywords）
    - 状态管理（AgentState 状态机）
    - 调用链追踪（trace_id + span）
    - 结构化日志

    子类需要实现：
        - execute(params, context) -> dict

    使用示例::

        class OutlineAgent(BaseAgent):
            agent_id = "outline"
            agent_name = "大纲Agent"
            intent_keywords = ["generate_outline", "generate_all_outlines"]

            def execute(self, params, context):
                self.log_event("start", {"params": params})
                # ... 业务逻辑 ...
                return {"reply": "大纲已生成", "action": {...}}
    """

    # ── 子类必须覆盖的类属性 ──
    agent_id: str = ""           # 唯一标识
    agent_name: str = ""         # 可读名称
    intent_keywords: list = []   # 触发关键词列表（与 intent 名称匹配）

    def __init__(self):
        self._state: AgentState = AgentState.IDLE
        self._trace_id: str = ""

    # ── 属性 ──

    @property
    def state(self) -> AgentState:
        """当前状态"""
        return self._state

    @property
    def trace_id(self) -> str:
        """当前调用链追踪 ID"""
        return self._trace_id

    # ── 意图匹配 ──

    def can_handle(self, intent: str) -> bool:
        """检查 intent 是否匹配当前 Agent 的 keywords。

        匹配规则：intent 字符串出现在 intent_keywords 列表中即为匹配。
        """
        return intent in self.intent_keywords

    # ── 抽象方法 ──

    @abstractmethod
    def execute(self, params: dict, context: dict) -> dict:
        """执行 Agent 的核心逻辑。

        Args:
            params: 意图参数（从 parse_intent 中提取）
            context: 上下文信息（current_chapter_index 等）

        Returns:
            dict: {"reply": str, "data": ..., "action": ...}
        """
        ...

    # ── 状态管理 ──

    def _set_state(self, new_state: AgentState) -> None:
        """更新状态并记录日志"""
        old_state = self._state
        self._state = new_state
        logger.debug(
            "[agent] %s 状态变更: %s -> %s (trace_id=%s)",
            self.agent_name, old_state.value, new_state.value, self._trace_id,
        )

    # ── 日志 ──

    def log_event(self, event_type: str, data: Optional[dict] = None) -> None:
        """记录结构化事件日志。

        优先使用当前 trace 上下文的 log_event，否则降级为普通 logger。
        """
        trace = get_current_trace()
        if trace:
            trace.log_event(
                event_type=f"{self.agent_name}:{event_type}",
                data=data,
            )
        else:
            logger.info(
                "[agent] %s event=%s data=%s",
                self.agent_name, event_type, data or {},
            )

    # ── 执行包装 ──

    def run(self, params: dict, context: dict) -> dict:
        """带状态管理和 trace 追踪的执行入口。

        调用 execute() 前设置状态为 RUNNING，执行后根据结果设置 COMPLETED 或 FAILED。
        同时创建子 span 用于追踪。
        """
        self._trace_id = self._generate_trace_id()
        self._set_state(AgentState.RUNNING)
        self.log_event("start", {"params": params, "context_keys": list(context.keys()) if context else []})

        # 创建子 span
        parent_trace = get_current_trace()
        child_span = None
        if parent_trace:
            child_span = parent_trace.new_span(f"{self.agent_id}.execute")
            self.log_event("span_created", {"span_name": child_span.span_name})

        try:
            result = self.execute(params, context)
            self._set_state(AgentState.COMPLETED)
            self.log_event("completed", {"has_reply": bool(result.get("reply")), "has_action": bool(result.get("action"))})
            return result
        except Exception as e:
            self._set_state(AgentState.FAILED)
            self.log_event("failed", {"error": str(e)})
            logger.error("[agent] %s 执行失败: %s", self.agent_name, e, exc_info=True)
            return {"reply": f"{self.agent_name}执行失败：{str(e)}"}
        finally:
            # 恢复父 span
            if parent_trace and child_span:
                parent_trace.activate()

    def _generate_trace_id(self) -> str:
        """生成 trace_id，优先从当前 trace 上下文获取"""
        trace = get_current_trace()
        if trace:
            return trace.trace_id
        return uuid.uuid4().hex[:16]