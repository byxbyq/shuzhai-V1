# -*- coding: utf-8 -*-
"""
书斋 V66 — 上下文压缩模块

提供三种压缩策略，用于在调用 LLM 前压缩对话历史，
控制输入 token 数量。

公开函数:
    compress_context(messages, strategy, max_tokens, task_type) -> list
        - full: 原文返回，不压缩
        - micro: 调用 LLM 对每条消息做一句话摘要
        - reactive: 根据 task_type 自动选择压缩粒度
"""

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

# 将消息列表粗略估算为 token 数（中文字符 ~2 token/字，英文 ~1.3 token/字）
_CHAR_PER_TOKEN = 0.5

# 生成类任务集合（reactive 策略与 ctx_layer 预处理共用）
_GENERATION_TASKS = {"generate", "writing", "draft", "chapter", "generation"}


def _apply_ctx_layer(messages: List[Dict], task_type: str) -> List[Dict]:
    """P2-2 上下文分层预处理（三策略共用）。

    消息可携带 ctx_layer 标记：
    - "excluded": 直接丢弃
    - "archived": 合并为单条摘要消息（置于最前）
    - "draft":    仅生成类任务保留，其余丢弃
    未标记消息原样保留（移除 ctx_layer 键避免干扰下游）。
    """
    is_gen = (task_type or "").lower().strip() in _GENERATION_TASKS
    kept: List[Dict] = []
    archived_parts: List[str] = []
    for msg in messages:
        layer = msg.get("ctx_layer")
        if layer == "excluded":
            continue
        if layer == "archived":
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                archived_parts.append(content.strip()[:200])
            continue
        if layer == "draft" and not is_gen:
            continue
        kept.append({k: v for k, v in msg.items() if k != "ctx_layer"})
    if archived_parts:
        merged = "[归档摘要] " + " | ".join(archived_parts)
        kept.insert(0, {"role": "system", "content": merged[:1000]})
        logger.info(f"[上下文压缩] ctx_layer 预处理：合并 {len(archived_parts)} 条 archived 消息")
    return kept


def _estimate_tokens(messages: List[Dict]) -> int:
    """粗略估算消息列表的总 token 数。"""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += int(len(content) * _CHAR_PER_TOKEN)
    return total


def _compress_full(messages: List[Dict], max_tokens: int, task_type: str) -> List[Dict]:
    """full 策略：原文返回，如果超限则截断最早的消息。"""
    estimated = _estimate_tokens(messages)
    if estimated <= max_tokens:
        return messages

    # 超限则从最早的消息逐步移除，直到估计值在 max_tokens 内
    # 但至少保留最后一条消息（通常是用户当前问题）
    result = list(messages)
    while len(result) > 1 and _estimate_tokens(result) > max_tokens:
        result.pop(0)
    return result


def _compress_micro(messages: List[Dict], max_tokens: int, task_type: str) -> List[Dict]:
    """micro 策略：调用 LLM 对每条非最后消息做一句话摘要。

    最后一条消息（通常是当前问题）保持原样。
    """
    from ..ai_client import AIClient

    if len(messages) <= 1:
        return messages

    # 最后一条消息保留原样
    last_msg = messages[-1]
    history = messages[:-1]

    # 将历史消息合并后请求摘要
    history_text_parts = []
    for i, msg in enumerate(history):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, str):
            history_text_parts.append(f"[{role}]: {content}")

    if not history_text_parts:
        return [last_msg]

    history_text = "\n".join(history_text_parts)

    summary_prompt = (
        "请将以下对话历史用一句话概括其核心内容，"
        "只输出概括句子，不要任何额外说明：\n\n"
        f"{history_text}"
    )

    try:
        ai = AIClient()
        summary = ai.generate(summary_prompt, task="context_compression")
        if isinstance(summary, str) and not summary.startswith("[错误]") and not summary.startswith("[生成失败:"):
            compressed = [{"role": "system", "content": f"[历史摘要] {summary.strip()}"}, last_msg]
            logger.info(f"[上下文压缩] micro 策略：将 {len(history)} 条历史消息压缩为 1 条摘要")
            return compressed
    except Exception as e:
        logger.warning(f"[上下文压缩] micro 压缩失败: {e}")

    # 压缩失败时退回 full 策略
    return _compress_full(messages, max_tokens, task_type)


def _compress_reactive(messages: List[Dict], max_tokens: int, task_type: str) -> List[Dict]:
    """reactive 策略：根据 task_type 自动选择压缩粒度。

    规则:
        - 生成类（generate/writing/draft/chapter）：保留最近 3 轮完整消息 + 更早的摘要
        - 校验类（check/verify/audit/review）：只保留当前上下文（最后一条消息）
        - 其他：保留最近 5 轮 + 更早截断
    """
    if not messages:
        return messages

    # 生成类任务：保留最近 3 轮完整 + 更早摘要
    GENERATION_TASKS = {"generate", "writing", "draft", "chapter", "generation"}
    # 校验类任务：只保留最后一条
    CHECK_TASKS = {"check", "verify", "audit", "review", "auditing"}

    task_lower = task_type.lower().strip()

    if task_lower in CHECK_TASKS:
        # 只保留最后一条消息
        logger.info(f"[上下文压缩] reactive/check 策略：仅保留最后 1 条消息")
        return [messages[-1]]

    if task_lower in GENERATION_TASKS:
        # 保留最近 3 轮（一轮 = user + assistant），再加上更早历史的摘要
        keep_count = min(6, len(messages))  # 3轮 ≈ 6条消息（user+assistant交替）
        recent = messages[-keep_count:]
        older = messages[:-keep_count]

        if not older:
            return messages

        # 对更早的消息做摘要
        from ..ai_client import AIClient

        older_text_parts = []
        for msg in older:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, str):
                older_text_parts.append(f"[{role}]: {content}")

        if older_text_parts:
            older_text = "\n".join(older_text_parts)
            summary_prompt = (
                "请用一句话概括以下对话历史的核心内容，"
                "只输出概括句子，不要任何额外说明：\n\n"
                f"{older_text}"
            )
            try:
                ai = AIClient()
                summary = ai.generate(summary_prompt, task="context_compression")
                if isinstance(summary, str) and not summary.startswith("[错误]") and not summary.startswith("[生成失败:"):
                    logger.info(f"[上下文压缩] reactive/generate 策略：保留最近 {keep_count} 条 + 更早摘要")
                    return [{"role": "system", "content": f"[早期历史摘要] {summary.strip()}"}] + recent
            except Exception as e:
                logger.warning(f"[上下文压缩] reactive 摘要失败: {e}")

        return recent

    # 默认：保留最近 5 轮（10 条消息），超出则从最早截断
    keep_count = min(10, len(messages))
    if len(messages) <= keep_count:
        return messages
    logger.info(f"[上下文压缩] reactive/default 策略：保留最近 {keep_count} 条消息")
    return messages[-keep_count:]


def compress_context(
    messages: List[Dict],
    strategy: str = "reactive",
    max_tokens: int = 4000,
    task_type: str = "general"
) -> List[Dict]:
    """对消息列表应用上下文压缩策略。

    Args:
        messages: 消息列表，每项为 {"role": "...", "content": "..."}
        strategy: 压缩策略
            - "full": 原文返回，超限时截断最早消息
            - "micro": 调用 LLM 将历史消息压缩为一句话摘要
            - "reactive": 根据 task_type 自动选择压缩粒度
        max_tokens: 最大 token 数（粗略估算），默认 4000
        task_type: 任务类型，用于 reactive 策略的选择

    Returns:
        压缩后的消息列表
    """
    if not messages:
        return []

    # P2-2: ctx_layer 三层排除预处理（excluded 丢弃 / archived 合并 / draft 仅生成类保留）
    messages = _apply_ctx_layer(messages, task_type)
    if not messages:
        return []

    strategy_lower = strategy.lower().strip()

    if strategy_lower == "full":
        return _compress_full(messages, max_tokens, task_type)
    elif strategy_lower == "micro":
        return _compress_micro(messages, max_tokens, task_type)
    elif strategy_lower == "reactive":
        return _compress_reactive(messages, max_tokens, task_type)
    else:
        logger.warning(f"[上下文压缩] 未知策略 '{strategy}'，退回 full 策略")
        return _compress_full(messages, max_tokens, task_type)
