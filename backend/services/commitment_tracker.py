"""
动态承诺台账（Commitment Tracker）

P2-4: 对 AI 生成过程中主动声明的叙事承诺进行登记、追踪、兑现校验。

承诺来源：
- "接下来……"（Next-Action 承诺）
- "准备……"（Prepared-Action 承诺）
- "打算……"（Intent 承诺）
- "将在第X章……"（Timed 承诺）
- "等……再……"（Conditional 承诺）

状态生命周期：
    DECLARED → FULFILLED  (已兑现)
    DECLARED → VOIDED     (已作废/冲突)
    DECLARED → OVERDUE    (逾期未兑现)

用法：
    tracker = CommitmentTracker()
    # 生成后扫描内容
    commitments = tracker.scan(content)
    tracker.register_batch(commitments, chapter_index)
    # 下次生成前检查
    pending = tracker.get_pending(chapter_index)
    overdue = tracker.get_overdue(chapter_index)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ============================================================
# 数据模型
# ============================================================

class CommitmentStatus(Enum):
    DECLARED = "declared"    # 已声明
    FULFILLED = "fulfilled"  # 已兑现
    VOIDED = "voided"        # 已作废
    OVERDUE = "overdue"      # 逾期


@dataclass
class Commitment:
    """单条叙事承诺"""
    id: str                          # 唯一 ID
    text: str                        # 承诺原文片段
    source_chapter: int              # 来源章节
    target_chapter: Optional[int] = None  # 目标章节（如有明确指向）
    status: CommitmentStatus = CommitmentStatus.DECLARED
    confidence: float = 0.5          # 置信度 0-1
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    fulfilled_at: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Commitment":
        d = dict(d)
        d["status"] = CommitmentStatus(d["status"])
        return cls(**d)


# ============================================================
# 承诺识别规则
# ============================================================

# 承诺触发模式：(正则, 类型标签, 置信度)
COMMITMENT_PATTERNS: List[tuple] = [
    # 时序承诺
    (r"(?:接下来|接下来就|下一章|下一回|下次|日后|之后)(?:.{0,20})(?:会|要|将|便|就|定要|一定要)(.{5,60})",
     "next_chapter", 0.75),
    # 意图承诺
    (r"(?:准备|打算|计划|决定|决心|立志)(?:.{0,10})(.{5,50})",
     "intent", 0.60),
    # 条件承诺
    (r"(?:等|等到|待|等到了|等……之后|等……以后|倘若|如果) .{3,15} (?:再|就|便)(.{5,50})",
     "conditional", 0.50),
    # 人物行动承诺
    (r"(?:定要|一定会|必定|势必|必然|必须)(.{5,40})",
     "determined_action", 0.55),
    # 揭示/揭露承诺
    (r"(?:终于要|即将|很快|马上)(?:揭开|揭示|揭晓|露出|暴露|显露|展示|展现)(.{5,40})",
     "revelation", 0.65),
]


def scan_commitments(content: str, chapter_index: int) -> List[Commitment]:
    """从生成内容中扫描叙事承诺

    Args:
        content: 生成的章节正文
        chapter_index: 当前章节索引（0-based）

    Returns:
        识别到的承诺列表
    """
    commitments: List[Commitment] = []
    seen_texts: set = set()

    for idx, (pattern, ctype, confidence) in enumerate(COMMITMENT_PATTERNS):
        for match in re.finditer(pattern, content):
            full_match = match.group(0).strip()

            # 去重
            if full_match in seen_texts:
                continue
            seen_texts.add(full_match)

            # 过滤过短或无意义片段
            if len(full_match) < 8:
                continue

            commitments.append(Commitment(
                id=f"cmt_{chapter_index}_{ctype}_{idx}_{len(commitments)}",
                text=full_match,
                source_chapter=chapter_index,
                confidence=confidence,
            ))

    return commitments


# ============================================================
# 承诺台账
# ============================================================

class CommitmentTracker:
    """动态承诺台账

    管理跨章节的叙事承诺生命周期。
    支持声明、兑现、作废、逾期检测。
    """

    def __init__(self):
        self._commitments: Dict[str, Commitment] = {}
        self._by_chapter: Dict[int, List[str]] = {}  # chapter_index → [commitment_id]

    # --- 注册 ---

    def register(self, commitment: Commitment) -> None:
        """注册单条承诺"""
        self._commitments[commitment.id] = commitment
        ch = commitment.source_chapter
        if ch not in self._by_chapter:
            self._by_chapter[ch] = []
        self._by_chapter[ch].append(commitment.id)

    def register_batch(self, commitments: List[Commitment], chapter_index: int) -> int:
        """批量注册，返回登记数量"""
        count = 0
        for cmt in commitments:
            cmt.source_chapter = chapter_index
            self.register(cmt)
            count += 1
        return count

    # --- 查询 ---

    def get_pending(self, up_to_chapter: int) -> List[Commitment]:
        """获取截至指定章节未兑现的承诺"""
        pending = []
        for ch in self._by_chapter:
            if ch > up_to_chapter:
                continue
            for cid in self._by_chapter.get(ch, []):
                cmt = self._commitments.get(cid)
                if cmt and cmt.status == CommitmentStatus.DECLARED:
                    pending.append(cmt)
        return pending

    def get_overdue(self, current_chapter: int, grace_period: int = 2) -> List[Commitment]:
        """获取逾期承诺（声明后超过 grace_period 章未兑现）"""
        overdue = []
        for cid, cmt in self._commitments.items():
            if cmt.status != CommitmentStatus.DECLARED:
                continue
            if (current_chapter - cmt.source_chapter) > grace_period:
                cmt.status = CommitmentStatus.OVERDUE
                overdue.append(cmt)
        return overdue

    def get_by_chapter(self, chapter_index: int) -> List[Commitment]:
        """获取指定章节的承诺"""
        return [
            self._commitments[cid]
            for cid in self._by_chapter.get(chapter_index, [])
            if cid in self._commitments
        ]

    # --- 状态变更 ---

    def fulfill(self, commitment_id: str) -> bool:
        """标记承诺已兑现"""
        cmt = self._commitments.get(commitment_id)
        if cmt and cmt.status == CommitmentStatus.DECLARED:
            cmt.status = CommitmentStatus.FULFILLED
            cmt.fulfilled_at = datetime.now().isoformat()
            return True
        return False

    def void(self, commitment_id: str, reason: str = "") -> bool:
        """作废承诺（设定冲突/作者否决）"""
        cmt = self._commitments.get(commitment_id)
        if cmt:
            cmt.status = CommitmentStatus.VOIDED
            cmt.notes = reason
            return True
        return False

    def check_fulfillment(self, content: str, current_chapter: int) -> List[Commitment]:
        """检查当前章节是否兑现了之前的承诺（模糊匹配）"""
        fulfilled = []
        for cid, cmt in self._commitments.items():
            if cmt.status != CommitmentStatus.DECLARED:
                continue
            # 用承诺文本的前 8 个字符做模糊匹配
            key = cmt.text[:8]
            if key in content:
                self.fulfill(cid)
                fulfilled.append(cmt)
        return fulfilled

    # --- 序列化 ---

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commitments": {cid: cmt.to_dict() for cid, cmt in self._commitments.items()},
            "by_chapter": {str(k): v for k, v in self._by_chapter.items()},
        }

    def to_list(self) -> List[Dict[str, Any]]:
        return [cmt.to_dict() for cmt in self._commitments.values()]

    # --- 承诺上下文（供 prompt 注入） ---

    def get_context_for_chapter(self, chapter_index: int, max_items: int = 5) -> str:
        """生成用于 prompt 注入的承诺上下文文本"""
        pending = self.get_pending(chapter_index)
        if not pending:
            return ""

        lines = ["\n\n【叙事承诺提醒 — 以下承诺待兑现】"]
        for cmt in pending[:max_items]:
            age = chapter_index - cmt.source_chapter
            lines.append(f"- [第{cmt.source_chapter + 1}章声明，已过{age}章] {cmt.text}")
        if len(pending) > max_items:
            lines.append(f"... 还有 {len(pending) - max_items} 条待兑现承诺")

        return "\n".join(lines)
