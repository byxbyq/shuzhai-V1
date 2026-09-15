# -*- coding: utf-8 -*-
"""书斋 V66 - Truth Ledger: 角色状态 / 伏笔 / 物品追踪"""
import json, os, time, threading
from dataclasses import asdict
from typing import Dict, List, Optional

# 数据模型已拆分到 backend.models.ledger_models，此处保留向后兼容导入
from backend.models.ledger_models import (
    CharacterState, Foreshadowing, ChapterLog,
    Artifact, Faction, Location, SubplotState, Snapshot
)

# 确保这些名称在当前模块命名空间中可用（向后兼容）
__all__ = [
    'CharacterState', 'Foreshadowing', 'ChapterLog',
    'Artifact', 'Faction', 'Location', 'SubplotState', 'Snapshot',
    'TruthLedger',
]


from backend.ledger_snapshot import LedgerSnapshotMixin
from backend.ledger_analysis import LedgerAnalysisMixin

class TruthLedger(LedgerSnapshotMixin, LedgerAnalysisMixin):
    """真相账本 — 跨章持久化唯一事实源"""

    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.character_states: Dict[str, CharacterState] = {}
        self.foreshadowing: List[Foreshadowing] = []
        self.chapter_logs: List[ChapterLog] = []
        self.artifacts: Dict[str, Artifact] = {}
        self.factions: Dict[str, Faction] = {}
        self.locations: Dict[str, Location] = {}
        self.subplots: List[SubplotState] = []  # 支线追踪
        self.audit_feedback: List[Dict] = []  # AI味审计反馈（用于动态引导下一章）
        self.validation_warnings: List[Dict] = []  # 校验警告历史（最近20条）
        self._dirty: bool = False
        self._save_timer: Optional[threading.Timer] = None
        self._debounce_interval: float = 0.5  # 500ms 防抖
        self._save_lock = threading.Lock()
        self._load()

    @property
    def _file(self): return os.path.join(self.project_dir, "truth_ledger.json")

    def _load(self):
        """从 SQLite 加载（优先），回退到 JSON"""
        # 优先：SQLite
        try:
            from backend.db import ProjectDB, has_db
            if has_db(self.project_dir):
                db = ProjectDB.get(self.project_dir)
                d = db.load_ledger()
                if d and d.get("character_states"):
                    self._load_from_dict(d)
                    return
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[Ledger] SQLite 加载失败，回退 JSON: {e}")

        # 回退：JSON
        if os.path.exists(self._file):
            with open(self._file, 'r', encoding='utf-8') as f:
                d = json.load(f)
            self._load_from_dict(d)

    def _load_from_dict(self, d: dict):
        """从 dict 重建内存对象（SQLite 和 JSON 共用）"""
        from dataclasses import fields as dc_fields
        self.character_states = {
            k: CharacterState(**{f: v for f, v in val.items() if f in {x.name for x in dc_fields(CharacterState)}})
            for k, val in d.get("character_states", {}).items()
        }
        fs_fields = {x.name for x in dc_fields(Foreshadowing)}
        self.foreshadowing = [
            Foreshadowing(**{f: v for f, v in h.items() if f in fs_fields})
            for h in d.get("foreshadowing", [])
        ]
        cl_fields = {x.name for x in dc_fields(ChapterLog)}
        self.chapter_logs = [
            ChapterLog(**{f: v for f, v in log.items() if f in cl_fields})
            for log in d.get("chapter_logs", [])
        ]
        art_fields = {x.name for x in dc_fields(Artifact)}
        self.artifacts = {
            k: Artifact(**{f: v for f, v in val.items() if f in art_fields})
            for k, val in d.get("artifacts", {}).items()
        }
        fac_fields = {x.name for x in dc_fields(Faction)}
        self.factions = {
            k: Faction(**{f: v for f, v in val.items() if f in fac_fields})
            for k, val in d.get("factions", {}).items()
        }
        loc_fields = {x.name for x in dc_fields(Location)}
        self.locations = {
            k: Location(**{f: v for f, v in val.items() if f in loc_fields})
            for k, val in d.get("locations", {}).items()
        }
        sub_fields = {x.name for x in dc_fields(SubplotState)}
        self.subplots = [
            SubplotState(**{f: v for f, v in s.items() if f in sub_fields})
            for s in d.get("subplots", [])
        ]
        self.validation_warnings = d.get("validation_warnings", [])
        self.audit_feedback = d.get("audit_feedback", [])

    def save(self):
        """标记脏数据并调度延迟写入（防抖）"""
        self._dirty = True
        with self._save_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
            self._save_timer = threading.Timer(self._debounce_interval, self._do_save)
            self._save_timer.daemon = True
            self._save_timer.start()

    def _do_save(self):
        """真正执行磁盘写入（内部方法）— SQLite 优先，JSON 回退"""
        with self._save_lock:
            if not self._dirty:
                return

            # 构建全量 dict（SQLite 和 JSON 共用）
            data = {
                "character_states": {k: asdict(v) for k, v in self.character_states.items()},
                "foreshadowing": [asdict(h) for h in self.foreshadowing],
                "chapter_logs": [asdict(log) for log in self.chapter_logs],
                "artifacts": {k: asdict(v) for k, v in self.artifacts.items()},
                "factions": {k: asdict(v) for k, v in self.factions.items()},
                "locations": {k: asdict(v) for k, v in self.locations.items()},
                "subplots": [asdict(s) for s in self.subplots],
                "audit_feedback": self.audit_feedback,
                "validation_warnings": self.validation_warnings,
            }

            # 优先写 SQLite
            try:
                from backend.db import ProjectDB, has_db
                if has_db(self.project_dir):
                    db = ProjectDB.get(self.project_dir)
                    db.save_ledger(data)
                    self._dirty = False
                    self._save_timer = None
                    return
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"[Ledger] SQLite 保存失败，回退 JSON: {e}")

            # 回退写 JSON
            try:
                if os.path.exists(self._file):
                    import shutil as _shutil
                    _shutil.copy2(self._file, self._file + '.bak')
            except Exception:
                pass
            data["updated"] = time.strftime("%Y-%m-%d %H:%M")
            with open(self._file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._dirty = False
            self._save_timer = None

    def flush(self):
        """立即写入磁盘（取消定时器并强制执行保存）"""
        with self._save_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None
        if self._dirty:
            self._do_save()

    def close(self):
        """关闭：取消定时器并 flush 确保数据落盘"""
        self.flush()

    def ensure_character(self, name: str):
        if name not in self.character_states:
            self.character_states[name] = CharacterState(name=name)

    def update_character(self, name: str, **kwargs):
        self.ensure_character(name)
        cs = self.character_states[name]
        for k, v in kwargs.items():
            if hasattr(cs, k):
                # 如果字段是list类型，确保传入的也是list
                if isinstance(getattr(cs, k), list):
                    if isinstance(v, str):
                        v = [v]  # 字符串转单元素列表
                    elif not isinstance(v, list):
                        v = [str(v)]
                    getattr(cs, k).extend(v)
                elif isinstance(getattr(cs, k), dict) and isinstance(v, dict):
                    getattr(cs, k).update(v)
                else:
                    setattr(cs, k, v)
        cs.last_seen_chapter = max(cs.last_seen_chapter, kwargs.get("chapter", cs.last_seen_chapter))
        self.save()

    def get_character_summary(self, name: str = None) -> str:
        if name:
            cs = self.character_states.get(name)
            return str(cs) if cs else f"{name}: 无记录"
        lines = []
        for n, cs in self.character_states.items():
            items = ", ".join(cs.possessions) if cs.possessions else "无"
            rels = ", ".join(f"{k}({v})" for k, v in cs.relationships.items()) if cs.relationships else "无"
            lines.append(f"{n}: 位置[{cs.location}] 心绪[{cs.emotion}] 健康[{cs.health}] 境界[{cs.realm}] 持有[{items}] 关系[{rels}] 存活[{cs.is_alive}]")
        return "\n".join(lines)

    def get_state_diff(self, chapter: int) -> str:
        log = next((l for l in self.chapter_logs if l.chapter == chapter), None)
        if not log or not log.character_changes:
            return ""
        diffs = []
        for name, changes in log.character_changes.items():
            diffs.append(f"{name}: " + ", ".join(f"{k}={v}" for k, v in changes.items()))
        return "\n".join(diffs)

    def get_timeline(self, chapter: int = None) -> str:
        """获取时间线数据（从 TimelineService 读取）

        Args:
            chapter: 可选，指定章节索引（0-based）。不传则返回最近5章摘要。
        Returns:
            格式化的时间线文本，或 "无时间线记录" 如果无数据。
        """
        try:
            from backend.timeline_service import TimelineService
            svc = TimelineService(self.project_dir)
            data = svc.get_timeline()
            volumes = data.get("volumes", {})
            if not volumes:
                return "无时间线记录"

            parts = []
            if chapter is not None:
                # 查找指定章节的时间线数据
                for vol_idx, vol_data in volumes.items():
                    chs = vol_data.get("chapters", {})
                    ch_node = chs.get(str(chapter))
                    if ch_node:
                        if ch_node.get("planned"):
                            parts.append(f"计划：{ch_node['planned']}")
                        if ch_node.get("actual"):
                            parts.append(f"实际：{ch_node['actual']}")
                        if ch_node.get("characters"):
                            parts.append("角色变化：" + "; ".join(str(c) for c in ch_node["characters"][:5]))
                        if ch_node.get("events"):
                            parts.append("核心事件：" + "; ".join(str(e) for e in ch_node["events"][:5]))
                        if ch_node.get("bridge", {}).get("from_prev"):
                            parts.append(f"前章衔接：{ch_node['bridge']['from_prev']}")
                        break
            else:
                # 返回最近5章的时间线摘要
                all_chapters = []
                for vol_idx in sorted(volumes.keys(), key=lambda x: int(x) if x.isdigit() else 0):
                    vol_data = volumes[vol_idx]
                    vol_title = vol_data.get("title", "")
                    chs = vol_data.get("chapters", {})
                    for ch_idx in sorted(chs.keys(), key=lambda x: int(x) if x.isdigit() else 0):
                        ch_node = chs[ch_idx]
                        actual = ch_node.get("actual", "")
                        if actual:
                            all_chapters.append((int(ch_idx) if ch_idx.isdigit() else 0, vol_title, actual))
                # 取最近5章
                for ch_idx, vol_title, actual in all_chapters[-5:]:
                    parts.append(f"第{ch_idx}章({vol_title})：{actual[:100]}")

            return "\n".join(parts) if parts else "无时间线记录"
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"get_timeline 失败: {e}")
            return "无时间线记录"

    def add_hook(self, content: str, planted_chapter: int, **kwargs) -> str:
        hid = f"hook_{planted_chapter:03d}_{len(self.foreshadowing)+1:02d}"
        hook = Foreshadowing(id=hid, content=content, planted_chapter=planted_chapter, **kwargs)
        self.foreshadowing.append(hook)
        self.save()
        return hid

    def recover_hook(self, hook_id: str, chapter: int) -> bool:
        for h in self.foreshadowing:
            if h.id == hook_id:
                h.status = "recovered"
                h.recovery_chapter = chapter
                self.save()
                return True
        return False

    def activate_hook(self, hook_id: str) -> bool:
        """激活伏笔：从 planted 变为 active，表示伏笔正在被推进"""
        for h in self.foreshadowing:
            if h.id == hook_id and h.status == "planted":
                h.status = "active"
                self.save()
                return True
        return False

    def abandon_hook(self, hook_id: str, reason: str = "") -> bool:
        for h in self.foreshadowing:
            if h.id == hook_id:
                h.status = "abandoned"
                h.note = reason
                self.save()
                return True
        return False

    def get_active_hooks(self) -> List[Foreshadowing]:
        """获取当前活跃的伏笔（active 状态：正在推进中）"""
        return [h for h in self.foreshadowing if h.status == "active"]

    def get_pending_hooks(self) -> List[Foreshadowing]:
        """获取所有未回收的伏笔（planted + active），用于生成时注入"""
        return [h for h in self.foreshadowing if h.status in ("planted", "active")]

    def activate_nearby_hooks(self, current_chapter: int, window: int = 3) -> int:
        """自动激活临近回收的伏笔：预期回收章节在 current_chapter ± window 内的 planted 伏笔变 active。
        返回激活的数量。"""
        activated = 0
        for h in self.foreshadowing:
            if h.status != "planted":
                continue
            if not h.expected_recovery_chapter:
                continue
            try:
                expected = int(h.expected_recovery_chapter)
            except (ValueError, TypeError):
                continue
            # 当前章节接近预期回收章节（前后 window 章），激活
            if current_chapter >= expected - window and current_chapter <= expected + window:
                h.status = "active"
                activated += 1
        if activated > 0:
            self.save()
        return activated

    def get_overdue_hooks(self, current_chapter: int) -> List[Foreshadowing]:
        overdue = []
        for h in self.get_pending_hooks():
            if h.expected_recovery_chapter:
                try:
                    expected = int(h.expected_recovery_chapter)
                except (ValueError, TypeError):
                    continue
                if current_chapter > expected:
                    overdue.append(h)
        return overdue

    def log_chapter(self, chapter: int, title: str, **kwargs):
        log = ChapterLog(chapter=chapter, title=title, **kwargs)
        self.chapter_logs.append(log)
        self.save()

    def archive_character(self, name: str) -> bool:
        """归档角色：标记为已退场，后续回忆/提及不触发死亡角色校验"""
        if name in self.character_states:
            self.character_states[name].archived = True
            self.character_states[name].is_alive = False
            self.save()
            return True
        return False

    def unarchive_character(self, name: str) -> bool:
        """取消归档：恢复角色为活跃状态"""
        if name in self.character_states:
            self.character_states[name].archived = False
            self.character_states[name].is_alive = True
            self.save()
            return True
        return False

    def get_archived_characters(self) -> List[Dict]:
        """获取所有已归档角色"""
        return [
            {"name": name, "last_seen_chapter": cs.last_seen_chapter,
             "location": cs.location, "realm": cs.realm}
            for name, cs in self.character_states.items()
            if cs.archived
        ]

    # ── 支线追踪 ──────────────────────────────────

    def register_subplot(self, title: str, description: str = "", start_chapter: int = 0,
                         related_characters: List[str] = None, priority: int = 2,
                         target_chapter: int = 0) -> str:
        """注册新支线，返回支线ID"""
        sid = f"subplot_{start_chapter:03d}_{len(self.subplots)+1:02d}"
        sub = SubplotState(
            id=sid, title=title, description=description,
            start_chapter=start_chapter,
            related_characters=related_characters or [],
            priority=priority, target_chapter=target_chapter,
            status="active" if start_chapter > 0 else "dormant",
            last_progress_chapter=start_chapter,
        )
        self.subplots.append(sub)
        self.save()
        return sid

    def update_subplot(self, sub_id: str, chapter: int, event: str = "",
                       status: str = None) -> bool:
        """更新支线状态/推进进度"""
        for s in self.subplots:
            if s.id == sub_id:
                if status:
                    s.status = status
                if event:
                    s.key_events.append(f"第{chapter}章: {event}")
                s.last_progress_chapter = chapter
                if status == "resolved":
                    s.resolve_chapter = chapter
                self.save()
                return True
        return False

    def resolve_subplot(self, sub_id: str, chapter: int) -> bool:
        """标记支线为已解决"""
        return self.update_subplot(sub_id, chapter, status="resolved")

    def abandon_subplot(self, sub_id: str, chapter: int = 0) -> bool:
        """放弃支线"""
        return self.update_subplot(sub_id, chapter, status="abandoned")

    def get_active_subplots(self) -> List[SubplotState]:
        """获取所有活跃/推进中的支线"""
        return [s for s in self.subplots if s.status in ("dormant", "active", "advancing")]

    # ── 别名方法（与规格文档对齐） ──
    def add_subplot(self, *args, **kwargs) -> str:
        """add_subplot 别名（规格文档命名），等价于 register_subplot"""
        return self.register_subplot(*args, **kwargs)

    def get_subplots(self, *args, **kwargs) -> List[SubplotState]:
        """get_subplots 别名（规格文档命名），等价于 get_active_subplots"""
        return self.get_active_subplots(*args, **kwargs)

    def get_subplot_context(self, current_chapter: int) -> str:
        """构建支线上下文文本（注入到 prompt 中）"""
        active = self.get_active_subplots()
        if not active:
            return ""
        # 按优先级排序，高优先级在前
        active.sort(key=lambda s: s.priority)
        lines = []
        for s in active:
            status_label = {"dormant": "潜伏", "active": "启动", "advancing": "推进中"}.get(s.status, s.status)
            gap = current_chapter - s.last_progress_chapter if s.last_progress_chapter > 0 else 0
            gap_warn = f"（⚠️已{gap}章未推进）" if gap > 10 else ""
            line = f"- [{s.id}] {s.title}（{status_label}）{gap_warn}"
            if s.description:
                line += f"\n  描述：{s.description[:60]}"
            if s.related_characters:
                line += f"\n  关联角色：{', '.join(s.related_characters[:5])}"
            if s.key_events:
                last_event = s.key_events[-1]
                line += f"\n  最近进展：{last_event}"
            if s.target_chapter and current_chapter >= s.target_chapter - 3:
                line += f"\n  ⚡目标章节{s.target_chapter}临近，建议尽快收束"
            lines.append(line)
        return "## 支线追踪\n" + "\n".join(lines) if lines else ""

    def build_context(self, current_chapter: int, relevant_characters: List[str] = None, limit_foreshadowing: int = 0) -> str:
        parts = []
        if relevant_characters:
            char_texts = []
            for name in relevant_characters:
                if name in self.character_states:
                    cs = self.character_states[name]
                    items = ", ".join(cs.possessions) if cs.possessions else "无"
                    char_texts.append(
                        f"【{name}】位置:{cs.location} | 心绪:{cs.emotion} | 健康:{cs.health} | "
                        f"境界:{cs.realm} | 持有:{items} | 最后出现:第{cs.last_seen_chapter}章"
                    )
            if char_texts:
                parts.append("## 角色当前状态\n" + "\n".join(char_texts))

        # limit_foreshadowing: 0=不限，>0=只取最近N个
        active = self.get_pending_hooks()
        if active:
            if limit_foreshadowing > 0 and len(active) > limit_foreshadowing:
                active = active[-limit_foreshadowing:]  # 取最近埋下的N个
                label = f"## 待回收伏笔（最近{limit_foreshadowing}个，共{len(self.get_pending_hooks())}个）"
            else:
                label = f"## 待回收伏笔（{len(active)}个）"
            hooks_text = "\n".join(
                f"- [{h.id}] (埋于第{h.planted_chapter}章): {h.content}"
                for h in active
            )
            parts.append(f"{label}\n{hooks_text}")

        # 支线追踪
        subplot_text = self.get_subplot_context(current_chapter)
        if subplot_text:
            parts.append(subplot_text)

        return "\n\n".join(parts) if parts else ""

    def get_stats(self) -> dict:
        # 统计时间线事件数
        timeline_count = 0
        try:
            from backend.timeline_service import TimelineService
            tl_svc = TimelineService(self.project_dir)
            tl_data = tl_svc.get_timeline()
            timeline_count = sum(
                1 for v in tl_data.get("volumes", {}).values()
                for c in v.get("chapters", {}).values()
                if c.get("actual")
            )
        except Exception:
            pass

        return {
            "characters": len(self.character_states),
            "timeline_events": timeline_count,
            "pending_hooks": len(self.get_pending_hooks()),
            "active_hooks": len(self.get_active_hooks()),
            "recovered_hooks": len([h for h in self.foreshadowing if h.status == "recovered"]),
            "abandoned_hooks": len([h for h in self.foreshadowing if h.status == "abandoned"]),
            "chapters_logged": len(self.chapter_logs),
            "artifacts": len(self.artifacts),
            "factions": len(self.factions),
            "locations": len(self.locations),
            "subplots_total": len(self.subplots),
            "subplots_active": len(self.get_active_subplots()),
            "subplots_resolved": len([s for s in self.subplots if s.status == "resolved"]),
            "validation_warnings": len(self.validation_warnings),
        }

    def add_validation_warning(self, chapter: int, title: str, warnings: List[str]):
        """添加一条校验警告（自动保留最近20条）"""
        self.validation_warnings.append({
            "chapter": chapter,
            "title": title,
            "warnings": warnings,
        })
        self.validation_warnings = self.validation_warnings[-20:]
        self.save()

    def store_audit_feedback(self, chapter: int, audit_issues: List[Dict]):
        """存储章节审计反馈，用于下一章的动态去AI味引导"""
        # 提取AI味相关的问题
        ai_issues = [
            {"type": i.get("type", ""), "message": i.get("message", "")}
            for i in audit_issues
            if i.get("type", "") in ("buzzword_forbidden", "ai_flavor", "formulaic",
                                     "character_break", "pov_drift", "logic_gaps")
        ]
        if ai_issues:
            self.audit_feedback.append({"chapter": chapter, "issues": ai_issues})
            self.audit_feedback = self.audit_feedback[-10:]  # 保留最近10章
            self.save()

    def get_audit_feedback(self, chapter: int) -> str:
        """获取指定章节前一章的审计反馈文本（注入到 prompt）"""
        # 找到 chapter 之前最近一条反馈
        prev_feedback = None
        for fb in self.audit_feedback:
            if fb["chapter"] < chapter:
                prev_feedback = fb
            else:
                break
        if not prev_feedback or not prev_feedback.get("issues"):
            return ""
        issues = prev_feedback["issues"]
        lines = [f"上一章（第{prev_feedback['chapter']}章）检测到以下问题，本章请主动避免："]
        for i in issues[:5]:
            lines.append(f"- {i.get('type', '')}: {i.get('message', '')[:80]}")
        return "\n".join(lines)

    def add_event(self, chapter: int, event: str, characters: List[str] = None,
                  location: str = "", importance: str = "normal"):
        """兼容 Novel Engine 的事件记录接口，存入 chapter_logs"""
        log = ChapterLog(
            chapter=chapter,
            title=f"事件: {event[:50]}",
            summary=event,
            characters=characters or [],
            word_count=0,
            location=location,
            importance=importance,
        )
        self.chapter_logs.append(log)
        self.save()

    def to_dict(self) -> dict:
        """序列化所有状态为 dict（兼容 Novel Engine 快照接口）"""
        return {
            "character_states": {k: asdict(cs) for k, cs in self.character_states.items()},
            "foreshadowing": [asdict(f) for f in self.foreshadowing],
            "chapter_logs": [asdict(cl) for cl in self.chapter_logs],
            "artifacts": {k: asdict(a) for k, a in self.artifacts.items()},
            "factions": {k: asdict(f) for k, f in self.factions.items()},
            "locations": {k: asdict(l) for k, l in self.locations.items()},
            "validation_warnings": list(self.validation_warnings),
        }

    @classmethod
    def from_dict(cls, data: dict, project_dir: str = "") -> "TruthLedger":
        """从 dict 反序列化重建实例（兼容 Novel Engine 快照接口）"""
        ledger = cls.__new__(cls)
        ledger.project_dir = project_dir
        ledger._dirty = False
        ledger._save_timer = None
        ledger._debounce_interval = 0.5
        ledger._save_lock = threading.Lock()

        ledger.character_states = {
            k: CharacterState(**v) for k, v in data.get("character_states", {}).items()
        }
        ledger.foreshadowing = [
            Foreshadowing(**h) for h in data.get("foreshadowing", [])
        ]
        ledger.chapter_logs = [
            ChapterLog(**log) for log in data.get("chapter_logs", [])
        ]
        ledger.artifacts = {
            k: Artifact(**v) for k, v in data.get("artifacts", {}).items()
        }
        ledger.factions = {
            k: Faction(**v) for k, v in data.get("factions", {}).items()
        }
        ledger.locations = {
            k: Location(**v) for k, v in data.get("locations", {}).items()
        }
        ledger.validation_warnings = data.get("validation_warnings", [])
        return ledger

    # ═══════════════════════════════════════════
    # 结构化设定库：道具/功法
    # ═══════════════════════════════════════════

    def add_artifact(self, artifact_id: str, name: str, **kwargs):
        """新增或更新道具/功法"""
        art = Artifact(id=artifact_id, name=name, **kwargs)
        self.artifacts[artifact_id] = art
        self.save()

    def update_artifact(self, artifact_id: str, **kwargs):
        if artifact_id in self.artifacts:
            art = self.artifacts[artifact_id]
            for k, v in kwargs.items():
                if hasattr(art, k):
                    setattr(art, k, v)
            self.save()

    def destroy_artifact(self, artifact_id: str):
        if artifact_id in self.artifacts:
            self.artifacts[artifact_id].destroyed = True
            self.save()

    def get_all_artifacts(self) -> list:
        return [asdict(a) for a in self.artifacts.values()]

    # ═══════════════════════════════════════════
    # 结构化设定库：势力/组织
    # ═══════════════════════════════════════════

    def add_faction(self, faction_id: str, name: str, **kwargs):
        fac = Faction(id=faction_id, name=name, **kwargs)
        self.factions[faction_id] = fac
        self.save()

    def update_faction(self, faction_id: str, **kwargs):
        if faction_id in self.factions:
            fac = self.factions[faction_id]
            for k, v in kwargs.items():
                if hasattr(fac, k):
                    setattr(fac, k, v)
            self.save()

    def get_all_factions(self) -> list:
        return [asdict(f) for f in self.factions.values()]

    # ═══════════════════════════════════════════
    # 结构化设定库：地点
    # ═══════════════════════════════════════════

    def add_location(self, location_id: str, name: str, **kwargs):
        """新增或更新地点"""
        loc = Location(id=location_id, name=name, **kwargs)
        self.locations[location_id] = loc
        self.save()

    def update_location(self, location_id: str, **kwargs):
        if location_id in self.locations:
            loc = self.locations[location_id]
            for k, v in kwargs.items():
                if hasattr(loc, k):
                    setattr(loc, k, v)
            self.save()

    def get_all_locations(self) -> list:
        return [asdict(l) for l in self.locations.values()]

    # ═══════════════════════════════════════════
    # H2: 追读力系统 — 量化读者继续阅读的动力
    # ═══════════════════════════════════════════

