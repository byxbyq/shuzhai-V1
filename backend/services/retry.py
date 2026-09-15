# -*- coding: utf-8 -*-
"""
书斋 V66 — 指数退避重试模块

提供可配置的异步重试机制，支持指数退避间隔和可重试错误类型判断。

公开函数:
    retry_with_backoff(func, max_retries=3, base_delay=1.0, retryable_errors=None)
        - 异步重试包装器，指数退避间隔为 base_delay * 2^(retry-1)
        - retryable_errors 默认包含 TimeoutError 和含特定关键字的异常
"""

import asyncio
import logging
from typing import Callable, Optional, Tuple, Type, Any

logger = logging.getLogger(__name__)

# 默认可重试错误类型匹配关键字
_DEFAULT_RETRYABLE_KEYWORDS = ("rate_limit", "timeout", "server_error")


def _is_retryable(error: Exception, retryable_errors: Optional[Tuple[Type[Exception], ...]] = None,
                   extra_keywords: Optional[Tuple[str, ...]] = None) -> bool:
    """判断异常是否属于可重试类型。

    Args:
        error: 捕获的异常
        retryable_errors: 允许重试的异常类型元组
        extra_keywords: 额外的错误消息关键字（大小写不敏感匹配）

    Returns:
        是否可重试
    """
    # 类型匹配
    if retryable_errors is not None:
        if isinstance(error, retryable_errors):
            return True

    # 关键字匹配
    if extra_keywords is not None:
        error_str = str(error).lower()
        for kw in extra_keywords:
            if kw.lower() in error_str:
                return True

    # 默认关键字匹配
    error_str = str(error).lower()
    for kw in _DEFAULT_RETRYABLE_KEYWORDS:
        if kw.lower() in error_str:
            return True

    return False


async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    retryable_errors: Optional[Tuple[Type[Exception], ...]] = None,
    extra_keywords: Optional[Tuple[str, ...]] = None,
    *args,
    **kwargs
) -> Any:
    """带指数退避的异步重试包装器。

    每次重试前等待 base_delay * 2^(retry-1) 秒，
    例如 base_delay=1.0 时：1s, 2s, 4s, 8s, ...

    Args:
        func: 要重试的异步函数（callable）
        max_retries: 最大重试次数（不含首次调用），默认 3
        base_delay: 基础延迟秒数，默认 1.0
        retryable_errors: 可重试的异常类型元组，默认 None（依赖关键字匹配）
        extra_keywords: 额外的错误消息关键字，默认 None（使用内置关键字）
        *args, **kwargs: 传递给 func 的参数

    Returns:
        func 的返回值

    Raises:
        最后一次调用抛出的异常（如果所有重试均失败）
    """
    # 合并默认关键字和额外关键字
    keywords = _DEFAULT_RETRYABLE_KEYWORDS
    if extra_keywords is not None:
        keywords = tuple(set(_DEFAULT_RETRYABLE_KEYWORDS + extra_keywords))

    # 默认可重试错误类型：TimeoutError
    if retryable_errors is None:
        retryable_errors = (TimeoutError, asyncio.TimeoutError)

    last_error: Optional[Exception] = None

    for attempt in range(max_retries + 1):  # 0..max_retries，共 max_retries+1 次尝试
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            return result
        except Exception as e:
            last_error = e

            if attempt >= max_retries:
                # 已达最大尝试次数
                logger.error(
                    f"[重试] 已尝试 {attempt + 1} 次（含 {max_retries} 次重试），全部失败: {e}"
                )
                raise

            if not _is_retryable(e, retryable_errors, keywords):
                # 不可重试的错误，直接抛出
                logger.warning(f"[重试] 遇到不可重试错误，停止重试: {e}")
                raise

            # 计算等待时间
            delay = base_delay * (2 ** attempt)  # 0-based: 1s, 2s, 4s, ...
            logger.warning(
                f"[重试] 第 {attempt + 1}/{max_retries + 1} 次尝试失败，"
                f"{delay:.1f}秒后进行第 {attempt + 2} 次重试。错误: {e}"
            )
            await asyncio.sleep(delay)

    # 理论上不会到这里（最后一次会 raise），但保留兜底
    if last_error is not None:
        raise last_error
    raise RuntimeError("retry_with_backoff: 意外终止")
