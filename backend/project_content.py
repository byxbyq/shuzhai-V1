# -*- coding: utf-8 -*-
"""书斋 V66 - 内容管理 Mixin（大纲 + 灵感卡片 + 伏笔 + 全书大纲）"""
import os, time, logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class ProjectContentMixin:
    """内容管理 Mixin：outline.txt 读写 + 结构化全书大纲 + 灵感卡片 + 伏笔管理"""

    # ── Outline Text ──

    def get_outline_text(self) -> str:
        """读取 outline.txt 全文"""
        op = os.path.join(self.project_dir, "outline.txt")
        if os.path.exists(op):
            with open(op, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def save_outline_text(self, text: str):
        op = os.path.join(self.project_dir, "outline.txt")
        if os.path.exists(op):
            snap_dir = os.path.join(self.project_dir, "snapshots")
            os.makedirs(snap_dir, exist_ok=True)
            import shutil
            shutil.copy2(op, os.path.join(snap_dir,
                f"outline_{time.strftime('%Y%m%d_%H%M%S')}.txt"))
        with open(op, "w", encoding="utf-8") as f:
            f.write(text)

    # ── 结构化全书大纲 ──

    def set_novel_outline(self, outline_data: Dict):
        """保存结构化全书大纲（dict格式：theme/core_conflict/story_arc/...）"""
        self.novel_outline = outline_data if isinstance(outline_data, dict) else {}
        self._dirty = True
        self._save_meta()

    def get_novel_outline(self) -> Dict:
        """获取结构化全书大纲"""
        return self.novel_outline

    # ── 灵感卡片 ──

    def set_brainstorm_cards(self, cards: List[Dict]):
        """保存灵感卡片"""
        self.brainstorm_cards = cards
        self._dirty = True
        self._save_meta()

    def get_brainstorm_cards(self) -> List[Dict]:
        """获取灵感卡片"""
        return self.brainstorm_cards

    # ── 连线框画布（planning_cards）──

    def set_planning_cards(self, data: Dict):
        """保存连线框画布数据（nodes/edges/meta）"""
        if not isinstance(data, dict):
            data = {"nodes": [], "edges": [], "meta": {}}
        # 结构校验
        data.setdefault("nodes", [])
        data.setdefault("edges", [])
        data.setdefault("meta", {})
        self.planning_cards = data
        self._dirty = True
        self._save_meta()

    def get_planning_cards(self) -> Dict:
        """获取连线框画布数据"""
        pc = getattr(self, 'planning_cards', None)
        if not isinstance(pc, dict):
            return {"nodes": [], "edges": [], "meta": {}}
        pc.setdefault("nodes", [])
        pc.setdefault("edges", [])
        pc.setdefault("meta", {})
        return pc

    # ── 伏笔全生命周期管理（委托给 TruthLedger）──

    def get_hooks(self) -> list:
        from dataclasses import asdict
        return [asdict(h) for h in self.ledger.foreshadowing] if self.ledger else []

    def add_hook(self, content: str, chapter_index: int, status: str = "planned") -> dict:
        from dataclasses import asdict
        if not self.ledger:
            logger.warning("add_hook: ledger is None, skipping")
            return {}
        mapped_status = "planted" if status == "planned" else status
        hid = self.ledger.add_hook(content, chapter_index, status=mapped_status)
        hook = next((h for h in self.ledger.foreshadowing if h.id == hid), None)
        return asdict(hook) if hook else {"id": hid, "content": content}

    def advance_hook(self, hook_id: str, chapter_index: int):
        if not self.ledger:
            logger.warning("advance_hook: ledger is None, skipping")
            return
        for h in self.ledger.foreshadowing:
            if h.id == hook_id:
                if h.status == "planted":
                    h.status = "active"
                self.ledger.save()
                break

    def recover_hook(self, hook_id: str, chapter_index: int):
        if not self.ledger:
            logger.warning("recover_hook: ledger is None, skipping")
            return
        self.ledger.recover_hook(hook_id, chapter_index)

    def check_overdue_hooks(self, current_chapter: int) -> list:
        from dataclasses import asdict
        if not self.ledger:
            return []
        overdue = self.ledger.get_overdue_hooks(current_chapter)
        return [asdict(h) for h in overdue]