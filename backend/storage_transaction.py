# -*- coding: utf-8 -*-
"""书斋 V66 - 统一存储事务层 (Phase 1)

TransactionContext 提供跨介质（TXT + SQLite）的统一事务边界：
- prepare 阶段：注册 TXT 写入 → 写入 .tmp 临时文件
- commit 阶段：先 commit SQLite → 再将 .tmp rename 替换原文件
- rollback 阶段：删除所有 .tmp 临时文件，不碰原文件

使用示例:
    tx = TransactionContext(project)
    with tx:
        tx.register_file_write(chapter_path, content)
        # ... 更新内存状态 ...
        tx.mark_sqlite_dirty()
"""

import os
import threading
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass  # NovelProject 类型在运行期由 project 参数传入


class TransactionContext:
    """统一存储事务上下文管理器。

    设计原则：
    - TXT 文件采用 write-to-tmp + rename 原子替换模式
    - SQLite 写入委托给 project._save_meta()（内部自带事务）
    - commit 顺序：先 SQLite 后文件 rename，确保元数据优先落盘
    - rollback 仅清理 .tmp，不碰原文件和已提交的 SQLite
    - 线程安全：threading.Lock 保护内部状态
    """

    def __init__(self, project):
        """初始化事务上下文。

        Args:
            project: NovelProject 实例，需提供 _save_meta() 方法用于 SQLite 持久化。
        """
        self._project = project
        self._pending_files: Dict[str, str] = {}  # {real_path: tmp_path}
        self._sqlite_dirty: bool = False
        self._lock = threading.Lock()
        self._entered: bool = False

    # ── 上下文管理器 ──

    def __enter__(self) -> "TransactionContext":
        """进入事务上下文，返回 self 供 with-as 绑定。"""
        self._entered = True
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> bool:
        """退出事务上下文。

        - 无异常：执行 commit（SQLite → 文件 rename）
        - 有异常：执行 rollback（清理 .tmp）
        """
        if exc_type is not None:
            self._rollback()
            return False  # 让异常继续传播
        try:
            self._commit()
        except Exception:
            self._rollback()
            raise
        return False

    # ── 注册接口 ──

    def register_file_write(self, real_path: str, content: str) -> None:
        """注册一个 TXT 文件写入操作。

        将 content 写入 real_path.tmp 临时文件，真正的替换在 commit 阶段完成。

        Args:
            real_path: 目标文件的绝对路径（如 chapter_001.txt）
            content: 要写入的文本内容
        """
        with self._lock:
            tmp_path = real_path + ".tmp"
            os.makedirs(os.path.dirname(real_path), exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
            self._pending_files[real_path] = tmp_path

    def mark_sqlite_dirty(self) -> None:
        """标记 SQLite 有待提交的写入操作。

        commit 阶段会调用 project._save_meta() 将内存状态持久化到 SQLite。
        """
        with self._lock:
            self._sqlite_dirty = True

    # ── 内部实现 ──

    def _commit(self) -> None:
        """提交事务：先 SQLite 后文件 rename。

        顺序保证：SQLite 元数据先落盘，然后 TXT 文件原子替换。
        若 SQLite 写入失败，.tmp 文件不会 rename，旧 TXT 原样保留。
        """
        with self._lock:
            # 1. SQLite：委托 _save_meta()（内部自带事务，失败会抛异常）
            if self._sqlite_dirty:
                self._project._save_meta()

            # 2. TXT：原子替换（os.replace 在同一文件系统上是原子的）
            for real_path, tmp_path in self._pending_files.items():
                os.replace(tmp_path, real_path)

            self._pending_files.clear()
            self._sqlite_dirty = False

    def _rollback(self) -> None:
        """回滚事务：删除所有 .tmp 文件，不碰原文件。"""
        with self._lock:
            for tmp_path in self._pending_files.values():
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass
            self._pending_files.clear()
            self._sqlite_dirty = False
