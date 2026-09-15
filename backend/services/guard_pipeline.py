"""
统一 Guard 管线（Guard Pipeline）

对标 ProseForge 的 Quality Gate + RuleQualityService 守卫字典模式，
将书斋分散在多个模块的质量检查统一为 FAIL/BLOCK/WARN/INFO 四级管线。

确定性门禁（零 AI 调用）：
- CJK n-gram 复读检测
- 段首重复率检测
- 必含线索命中检查
- 字数下限门禁
- 连续总结式结尾检测

用法：
    pipeline = GuardPipeline()
    pipeline.register_defaults()  # 注册所有内置门禁
    report = pipeline.run(content, context={"min_words": 2500, "required_clues": [...]})
    if report.blocked:
        for issue in report.issues:
            print(issue)
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


# ============================================================
# 数据模型
# ============================================================

class GuardSeverity(Enum):
    """门禁严重级别，与 ProseForge 对齐"""
    BLOCK = "block"   # 硬阻断：必须修复才能继续
    WARN = "warn"     # 警告：记录但允许继续
    INFO = "info"     # 提示：仅记录


@dataclass
class GuardIssue:
    """单条门禁问题"""
    guard_name: str
    severity: GuardSeverity
    message: str
    locations: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GuardReport:
    """门禁报告"""
    passed: bool
    blocked: bool
    issues: List[GuardIssue]
    warn_count: int = 0
    info_count: int = 0

    def __post_init__(self):
        self.warn_count = sum(1 for i in self.issues if i.severity == GuardSeverity.WARN)
        self.info_count = sum(1 for i in self.issues if i.severity == GuardSeverity.INFO)

    def block_issues(self) -> List[GuardIssue]:
        return [i for i in self.issues if i.severity == GuardSeverity.BLOCK]

    def warn_issues(self) -> List[GuardIssue]:
        return [i for i in self.issues if i.severity == GuardSeverity.WARN]

    def to_dict(self) -> Dict:
        return {
            "passed": self.passed,
            "blocked": self.blocked,
            "block_count": len(self.block_issues()),
            "warn_count": self.warn_count,
            "info_count": self.info_count,
            "issues": [
                {
                    "guard": i.guard_name,
                    "severity": i.severity.value,
                    "message": i.message,
                    "locations": i.locations,
                    "details": i.details,
                }
                for i in self.issues
            ],
        }


# ============================================================
# Guard 函数类型
# ============================================================

GuardFunc = Callable[[str, Optional[Dict]], List[GuardIssue]]


# ============================================================
# GuardPipeline
# ============================================================

class GuardPipeline:
    """统一门禁管线

    按注册顺序依次执行所有守卫，收集 Issues 后汇总为 GuardReport。
    出现 BLOCK 级别问题时 passed=False，blocked=True。
    守卫执行异常时自动降级为 WARN 级别记录，不中断管线。
    """

    def __init__(self):
        self._guards: Dict[str, GuardFunc] = {}

    def register(self, name: str, guard_fn: GuardFunc) -> "GuardPipeline":
        """注册一个守卫函数

        Args:
            name: 守卫名称（唯一标识）
            guard_fn: 守卫函数，签名为 (content: str, context: dict | None) -> List[GuardIssue]
        """
        if name in self._guards:
            raise ValueError(f"Guard '{name}' 已注册")
        self._guards[name] = guard_fn
        return self

    def unregister(self, name: str) -> None:
        self._guards.pop(name, None)

    def run(self, content: str, context: Optional[Dict] = None) -> GuardReport:
        """执行全部守卫，返回汇总报告"""
        ctx = context or {}
        all_issues: List[GuardIssue] = []

        for name, guard_fn in self._guards.items():
            try:
                results = guard_fn(content, ctx)
                if isinstance(results, list):
                    all_issues.extend(results)
                elif results is not None:
                    all_issues.append(results)
            except Exception as e:
                all_issues.append(GuardIssue(
                    guard_name=name,
                    severity=GuardSeverity.WARN,
                    message=f"Guard 执行异常: {type(e).__name__}: {e}",
                ))

        blocked = any(i.severity == GuardSeverity.BLOCK for i in all_issues)
        return GuardReport(
            passed=not blocked,
            blocked=blocked,
            issues=all_issues,
        )

    def list_guards(self) -> List[str]:
        return list(self._guards.keys())

    # ----------------------------------------------------------
    # 快捷注册
    # ----------------------------------------------------------

    def register_defaults(self) -> "GuardPipeline":
        """一次性注册所有内置确定性门禁"""
        self.register("cjk_ngram_repeat", check_cjk_ngram_repeat)
        self.register("paragraph_start_repeat", check_paragraph_start_repeat)
        self.register("required_clues", check_required_clues)
        self.register("min_word_count", check_min_word_count)
        self.register("consecutive_summary_endings", check_consecutive_summary_endings)
        return self


# ============================================================
# 内置确定性门禁函数
# ============================================================

# --- CJK n-gram 复读检测 ---

CJK_NGRAM_THRESHOLDS = {4: 8, 5: 6, 6: 5}
"""n-gram 长度 → 最大允许出现次数（超过即阻断）
来源：ProseForge agent_executor.py Quality Gate"""


def check_cjk_ngram_repeat(content: str, context: Optional[Dict] = None) -> List[GuardIssue]:
    """CJK n-gram 复读检测

    检测中文正文中同一连续片段是否被机械重复使用。
    基于纯规则，零 AI 调用，毫秒级完成。

    阈值（ProseForge 标准）：
    - 4 字片段出现 >= 8 次 → BLOCK
    - 5 字片段出现 >= 6 次 → BLOCK
    - 6 字片段出现 >= 5 次 → BLOCK

    虚字/语气串（如 '他的了是'）在统计前已被过滤。
    """
    issues: List[GuardIssue] = []

    # 只取中文汉字，排除标点、空格、英文
    cjk_text = "".join(re.findall(r"[\u4e00-\u9fff]", content))
    if not cjk_text:
        return issues

    # 虚字/语气串过滤：单字占比 > 50% 的 n-gram 不计入复读
    # 常见虚字集合
    function_words = set("的了是在着我他她它这不也还就又和与或但而因为所以如果虽然然而")

    for n, threshold in CJK_NGRAM_THRESHOLDS.items():
        if len(cjk_text) < n:
            continue

        ngrams: Dict[str, int] = {}
        for i in range(len(cjk_text) - n + 1):
            ngram = cjk_text[i:i + n]
            ngrams[ngram] = ngrams.get(ngram, 0) + 1

        # 过滤虚字占比过高的 n-gram（单字虚字占比 > 0.5 不计入）
        violations = []
        for ng, cnt in ngrams.items():
            if cnt >= threshold:
                func_ratio = sum(1 for ch in ng if ch in function_words) / n
                if func_ratio <= 0.5:
                    violations.append((ng, cnt))

        if violations:
            # 按出现次数降序
            violations.sort(key=lambda x: -x[1])
            top_violations = violations[:5]
            examples = "、".join(f'"{ng}"({cnt}次)' for ng, cnt in top_violations)

            issues.append(GuardIssue(
                guard_name="cjk_ngram_repeat",
                severity=GuardSeverity.BLOCK,
                message=f"CJK {n}-gram 复读：{len(violations)} 个片段超阈值（{examples}）",
                details={
                    "n": n,
                    "threshold": threshold,
                    "violation_count": len(violations),
                    "top_violations": [{"ngram": ng, "count": cnt} for ng, cnt in top_violations],
                },
            ))

    return issues


# --- 段首重复率检测 ---

def check_paragraph_start_repeat(content: str, context: Optional[Dict] = None) -> List[GuardIssue]:
    """段首重复率检测

    检测段落开头的 2 字 bigram 是否重复过多，
    反映 AI 写作中常见的"段首模板化"问题。

    阈值（ProseForge 标准）：
    - 重复段首占比 > 40% → WARN
    """
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    if len(paragraphs) < 3:
        return []

    starts = [p[:2] for p in paragraphs if len(p) >= 2]
    if not starts:
        return []

    counter = Counter(starts)
    repeat_count = sum(1 for c in counter.values() if c > 1)
    repeat_ratio = repeat_count / len(starts)

    if repeat_ratio > 0.4:
        top_repeats = counter.most_common(3)
        examples = "、".join(f'"{s}"({c}段)' for s, c in top_repeats)

        return [GuardIssue(
            guard_name="paragraph_start_repeat",
            severity=GuardSeverity.WARN,
            message=f"段首重复率 {repeat_ratio:.1%}，超过 40% 阈值（{examples}）",
            details={
                "ratio": round(repeat_ratio, 3),
                "unique_starts": len(counter),
                "total_paragraphs": len(starts),
                "top_repeats": [{"start": s, "count": c} for s, c in top_repeats],
            },
        )]
    return []


# --- 连续总结式结尾检测 ---

SUMMARY_ENDING_PATTERNS = [
    re.compile(r"总[而言之]"),
    re.compile(r"综[上所述合]"),
    re.compile(r"这一[夜日刻场幕次段].*(?:让|使|令|叫)"),
    re.compile(r"如此.{0,4}(?:结束|落幕|画上)"),
    re.compile(r"在这.{0,6}中.{0,8}(?:明白|懂得|领悟|学会|知道|理解)"),
]


def check_consecutive_summary_endings(content: str, context: Optional[Dict] = None) -> List[GuardIssue]:
    """连续总结式结尾检测

    检测段落是否以"总而言之""这一夜让……"等总结句连续结尾，
    反映 AI 写作中"每段强行总结升华"的腔调。

    阈值（ProseForge 标准）：
    - 连续 >= 3 段总结式结尾 → WARN
    """
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    if len(paragraphs) < 3:
        return []

    # 取每段的最后一句（以句号/感叹号/问号为界）
    def is_summary_ending(para: str) -> bool:
        if not para:
            return False
        sentences = re.split(r"[。！？!?]", para)
        last_sentence = sentences[-1].strip() if sentences else para
        return any(pattern.search(last_sentence) for pattern in SUMMARY_ENDING_PATTERNS)

    endings = [is_summary_ending(p) for p in paragraphs]
    max_consecutive = 0
    current = 0
    for e in endings:
        if e:
            current += 1
            max_consecutive = max(max_consecutive, current)
        else:
            current = 0

    if max_consecutive >= 3:
        return [GuardIssue(
            guard_name="consecutive_summary_endings",
            severity=GuardSeverity.WARN,
            message=f"连续 {max_consecutive} 段总结式结尾，疑似 AI 腔",
            details={
                "consecutive_count": max_consecutive,
                "total_paragraphs": len(paragraphs),
            },
        )]
    return []


# --- 必含线索命中检查 ---

def check_required_clues(content: str, context: Optional[Dict] = None) -> List[GuardIssue]:
    """必含线索命中检查

    检查章节内容是否包含了预设的必含线索。
    支持精确子串匹配和模糊字符覆盖率匹配。

    context 参数：
    - required_clues: List[str] — 必含线索列表
    - clue_match_mode: "exact" | "fuzzy" — 匹配模式（默认 fuzzy）

    阈值（ProseForge 标准）：
    - 精确子串命中 或 模糊片段覆盖率 >= 60% → 命中
    - 全部未命中 → BLOCK
    - 部分未命中 → WARN
    """
    ctx = context or {}
    required_clues = ctx.get("required_clues", [])
    if not required_clues:
        return []

    match_mode = ctx.get("clue_match_mode", "fuzzy")
    hit_count = 0
    missed: List[str] = []

    for clue in required_clues:
        if clue in content:
            hit_count += 1
        elif match_mode == "fuzzy":
            clue_chars = set(clue)
            content_chars = set(content)
            if clue_chars:
                overlap = len(clue_chars & content_chars) / len(clue_chars)
                if overlap >= 0.6:
                    hit_count += 1
                else:
                    missed.append(clue)
            else:
                missed.append(clue)
        else:
            missed.append(clue)

    total = len(required_clues)

    if missed and hit_count == 0:
        return [GuardIssue(
            guard_name="required_clues",
            severity=GuardSeverity.BLOCK,
            message=f"必含线索全部未命中（{total} 条）",
            details={"missed": missed, "hit": 0, "total": total, "mode": match_mode},
        )]
    elif missed:
        return [GuardIssue(
            guard_name="required_clues",
            severity=GuardSeverity.WARN,
            message=f"必含线索 {len(missed)}/{total} 条未命中",
            details={"missed": missed, "hit": hit_count, "total": total, "mode": match_mode},
        )]
    return []


# --- 字数下限门禁 ---

def check_min_word_count(content: str, context: Optional[Dict] = None) -> List[GuardIssue]:
    """字数下限门禁

    纯中文字符计数，检查是否达到最小字数要求。
    仅在 context 显式传入 min_words 时才执行检查。

    context 参数：
    - min_words: int — 最小中文字数（不传则跳过）

    不满足 → BLOCK
    """
    ctx = context or {}
    if "min_words" not in ctx:
        return []  # 未设定则不检查

    min_words = ctx["min_words"]
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", content))

    if cjk_count < min_words:
        return [GuardIssue(
            guard_name="min_word_count",
            severity=GuardSeverity.BLOCK,
            message=f"中文字数 {cjk_count} 未达下限 {min_words}",
            details={"actual": cjk_count, "required": min_words, "shortfall": min_words - cjk_count},
        )]
    return []


# ============================================================
# 工厂函数：创建默认管线
# ============================================================

def create_default_pipeline() -> GuardPipeline:
    """创建并返回已注册全部内置门禁的管线实例"""
    return GuardPipeline().register_defaults()
