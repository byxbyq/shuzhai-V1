"""
有界改写循环 & 上下文分层排除

P2-1 有界改写循环：
- 循环硬上限配置中心
- 问题分类（可修/不可修）
- 停滞检测（连续无改善则退出）
- Token 预算追踪

P2-2 上下文分层排除：
- Layer 枚举：STATIC / SEMI_STATIC / DYNAMIC / REPAIR
- 重试时跳过 STATIC 层，减少 prompt 膨胀

用法：
    loop = RewriteLoop(max_rounds=2, token_budget=32000)
    loop.inject_layer(ContextLayer.STATIC, "世界观设定...")
    loop.inject_layer(ContextLayer.DYNAMIC, "当前时间线...")

    result = loop.run(generate_fn, content_validator)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 上下文分层
# ============================================================

class ContextLayer(Enum):
    """上下文分层枚举，与 ProseForge 对齐"""
    STATIC = auto()       # 不变层：世界观、设定库、全书大纲
    SEMI_STATIC = auto()  # 半静态层：人物档案、伏笔状态
    DYNAMIC = auto()      # 动态层：时间线、向量记忆、蒸馏记忆
    REPAIR = auto()       # 修复层：仅重试时追加


# ============================================================
# 问题分类
# ============================================================

class IssueCategory(Enum):
    """问题分类，决定改写策略"""
    FIXABLE = "fixable"          # 可修：禁词、太短、AI味、段首重复
    HARD = "hard"                # 难修：大纲偏离、角色一致性
    FATAL = "fatal"              # 不可修：死亡角色活跃、逾期伏笔过量
    GUARD = "guard"              # 确定性门禁阻断

    @classmethod
    def classify(cls, issue: Dict[str, Any]) -> "IssueCategory":
        """根据 issue 的 type 字段分类"""
        itype = issue.get("type", "")
        severity = issue.get("severity", "")

        # 确定性门禁
        if itype.startswith("guard_"):
            return cls.GUARD

        # 不可修
        if itype in ("dead_character",):
            return cls.FATAL
        if itype == "overdue_foreshadowing" and severity == "high":
            return cls.FATAL

        # 难修
        if itype in ("outline_deviation", "too_short"):
            return cls.HARD

        # 可修
        return cls.FIXABLE

    @property
    def retryable(self) -> bool:
        """是否值得重试"""
        return self in (IssueCategory.FIXABLE, IssueCategory.HARD)


# ============================================================
# 改写循环配置
# ============================================================

@dataclass
class RewriteConfig:
    """改写循环全局配置

    所有参数可通过 _REWRITE_CONFIG 模块级单例访问。
    """
    max_rounds: int = 2              # 最大改写轮数
    token_budget: int = 32000        # 单轮 Token 预算（模型 max_tokens）
    temperature_base: float = 0.85   # 基础温度
    temperature_decay: float = 0.08  # 每轮温度衰减
    temperature_floor: float = 0.5   # 温度下限
    stagnation_limit: int = 2        # 停滞检测：连续 N 轮无改善则退出
    early_exit_on_unfixable: bool = True  # 仅有不可修问题时提前退出
    strip_static_on_retry: bool = True    # 重试时跳过 STATIC 层


# 模块级配置单例
_REWRITE_CONFIG = RewriteConfig()


def get_rewrite_config() -> RewriteConfig:
    return _REWRITE_CONFIG


def set_rewrite_config(**kwargs) -> RewriteConfig:
    """运行时更新配置"""
    for k, v in kwargs.items():
        if hasattr(_REWRITE_CONFIG, k):
            setattr(_REWRITE_CONFIG, k, v)
    return _REWRITE_CONFIG


# ============================================================
# 改写循环核心
# ============================================================

GenerateFunc = Callable[[str, float], str]
"""生成函数签名：(prompt, temperature) -> content"""

ValidateFunc = Callable[[str], List[Dict[str, Any]]]
"""验证函数签名：(content) -> [{type, description, severity, ...}]"""


@dataclass
class RewriteRound:
    """单轮改写记录"""
    round_index: int
    temperature: float
    content: str
    issues: List[Dict[str, Any]]
    token_used: int
    fixable_count: int
    hard_count: int
    fatal_count: int
    guard_count: int
    improved: bool = False

    @property
    def total_issues(self) -> int:
        return len(self.issues)

    @property
    def all_unfixable(self) -> bool:
        """是否所有问题都不可修（hard + fatal + guard）"""
        return self.fixable_count == 0 and self.total_issues > 0


@dataclass
class RewriteResult:
    """改写循环最终结果"""
    content: str
    rounds: List[RewriteRound]
    final_issues: List[Dict[str, Any]]
    total_tokens: int
    terminated_early: bool
    termination_reason: str = ""
    passed: bool = False

    @property
    def round_count(self) -> int:
        return len(self.rounds)


class RewriteLoop:
    """有界改写循环

    在 max_rounds 内反复生成→验证→分类→决策，支持：
    - 问题分类（可修/难修/不可修/门禁）
    - 停滞检测（连续无改善则退出）
    - Token 预算
    - 温度退火
    - 上下文分层排除
    """

    def __init__(
        self,
        config: Optional[RewriteConfig] = None,
    ):
        self.config = config or get_rewrite_config()
        self._layers: Dict[ContextLayer, List[str]] = {ly: [] for ly in ContextLayer}
        self._repair_notes: List[str] = []

    # --- 上下文分层管理 ---

    def inject_layer(self, layer: ContextLayer, text: str) -> "RewriteLoop":
        """注入一个上下文分层片段"""
        self._layers[layer].append(text)
        return self

    def inject_layers(self, layer: ContextLayer, texts: List[str]) -> "RewriteLoop":
        """批量注入"""
        self._layers[layer].extend(texts)
        return self

    def add_repair_note(self, note: str) -> "RewriteLoop":
        """追加修复指令"""
        self._repair_notes.append(note)
        return self

    def build_prompt(self, round_index: int) -> str:
        """按分层规则构建 prompt

        第 1 轮：全部层
        后续轮：skip STATIC（如果 strip_static_on_retry=True）
        """
        parts: List[str] = []

        is_retry = round_index > 0
        skip_static = is_retry and self.config.strip_static_on_retry

        for layer in ContextLayer:
            if skip_static and layer == ContextLayer.STATIC:
                continue
            if layer == ContextLayer.REPAIR and not is_retry:
                continue  # REPAIR 层仅重试时注入
            for text in self._layers[layer]:
                parts.append(text)

        if is_retry and self._repair_notes:
            parts.append("\n\n【修订指令】\n" + "\n".join(
                f"{i}. {note}" for i, note in enumerate(self._repair_notes, 1)
            ))

        return "\n\n".join(parts)

    # --- 改写循环主逻辑 ---

    def run(
        self,
        generate_fn: GenerateFunc,
        validate_fn: ValidateFunc,
        *,
        build_repair: Optional[Callable[[List[Dict]], str]] = None,
    ) -> RewriteResult:
        """执行有界改写循环

        Args:
            generate_fn: (prompt, temperature) -> content
            validate_fn: (content) -> [{type, description, severity, ...}]
            build_repair: (issues) -> repair_note_str，用于构建修复指令

        Returns:
            RewriteResult
        """
        cfg = self.config
        rounds: List[RewriteRound] = []
        total_tokens = 0
        previous_fixable = float("inf")

        for ri in range(cfg.max_rounds):
            # 温度退火
            temperature = max(
                cfg.temperature_floor,
                cfg.temperature_base - cfg.temperature_decay * ri,
            )

            # 构建 prompt
            prompt = self.build_prompt(ri)

            # 生成
            try:
                content = generate_fn(prompt, temperature)
            except Exception as e:
                logger.error("改写循环第 %d 轮生成失败: %s", ri + 1, e)
                break

            # 验证
            issues = validate_fn(content)

            # 分类统计
            fixable = hard = fatal = guard = 0
            for iss in issues:
                cat = IssueCategory.classify(iss)
                if cat == IssueCategory.FIXABLE:
                    fixable += 1
                elif cat == IssueCategory.HARD:
                    hard += 1
                elif cat == IssueCategory.FATAL:
                    fatal += 1
                elif cat == IssueCategory.GUARD:
                    guard += 1

            # 估算 Token（粗估：prompt 字符数 / 2 + content 字符数 / 2）
            token_estimate = len(prompt) // 2 + len(content) // 2
            total_tokens += token_estimate

            rnd = RewriteRound(
                round_index=ri,
                temperature=temperature,
                content=content,
                issues=issues,
                token_used=token_estimate,
                fixable_count=fixable,
                hard_count=hard,
                fatal_count=fatal,
                guard_count=guard,
                improved=(fixable < previous_fixable),
            )
            rounds.append(rnd)
            previous_fixable = fixable

            # 决策：是否继续？
            high_issues = [i for i in issues if i.get("severity") == "high"]

            # 无 high 问题 → 通过
            if not high_issues:
                return RewriteResult(
                    content=content,
                    rounds=rounds,
                    final_issues=issues,
                    total_tokens=total_tokens,
                    terminated_early=False,
                    termination_reason="all_checks_passed",
                    passed=True,
                )

            # 仅有不可修问题 → 提前退出
            if cfg.early_exit_on_unfixable and rnd.all_unfixable:
                return RewriteResult(
                    content=content,
                    rounds=rounds,
                    final_issues=issues,
                    total_tokens=total_tokens,
                    terminated_early=True,
                    termination_reason="only_unfixable_issues",
                    passed=False,
                )

            # 停滞检测
            if ri >= cfg.stagnation_limit - 1:
                recent = rounds[-cfg.stagnation_limit:]
                if all(not r.improved for r in recent):
                    return RewriteResult(
                        content=content,
                        rounds=rounds,
                        final_issues=issues,
                        total_tokens=total_tokens,
                        terminated_early=True,
                        termination_reason="stagnation_detected",
                        passed=False,
                    )

            # 构建修复指令（如果有提供）
            if build_repair and issues:
                repair_note = build_repair(issues)
                if repair_note:
                    self._repair_notes.append(repair_note)

        # 达到最大轮数
        last = rounds[-1] if rounds else None
        return RewriteResult(
            content=last.content if last else "",
            rounds=rounds,
            final_issues=last.issues if last else [],
            total_tokens=total_tokens,
            terminated_early=False,
            termination_reason="max_rounds_reached",
            passed=not any(
                i.get("severity") == "high" for i in (last.issues if last else [])
            ),
        )

    # --- 批量分类 ---

    @staticmethod
    def classify_issues(issues: List[Dict]) -> Dict[str, List[Dict]]:
        """将问题按类别分组"""
        result: Dict[str, List[Dict]] = {
            "fixable": [],
            "hard": [],
            "fatal": [],
            "guard": [],
        }
        for iss in issues:
            cat = IssueCategory.classify(iss)
            result[cat.value].append(iss)
        return result
