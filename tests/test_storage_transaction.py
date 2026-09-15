# -*- coding: utf-8 -*-
"""TransactionContext 单元测试（5 用例）"""

import os
import pytest
from unittest.mock import MagicMock


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════

@pytest.fixture
def mock_project():
    """构造最小化 mock project，供 TransactionContext 使用"""
    proj = MagicMock()
    proj._get_db.return_value.commit.return_value = None
    proj._save_meta.return_value = None
    return proj


@pytest.fixture
def target_dir(tmp_path):
    """临时目标目录，用于文件写入测试"""
    return str(tmp_path)


# ═══════════════════════════════════════════
# 导入被测模块
# ═══════════════════════════════════════════

from backend.storage_transaction import TransactionContext


# ═══════════════════════════════════════════
# 测试用例
# ═══════════════════════════════════════════

class TestTransactionContext:

    # ── 用例 1: commit 写入文件 ──

    def test_commit_writes_file(self, mock_project, target_dir):
        """register_file_write 后正常退出，文件存在且内容正确"""
        file_path = os.path.join(target_dir, "chapter_001.txt")
        content = "第一章正文内容"

        with TransactionContext(mock_project) as tx:
            tx.register_file_write(file_path, content)

        assert os.path.exists(file_path), "commit 后目标文件应存在"
        with open(file_path, "r", encoding="utf-8") as f:
            assert f.read() == content, "文件内容应一致"
        assert not os.path.exists(file_path + ".tmp"), ".tmp 文件应在 commit 后消失"

    # ── 用例 2: rollback 清理 .tmp ──

    def test_rollback_cleans_tmp(self, mock_project, target_dir):
        """异常退出时 .tmp 被清理，目标文件不存在"""
        file_path = os.path.join(target_dir, "chapter_002.txt")
        content = "第二章正文内容"

        try:
            with TransactionContext(mock_project) as tx:
                tx.register_file_write(file_path, content)
                raise ValueError("模拟业务异常")
        except ValueError:
            pass

        assert not os.path.exists(file_path), "rollback 后目标文件不应存在"
        assert not os.path.exists(file_path + ".tmp"), "rollback 后 .tmp 应被清理"

    # ── 用例 3: mark_sqlite_dirty 触发 commit ──

    def test_mark_sqlite_dirty_triggers_commit(self, mock_project):
        """mark_sqlite_dirty() 后正常退出，_save_meta 被调用"""
        with TransactionContext(mock_project) as tx:
            tx.mark_sqlite_dirty()

        mock_project._save_meta.assert_called_once()

    # ── 用例 4: 若干文件原子性 ──

    def test_multiple_files_atomic(self, mock_project, target_dir):
        """注册 3 个文件写入，异常时全部 .tmp 清理，无残留"""
        files = {}
        for i in range(3):
            files[os.path.join(target_dir, f"ch_{i}.txt")] = f"content_{i}"

        try:
            with TransactionContext(mock_project) as tx:
                for path, content in files.items():
                    tx.register_file_write(path, content)
                raise RuntimeError("模拟中途异常")
        except RuntimeError:
            pass

        for path in files:
            assert not os.path.exists(path), f"rollback 后 {path} 不应存在"
            assert not os.path.exists(path + ".tmp"), f"rollback 后 {path}.tmp 应被清理"

    # ── 用例 5: 空上下文不抛异常 ──

    def test_noop_context(self, mock_project):
        """不注册任何操作，__exit__ 不抛异常"""
        try:
            with TransactionContext(mock_project) as tx:
                pass
        except Exception:
            pytest.fail("空事务上下文不应抛异常")
        mock_project._save_meta.assert_not_called()
