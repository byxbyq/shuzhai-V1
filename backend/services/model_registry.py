# -*- coding: utf-8 -*-
"""模型元数据注册表 + 弹性思考强度（书斋自研）

核心职责：
  - 内置各 provider / 模型的真实上下文窗口、max_output、思考强度档位
  - 按任务类型自动决定思考强度（弹性降档/升档），保护结构化输出
  - 供 ai_client 在生成前查询真实窗口，避免 prompt 超窗被截断

设计要点：
  - 注册表为纯数据 + 纯函数，不持有 API Key / 网络状态
  - 弹性思考强度依据任务类型归类：JSON 结构化任务 → 降档（小 JSON 用 low/off）
    正文生成任务 → 升档（thinking=high/enabled 且上调输出预算）
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 模型元数据注册表
# ═══════════════════════════════════════════════════════════════════

# 每项字段：
#   context_window : 真实上下文窗口（token，经调研核实的保守值）
#   max_output     : 单次生成最大输出 token（默认值）
#   thinking       : 思考强度档位：off / low / medium / high / max（模型能力上限）
#   note           : 备注
MODEL_REGISTRY: Dict[str, Dict[str, dict]] = {
    "deepseek": {
        "deepseek-v4": {
            "context_window": 65536,
            "max_output": 8192,
            "thinking": "high",
            "note": "架构/复杂设计主力模型",
        },
        "deepseek-v4-flash": {
            "context_window": 65536,
            "max_output": 8192,
            "thinking": "medium",
            "note": "正文写作/摘要/检查默认模型",
        },
        "deepseek-v3": {
            "context_window": 65536,
            "max_output": 8192,
            "thinking": "off",
            "note": "旧版兼容",
        },
    },
    "openai": {
        "gpt-4o": {
            "context_window": 128000,
            "max_output": 8192,
            "thinking": "off",
            "note": "OpenAI 旗舰",
        },
        "gpt-4o-mini": {
            "context_window": 128000,
            "max_output": 8192,
            "thinking": "off",
            "note": "OpenAI 轻量",
        },
        "gpt-4.1": {
            "context_window": 1047576,
            "max_output": 32768,
            "thinking": "off",
            "note": "超长窗口",
        },
    },
    "doubao": {
        "doubao-pro-32k": {
            "context_window": 32000,
            "max_output": 4096,
            "thinking": "off",
            "note": "豆包 32k",
        },
        "doubao-pro-128k": {
            "context_window": 128000,
            "max_output": 8192,
            "thinking": "off",
            "note": "豆包 128k",
        },
    },
    "kimi": {
        "moonshot-v1-8k": {
            "context_window": 8192,
            "max_output": 4096,
            "thinking": "off",
            "note": "Kimi 8k",
        },
        "moonshot-v1-32k": {
            "context_window": 32768,
            "max_output": 8192,
            "thinking": "off",
            "note": "Kimi 32k",
        },
        "moonshot-v1-128k": {
            "context_window": 131072,
            "max_output": 8192,
            "thinking": "off",
            "note": "Kimi 128k",
        },
    },
    "ollama": {
        "qwen3:14b": {
            "context_window": 32768,
            "max_output": 4096,
            "thinking": "off",
            "note": "本地默认",
        },
        "qwen3:32b": {
            "context_window": 32768,
            "max_output": 8192,
            "thinking": "off",
            "note": "本地增强",
        },
    },
}

# 未知模型兜底元数据（防止查询空指针）
_FALLBACK_META = {
    "context_window": 32768,
    "max_output": 4096,
    "thinking": "off",
    "note": "未注册模型，使用保守兜底值",
}


def get_model_meta(provider: str, model: str) -> dict:
    """查询模型元数据；未注册时返回保守兜底值"""
    provider_map = MODEL_REGISTRY.get(provider, {})
    meta = provider_map.get(model)
    if meta is None:
        return dict(_FALLBACK_META)
    return dict(meta)


def get_context_window(provider: str, model: str) -> int:
    """获取真实上下文窗口（token）"""
    return get_model_meta(provider, model)["context_window"]


def get_max_output(provider: str, model: str) -> int:
    """获取默认最大输出 token"""
    return get_model_meta(provider, model)["max_output"]


def get_thinking_capability(provider: str, model: str) -> str:
    """获取模型思考强度能力上限：off / low / medium / high / max"""
    return get_model_meta(provider, model)["thinking"]


def list_registered_models() -> Dict[str, list]:
    """列出注册表全部模型（供面板展示真实窗口而非拍脑袋值）"""
    out = {}
    for provider, models in MODEL_REGISTRY.items():
        out[provider] = [
            {
                "model": name,
                "context_window": meta["context_window"],
                "max_output": meta["max_output"],
                "thinking": meta["thinking"],
                "note": meta.get("note", ""),
            }
            for name, meta in models.items()
        ]
    return out


def get_registry_overview() -> list:
    """注册表概览（扁平列表，供 /api/stats/models 面板展示）"""
    rows = []
    for provider, models in MODEL_REGISTRY.items():
        for name, meta in models.items():
            rows.append(
                {
                    "provider": provider,
                    "model": name,
                    "context_window": meta["context_window"],
                    "max_output": meta["max_output"],
                    "thinking": meta["thinking"],
                    "note": meta.get("note", ""),
                }
            )
    return rows


def get_provider_models(provider: str):
    """查询指定 provider 的模型清单；未知 provider 返回 None"""
    models = MODEL_REGISTRY.get(provider)
    if models is None:
        return None
    return [
        {
            "model": name,
            "context_window": meta["context_window"],
            "max_output": meta["max_output"],
            "thinking": meta["thinking"],
            "note": meta.get("note", ""),
        }
        for name, meta in models.items()
    ]


# ═══════════════════════════════════════════════════════════════════
# 弹性思考强度
# ═══════════════════════════════════════════════════════════════════

# 任务类型 → 思考档位策略
#   low  : 小型结构化任务（JSON 提取/校验/分类）→ 自动降档，保护结构化输出
#   high : 正文创作/复杂设计 → 自动升档，提升质量
#   auto : 交给模型默认
THINKING_POLICY = {
    # 降档组：小 JSON 任务，思考吃输出预算易破坏 JSON
    "json": "low",
    "check": "low",
    "summary": "low",
    "distill": "low",
    "deconstruct": "low",
    "extract": "low",
    "classify": "low",
    "validate": "low",
    "audit": "low",
    # 升档组：正文/架构/复杂设计
    "writing": "high",
    "architecture": "high",
    "plot": "high",
    "outline": "high",
    "plan": "high",
    # 默认组
    "chat": "medium",
    "general": "medium",
}


def get_thinking_for_task(task_type: str) -> str:
    """按任务类型返回期望思考档位（elastic policy）"""
    return THINKING_POLICY.get(task_type, "medium")


def resolve_thinking(provider: str, model: str, task_type: str,
                     user_thinking: Optional[str] = None) -> str:
    """解析最终思考档位。

    优先级：
      1. 调用方显式指定（user_thinking）→ 不覆盖
      2. 弹性策略（按任务类型）
      3. 模型能力上限（capability）
    """
    if user_thinking:
        return user_thinking
    desired = get_thinking_for_task(task_type)
    capability = get_thinking_capability(provider, model)
    # 能力等级排序：off < low < medium < high < max
    _rank = {"off": 0, "low": 1, "medium": 2, "high": 3, "max": 4}
    if _rank.get(desired, 2) > _rank.get(capability, 0):
        # 模型不支持更高档位，回落到能力上限
        logger.debug(
            "[model_registry] 思考档位 %s 超出 %s/%s 能力 %s，回落",
            desired, provider, model, capability,
        )
        return capability
    return desired


def resolve_output_budget(provider: str, model: str, task_type: str,
                          requested: Optional[int] = None) -> int:
    """解析输出预算。

    正文任务（writing/architecture/plot）自动上调至模型 max_output，
    避免思考 token 抢占正文预算；其余任务取请求值或注册表默认值。
    """
    meta = get_model_meta(provider, model)
    default_budget = meta["max_output"]
    if task_type in ("writing", "architecture", "plot", "outline", "plan"):
        return max(requested or default_budget, default_budget)
    if requested:
        return requested
    return default_budget


def estimate_prompt_tokens(prompt: str) -> int:
    """粗略估算 prompt token 数（中文按 1 字 ≈ 0.6 token，英文按 4 字符 ≈ 1 token）"""
    if not prompt:
        return 0
    cjk = sum(1 for ch in prompt if "\u4e00" <= ch <= "\u9fff")
    other = len(prompt) - cjk
    return int(cjk * 0.6 + other * 0.25)


def check_window_fit(provider: str, model: str, prompt: str,
                     max_output: Optional[int] = None) -> dict:
    """检查 prompt 是否超出真实窗口，返回结构化诊断。

    Returns:
        {
            "provider": str,
            "model": str,
            "context_window": int,
            "prompt_tokens_est": int,
            "output_budget": int,
            "fits": bool,          # 是否安全放入
            "over_by": int,        # 超出 token 数（<=0 表示未超出）
            "suggestion": str,     # 建议
        }
    """
    window = get_context_window(provider, model)
    out_budget = resolve_output_budget(provider, model, "chat", max_output)
    est = estimate_prompt_tokens(prompt)
    total = est + out_budget
    over = total - window
    fits = over <= 0
    suggestion = ""
    if not fits:
        suggestion = (
            f"建议压缩 prompt 约 {over} token，或切换更大窗口模型"
            f"（当前 {window:,} token）"
        )
    return {
        "provider": provider,
        "model": model,
        "context_window": window,
        "prompt_tokens_est": est,
        "output_budget": out_budget,
        "fits": fits,
        "over_by": max(over, 0),
        "suggestion": suggestion,
    }
