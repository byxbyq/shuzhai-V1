# -*- coding: utf-8 -*-
"""
书斋 V65 - 调用链追踪模块
提供 trace_id / span_id 的生成与上下文传播，支持嵌套 span（子调用）。
使用 contextvars 实现线程安全 / 异步安全的上下文传递。
"""

import uuid
import time
import logging
from contextvars import ContextVar
from typing import Optional

logger = logging.getLogger(__name__)

# ── contextvars：跨函数调用边界传递 trace 上下文 ──
_trace_context_var: ContextVar[Optional["TraceContext"]] = ContextVar(
    "trace_context", default=None
)


def generate_trace_id() -> str:
    """生成全局唯一的 trace ID（UUID4 短格式）"""
    return uuid.uuid4().hex[:16]


def generate_span_id() -> str:
    """生成 span ID（8 位十六进制）"""
    return uuid.uuid4().hex[:8]


class TraceContext:
    """调用链上下文，存储 trace_id、当前 span 信息及嵌套关系。

    使用示例::

        # 根 span
        trace = TraceContext.new_root()
        with trace.span("execute_intent"):
            # 子 span
            with trace.span("call_api"):
                ...

    支持通过 contextvars 跨函数获取::

        trace = get_current_trace()
        if trace:
            trace.log("event", {"key": "value"})
    """

    def __init__(
        self,
        trace_id: str,
        span_id: str,
        parent_span_id: str = "",
        span_name: str = "",
    ):
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.span_name = span_name
        self._start_time: float = time.time()
        self._span_stack: list[str] = []  # 记录 span 嵌套路径

    @classmethod
    def new_root(cls, span_name: str = "root") -> "TraceContext":
        """创建一条新的 trace（根 span）"""
        trace_id = generate_trace_id()
        span_id = generate_span_id()
        ctx = cls(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id="",
            span_name=span_name,
        )
        _trace_context_var.set(ctx)
        logger.debug(
            "[trace] 新建 trace_id=%s span_id=%s name=%s",
            trace_id, span_id, span_name,
        )
        return ctx

    def new_span(self, span_name: str) -> "TraceContext":
        """在当前 trace 下创建子 span，返回子 span 的 TraceContext。

        注意：调用者需要在子 span 结束后调用 parent_ctx.activate() 恢复父上下文。
        """
        child_span_id = generate_span_id()
        child = TraceContext(
            trace_id=self.trace_id,
            span_id=child_span_id,
            parent_span_id=self.span_id,
            span_name=span_name,
        )
        child._span_stack = list(self._span_stack) + [span_name]
        _trace_context_var.set(child)
        logger.debug(
            "[trace] 新建 span trace_id=%s span_id=%s parent=%s name=%s",
            self.trace_id, child_span_id, self.span_id, span_name,
        )
        return child

    def activate(self) -> None:
        """将当前上下文激活为线程的活跃 trace"""
        _trace_context_var.set(self)

    def log_event(self, event_type: str, data: Optional[dict] = None) -> None:
        """记录结构化事件到日志"""
        elapsed = time.time() - self._start_time
        log_data = {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "span_name": self.span_name,
            "event_type": event_type,
            "elapsed_ms": round(elapsed * 1000, 2),
            "data": data or {},
        }
        logger.info("[trace] %s", log_data)

    def to_dict(self) -> dict:
        """导出为字典"""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "span_name": self.span_name,
            "span_stack": self._span_stack,
        }


def get_current_trace() -> Optional[TraceContext]:
    """获取当前请求的 trace 上下文（通过 contextvars）"""
    return _trace_context_var.get()


def clear_current_trace() -> None:
    """清除当前 trace 上下文"""
    _trace_context_var.set(None)