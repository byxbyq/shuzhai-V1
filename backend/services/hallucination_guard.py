# -*- coding: utf-8 -*-
"""P3-2 防幻觉检查（Hallucination Guard）

实体名 + 规范字段 + 归一化值检测，OPEN 状态幂等：
- 实体名检测：正文中出现的与规范实体名编辑距离<=2 的近似片段，
  判定为疑似笔误/幻觉实体（规范名本身出现则跳过）。
- 规范字段检测：正文对已知角色的境界/修为等规范字段给出
  与 TruthLedger 不一致的归一化值时，产出数值失配问题。
- 幂等台账：每个问题按（实体, 类型, 归一化详情）签名，
  OPEN 状态重复检查不重复上报；mark_fixed() 后可再次上报。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class IssueStatus(Enum):
    OPEN = "open"
    FIXED = "fixed"


@dataclass
class HallucinationIssue:
    signature: str
    entity: str
    issue_type: str          # near_miss_name / realm_mismatch
    detail: str
    status: IssueStatus = IssueStatus.OPEN
    first_seen_chapter: int = 0

    def to_dict(self) -> Dict:
        return {
            "signature": self.signature,
            "entity": self.entity,
            "issue_type": self.issue_type,
            "detail": self.detail,
            "status": self.status.value,
            "first_seen_chapter": self.first_seen_chapter,
        }


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein 编辑距离（动态规划，短串专用）"""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[lb]


# 规范字段检测：「角色名+的+境界/修为/等级+是/为/：+值」
_REALM_PATTERN = re.compile(
    r"([\u4e00-\u9fff]{2,6})的(?:境界|修为|等级)\s*(?:是|为|：|:)?\s*([\u4e00-\u9fff\w]{1,10})"
)


def _normalize_value(v: str) -> str:
    """归一化：去空白/标点、统一小写"""
    return re.sub(r"[\s。，,．.、:：\-—]+", "", str(v)).lower()


class HallucinationGuard:
    """防幻觉检查器（进程内幂等台账）"""

    def __init__(self):
        self._ledger: Dict[str, HallucinationIssue] = {}

    # ----------------------------------------------------------
    # 规范索引构建
    # ----------------------------------------------------------

    @staticmethod
    def build_canonical_index(ledger=None, world=None) -> Dict[str, Dict]:
        """从 TruthLedger / WorldSettings 构建规范实体索引。

        返回 {entity_name: {"kind": ..., "realm": ...}}
        """
        index: Dict[str, Dict] = {}
        if ledger is not None:
            for name, cs in getattr(ledger, "character_states", {}).items():
                index[name] = {
                    "kind": "character",
                    "realm": getattr(cs, "realm", "") or "",
                    "is_alive": getattr(cs, "is_alive", True),
                }
        if world is not None:
            for kind, attr in (("force", "forces"), ("location", "locations"), ("item", "items")):
                for entry in getattr(world, attr, []) or []:
                    name = entry.get("name") if isinstance(entry, dict) else None
                    if name:
                        index[name] = {"kind": kind}
        return index

    # ----------------------------------------------------------
    # 主检查入口
    # ----------------------------------------------------------

    def check(self, content: str, ledger=None, world=None,
              chapter_index: int = 0) -> Dict:
        """执行防幻觉检查，返回报告 dict。

        幂等：OPEN 状态的既有问题不重复计入 new_issues。
        """
        if not content:
            return {"ok": True, "new_issues": [], "open_total": 0}

        index = self.build_canonical_index(ledger, world)
        new_issues: List[Dict] = []

        # 1) 近似名检测（疑似笔误/幻觉实体）
        for name, meta in index.items():
            if len(name) < 2 or name in content:
                continue
            hit = self._find_near_miss(content, name)
            if hit:
                issue = self._register(
                    entity=name,
                    issue_type="near_miss_name",
                    detail=f"正文出现疑似笔误「{hit}」，规范名为「{name}」",
                    chapter_index=chapter_index,
                )
                if issue:
                    new_issues.append(issue.to_dict())

        # 2) 规范字段归一化值检测（境界/修为）
        for m in _REALM_PATTERN.finditer(content):
            who, value = m.group(1), m.group(2)
            meta = index.get(who)
            if not meta or meta.get("kind") != "character":
                continue
            canonical = _normalize_value(meta.get("realm", ""))
            stated = _normalize_value(value)
            if canonical and stated and canonical != stated:
                issue = self._register(
                    entity=who,
                    issue_type="realm_mismatch",
                    detail=f"正文称「{who}」境界为「{value}」，台账规范值为「{meta.get('realm')}」",
                    chapter_index=chapter_index,
                )
                if issue:
                    new_issues.append(issue.to_dict())

        open_total = sum(
            1 for i in self._ledger.values() if i.status == IssueStatus.OPEN
        )
        if new_issues:
            logger.info("[hallucination_guard] 新增 %d 项疑似幻觉问题", len(new_issues))
        return {"ok": not new_issues, "new_issues": new_issues, "open_total": open_total}

    # ----------------------------------------------------------
    # 内部工具
    # ----------------------------------------------------------

    @staticmethod
    def _find_near_miss(content: str, name: str, max_dist: int = 2) -> Optional[str]:
        """在正文中查找与规范名编辑距离<=max_dist 的同长片段。

        仅对长度>=2 的名字执行；阈值随名字长度收紧（长度2 距离1）。
        """
        n = len(name)
        dist_cap = 1 if n <= 2 else max_dist
        # 滑动窗口只扫同长片段，复杂度 O(len(content)*n)
        for i in range(len(content) - n + 1):
            seg = content[i:i + n]
            # 快速剪枝：首尾字符至少一个相同才值得算距离
            if seg[0] != name[0] and seg[-1] != name[-1]:
                continue
            if 0 < _edit_distance(seg, name) <= dist_cap:
                return seg
        return None

    def _register(self, entity: str, issue_type: str, detail: str,
                  chapter_index: int) -> Optional[HallucinationIssue]:
        """登记问题；OPEN 状态幂等（重复检查返回 None）"""
        signature = f"{entity}|{issue_type}|{_normalize_value(detail)}"
        existing = self._ledger.get(signature)
        if existing is not None and existing.status == IssueStatus.OPEN:
            return None  # 幂等：不重复上报
        issue = HallucinationIssue(
            signature=signature,
            entity=entity,
            issue_type=issue_type,
            detail=detail,
            status=IssueStatus.OPEN,
            first_seen_chapter=chapter_index,
        )
        self._ledger[signature] = issue
        return issue

    def mark_fixed(self, signature: str) -> bool:
        """将指定问题标记为 FIXED；此后若再次出现可重新上报"""
        issue = self._ledger.get(signature)
        if issue is None:
            return False
        issue.status = IssueStatus.FIXED
        return True

    def open_issues(self) -> List[Dict]:
        return [i.to_dict() for i in self._ledger.values()
                if i.status == IssueStatus.OPEN]

    def to_dict(self) -> Dict:
        return {"issues": [i.to_dict() for i in self._ledger.values()]}


# 模块级默认实例（供 gate 流程与六席位流水线复用）
_default_guard: Optional[HallucinationGuard] = None


def get_default_guard() -> HallucinationGuard:
    global _default_guard
    if _default_guard is None:
        _default_guard = HallucinationGuard()
    return _default_guard
