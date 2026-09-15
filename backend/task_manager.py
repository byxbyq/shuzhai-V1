# -*- coding: utf-8 -*-
"""书斋 V66 — 后台任务管理器

单例模式：全局唯一 TaskManager 实例，管理所有后台长任务（AI 生成/蒸馏/解构）。
提供任务提交、进度查询、取消令牌、并发控制和自动清理功能。
"""

import uuid
import time
import threading
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable

logger = logging.getLogger(__name__)

# ── 常量 ──
MAX_CONCURRENT_TASKS = 2          # 最大并发 AI 任务（避免 token 耗尽）
CLEANUP_AGE_SECONDS = 3600        # 已完成任务保留 1 小时后自动清理


class TaskStatus(str, Enum):
    pending   = "pending"
    running   = "running"
    completed = "completed"
    failed    = "failed"
    cancelled = "cancelled"


@dataclass
class TaskInfo:
    task_id:    str
    task_type:  str
    status:     TaskStatus  = TaskStatus.pending
    progress:   int         = 0           # 0-100
    message:    str         = ""          # 当前步骤描述
    result:     Any         = None        # 完成后的结果
    error:      str         = ""          # 失败原因
    created_at: float       = field(default_factory=time.time)
    updated_at: float       = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "task_id":    self.task_id,
            "task_type":  self.task_type,
            "status":     self.status.value,
            "progress":   self.progress,
            "message":    self.message,
            "result":     self.result,
            "error":      self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class _TaskContext:
    """单个任务的运行时上下文（内部使用）"""
    def __init__(self, info: TaskInfo):
        self.info         = info
        self.cancel_event = threading.Event()


class TaskManager:
    """单例后台任务管理器"""

    _instance: Optional["TaskManager"] = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._initialized = False
                    cls._instance = obj
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._tasks: Dict[str, _TaskContext] = {}
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(MAX_CONCURRENT_TASKS)
        logger.info("TaskManager 初始化完成，最大并发=%d", MAX_CONCURRENT_TASKS)

    # ── 公开 API ──

    def submit(self, task_type: str, func: Callable, *args, **kwargs) -> str:
        """提交任务到线程池，立即返回 task_id。

        参数：
            task_type: 任务类型标签（如 "distill" / "generate" / "deconstruct"）
            func:       要在线程中执行的可调用对象。
                        签名应为 func(info: TaskInfo, cancel_event: threading.Event, ...)
                        前两个参数由 TaskManager 自动注入，后续 *args/**kwargs 透传。
        返回：
            task_id 字符串
        """
        task_id = uuid.uuid4().hex[:12]
        info = TaskInfo(task_id=task_id, task_type=task_type)
        ctx = _TaskContext(info)

        with self._lock:
            self._tasks[task_id] = ctx

        # 自动清理过期任务
        self._cleanup()

        # 启动后台线程
        t = threading.Thread(
            target=self._run_task,
            args=(ctx, func, args, kwargs),
            daemon=True,
        )
        t.start()
        logger.info("任务已提交: task_id=%s type=%s", task_id, task_type)
        return task_id

    def get_status(self, task_id: str) -> Optional[TaskInfo]:
        """查询任务状态与进度"""
        with self._lock:
            ctx = self._tasks.get(task_id)
        return ctx.info if ctx else None

    def cancel(self, task_id: str) -> bool:
        """取消指定任务。返回 True 表示取消信号已发出"""
        with self._lock:
            ctx = self._tasks.get(task_id)
        if ctx is None:
            return False
        if ctx.info.status in (TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled):
            return False
        ctx.cancel_event.set()
        ctx.info.status = TaskStatus.cancelled
        ctx.info.updated_at = time.time()
        ctx.info.message = "正在取消..."
        logger.info("任务取消信号已发出: task_id=%s", task_id)
        return True

    def update_progress(self, task_id: str, progress: int, message: str = ""):
        """供执行函数内部调用的进度上报接口"""
        with self._lock:
            ctx = self._tasks.get(task_id)
        if ctx is None:
            return
        ctx.info.progress = max(0, min(100, progress))
        ctx.info.message = message
        ctx.info.updated_at = time.time()

    def list_tasks(self, task_type: str = None) -> List[dict]:
        """列出任务（可按类型过滤），按创建时间倒序"""
        with self._lock:
            tasks = list(self._tasks.values())
        result = []
        for ctx in tasks:
            if task_type and ctx.info.task_type != task_type:
                continue
            result.append(ctx.info.to_dict())
        result.sort(key=lambda x: x["created_at"], reverse=True)
        return result

    # ── 内部方法 ──

    def _run_task(self, ctx: _TaskContext, func: Callable, args, kwargs):
        """后台线程入口：获取信号量 → 执行 → 兜底处理"""
        acquired = self._semaphore.acquire(timeout=1)
        if not acquired:
            # 信号量满，等不到 slot — 任务仍排队执行（阻塞到 acquire）
            self._semaphore.acquire()

        try:
            ctx.info.status = TaskStatus.running
            ctx.info.updated_at = time.time()
            ctx.info.message = "开始执行..."
            logger.info("任务开始执行: task_id=%s", ctx.info.task_id)

            result = func(ctx.info, ctx.cancel_event, *args, **kwargs)

            # 函数正常返回 → completed（除非已被 cancel 设置）
            if ctx.info.status == TaskStatus.running:
                ctx.info.status = TaskStatus.completed
                ctx.info.result = result
                ctx.info.progress = 100
                ctx.info.message = "完成"
            ctx.info.updated_at = time.time()

        except Exception as e:
            logger.exception("任务执行异常: task_id=%s", ctx.info.task_id)
            ctx.info.status = TaskStatus.failed
            ctx.info.error = str(e)
            ctx.info.message = f"异常: {e}"
            ctx.info.updated_at = time.time()

        finally:
            self._semaphore.release()

    def _cleanup(self):
        """清理超过 CLEANUP_AGE_SECONDS 的已完成/失败/取消任务"""
        now = time.time()
        stale_ids = []
        with self._lock:
            for tid, ctx in self._tasks.items():
                if ctx.info.status in (TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled):
                    if now - ctx.info.updated_at > CLEANUP_AGE_SECONDS:
                        stale_ids.append(tid)
        for tid in stale_ids:
            with self._lock:
                self._tasks.pop(tid, None)
            logger.debug("自动清理过期任务: task_id=%s", tid)


# ── 全局单例 ──
task_manager = TaskManager()
