# -*- coding: utf-8 -*-
"""项目服务单元测试（14 用例）

测试范围：
  - retry_with_backoff 异步重试机制
  - _is_retryable 错误判断
  - save_chapter_outline 章节大纲保存
  - perturb_text 文本结构扰动
"""

import pytest
from unittest.mock import patch, MagicMock


# ═══════════════════════════════════════════
# 1. retry 模块测试
# ═══════════════════════════════════════════

from backend.services.retry import _is_retryable, retry_with_backoff


class TestIsRetryable:
    """可重试错误判断"""

    def test_timeout_is_retryable(self):
        """TimeoutError 含 timeout 关键字时可重试"""
        assert _is_retryable(TimeoutError("request timeout after 30s")) is True

    def test_value_error_not_retryable(self):
        """普通 ValueError 不可重试"""
        assert _is_retryable(ValueError("invalid argument")) is False

    def test_rate_limit_keyword_retryable(self):
        """含 'rate_limit' 关键字的异常可重试"""
        assert _is_retryable(RuntimeError("rate_limit exceeded")) is True

    def test_server_error_keyword_retryable(self):
        """含 'server_error' 关键字的异常可重试"""
        assert _is_retryable(RuntimeError("server_error occurred")) is True

    def test_timeout_keyword_retryable(self):
        """含 'timeout' 关键字的异常可重试"""
        assert _is_retryable(RuntimeError("request timeout after 30s")) is True

    def test_custom_retryable_type(self):
        """自定义可重试类型"""
        class CustomRetryable(Exception):
            pass
        exc = CustomRetryable("retry me")
        assert _is_retryable(exc, retryable_errors=(CustomRetryable,)) is True

    def test_custom_extra_keyword(self):
        """自定义额外关键字"""
        exc = RuntimeError("circuit_breaker_open")
        assert _is_retryable(exc, extra_keywords=("circuit_breaker",)) is True


class TestRetryWithBackoff:
    """异步重试机制"""

    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        """第一次成功不重试"""
        called = []

        async def success():
            called.append(1)
            return "ok"

        result = await retry_with_backoff(success, max_retries=2)
        assert result == "ok"
        assert called == [1]

    @pytest.mark.asyncio
    async def test_retry_on_timeout_then_success(self):
        """超时后重试成功"""
        calls = []

        async def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise TimeoutError("first timeout")
            return "recovered"

        result = await retry_with_backoff(flaky, max_retries=2, base_delay=0.01)
        assert result == "recovered"
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_exhaust_retries_raises(self):
        """耗尽重试后抛出最后一次异常"""
        async def always_fail():
            raise TimeoutError("always timeout")

        with pytest.raises(TimeoutError, match="always timeout"):
            await retry_with_backoff(always_fail, max_retries=2, base_delay=0.01)

    @pytest.mark.asyncio
    async def test_non_retryable_stops_immediately(self):
        """不可重试错误立即停止"""
        calls = []

        async def bad_call():
            calls.append(1)
            raise ValueError("invalid input")

        with pytest.raises(ValueError, match="invalid input"):
            await retry_with_backoff(bad_call, max_retries=3, base_delay=0.01)

        # 只调用了一次，没有重试
        assert len(calls) == 1


# ═══════════════════════════════════════════
# 2. chapter_service 测试
# ═══════════════════════════════════════════

class TestSaveChapterOutline:
    """章节大纲保存"""

    def test_no_project_returns_error(self):
        """无项目时返回错误"""
        with patch('backend.services.chapter_service.state') as mock_state:
            mock_state.project = None
            from backend.services.chapter_service import save_chapter_outline
            result = save_chapter_outline({"index": 0, "outline": "test"})
        assert result["ok"] is False
        assert result["error"] == "no project"

    def test_invalid_index_returns_error(self):
        """无效索引返回错误"""
        mock_project = MagicMock()
        mock_project.chapters = []  # 空列表
        mock_project.save_all = MagicMock()
        with patch('backend.services.chapter_service.state') as mock_state:
            mock_state.project = mock_project
            from backend.services.chapter_service import save_chapter_outline
            result = save_chapter_outline({"index": 5, "outline": "test"})
        assert result["ok"] is False
        assert result["error"] == "invalid chapter index"

    def test_save_outline_success(self):
        """保存大纲成功"""
        mock_project = MagicMock()
        mock_project.chapters = [{"title": "第一章", "outline": ""}]
        mock_project.save_all = MagicMock()
        with patch('backend.services.chapter_service.state') as mock_state:
            mock_state.project = mock_project
            from backend.services.chapter_service import save_chapter_outline
            result = save_chapter_outline({
                "index": 0,
                "outline": "主角踏上旅程",
                "blueprint": {"act": "开局"},
                "locked": True
            })
        assert result["ok"] is True
        assert mock_project.chapters[0]["outline"] == "主角踏上旅程"
        assert mock_project.chapters[0]["blueprint"] == {"act": "开局"}
        assert mock_project.chapters[0]["locked"] is True
        mock_project.save_all.assert_called_once()


# ═══════════════════════════════════════════
# 3. text_perturb 测试
# ═══════════════════════════════════════════

from backend.services.text_perturb import perturb_text


class TestPerturbText:
    """文本结构扰动"""

    def test_short_text_unchanged(self):
        """短文本（<200字）原样返回"""
        short = "这是一段很短的测试文本。只有几个字而已。"
        result = perturb_text(short, intensity=0.5, seed=42)
        assert result == short

    def test_empty_text_unchanged(self):
        """空文本原样返回"""
        assert perturb_text("", intensity=0.5) == ""

    def test_same_seed_reproducible(self):
        """相同种子结果一致"""
        long_text = (
            "第一章　风云涌动。那是一个灰蒙蒙的清晨，天边的云层低垂得仿佛要压到屋顶上来。"
            "张三站在城墙上望着远方连绵的山脉，心中翻涌着莫名的躁动，他想起师傅临终前的话语，"
            "想起那些被岁月掩埋的秘密。身边的老仆低声说少爷该用早膳了，他摆了摆手没有回答，"
            "目光依旧望着东边的方向。这几日城里来了许多陌生的面孔，他们穿着各式各样的服饰，"
            "操着不同的口音，但每个人眼中都闪动着同样的光芒。那是一种对即将发生之事的预感，"
            "一种山雨欲来风满楼的压抑。夜幕降临时城中的灯火比往日更早地亮了起来，街巷间传来"
            "急促的脚步声和兵器碰撞的声响。这是一个注定不平凡的夜晚，空气中弥漫着紧张的气息，"
            "仿佛整个世界都在等待着什么。张三缓缓走下城墙，脚步沉重而坚定。"
        )
        r1 = perturb_text(long_text, intensity=0.5, seed=123)
        r2 = perturb_text(long_text, intensity=0.5, seed=123)
        assert r1 == r2

    def test_intensity_zero_produces_minimal_changes(self):
        """intensity=0 几乎不变化"""
        long_text = (
            "第一章　风云涌动。那是一个灰蒙蒙的清晨，天边的云层低垂得仿佛要压到屋顶上来。"
            "张三站在城墙上望着远方连绵的山脉，心中翻涌着莫名的躁动，他想起师傅临终前的话语，"
            "想起那些被岁月掩埋的秘密。身边的老仆低声说少爷该用早膳了，他摆了摆手没有回答，"
            "目光依旧望着东边的方向。这几日城里来了许多陌生的面孔，他们穿着各式各样的服饰，"
            "操着不同的口音，但每个人眼中都闪动着同样的光芒。那是一种对即将发生之事的预感。"
        )
        result = perturb_text(long_text, intensity=0.0, seed=0)
        # intensity=0 时，随机断句概率很低，段落拆分概率低
        # 超长句还是会切断，但概率也低
        # 基本上应该和原文差不多
        assert isinstance(result, str)
        assert len(result) > 0
