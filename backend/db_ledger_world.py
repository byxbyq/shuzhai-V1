# -*- coding: utf-8 -*-
"""ProjectDB 的 Ledger 和 World 持久化方法（从 db.py 拆分）"""
import json
import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def _j(obj) -> str:
    """Python 对象 → JSON 字符串（用于 SQLite TEXT 列）。与 db.py 内同名函数语义一致。"""
    if isinstance(obj, str):
        return obj  # 已经是 JSON 字符串
    return json.dumps(obj, ensure_ascii=False)


def _jd(text, default=None):
    """JSON 字符串 → Python 对象（从 SQLite TEXT 列读回）。与 db.py 内同名函数语义一致。"""
    if not text or text == '':
        return default if default is not None else (text or None)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text  # 可能是纯文本字段（如 outline）


class LedgerWorldMixin:
    """提供 TruthLedger 和 World 设置的持久化方法"""

    def save_ledger(self, ledger_dict: Dict) -> None:
        """保存 TruthLedger 全量数据"""
        pid = self.get_project_id()
        if pid is None:
            return

        with self.transaction() as conn:
            # character_states: 先删后插
            conn.execute("DELETE FROM character_states WHERE project_id=?", (pid,))
            for name, cs in ledger_dict.get("character_states", {}).items():
                conn.execute(
                    """INSERT INTO character_states(project_id, name, location, emotion,
                       health, realm, relationships, possessions, secrets_known,
                       last_seen_chapter, is_alive, arc_stage)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (pid, name, cs.get("location",""), cs.get("emotion",""),
                     cs.get("health","正常"), cs.get("realm",""),
                     _j(cs.get("relationships",{})),
                     _j(cs.get("possessions",[])),
                     _j(cs.get("secrets_known",[])),
                     cs.get("last_seen_chapter",0),
                     int(cs.get("is_alive",True)),
                     cs.get("arc_stage",""))
                )

            # foreshadowing
            conn.execute("DELETE FROM foreshadowing WHERE project_id=?", (pid,))
            for h in ledger_dict.get("foreshadowing", []):
                conn.execute(
                    """INSERT INTO foreshadowing(project_id, hook_id, content,
                       planted_chapter, planted_paragraph, expected_recovery,
                       status, related_characters, related_items,
                       deadline_chapter, recovery_chapter, note,
                       arc_type, strength, hook_type)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (pid, h.get("id",""), h.get("content",""),
                     h.get("planted_chapter",0), h.get("planted_paragraph",""),
                     h.get("expected_recovery_chapter",0),
                     h.get("status","planted"),
                     _j(h.get("related_characters",[])),
                     _j(h.get("related_items",[])),
                     h.get("deadline_chapter",0),
                     h.get("recovery_chapter",0),
                     h.get("note",""),
                     h.get("arc_type",""),
                     h.get("strength",2),
                     h.get("hook_type",""))
                )

            # chapter_logs
            conn.execute("DELETE FROM chapter_logs WHERE project_id=?", (pid,))
            for log in ledger_dict.get("chapter_logs", []):
                conn.execute(
                    """INSERT INTO chapter_logs(project_id, chapter, title, summary,
                       characters, word_count, location, importance,
                       key_choices, costs, new_foreshadowing, resolved_foreshadowing,
                       character_changes, strand_type)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (pid, log.get("chapter",0), log.get("title",""),
                     log.get("summary",""),
                     _j(log.get("characters",[])),
                     log.get("word_count",0),
                     log.get("location",""),
                     log.get("importance","normal"),
                     _j(log.get("key_choices",[])),
                     _j(log.get("costs",[])),
                     _j(log.get("new_foreshadowing",[])),
                     _j(log.get("resolved_foreshadowing",[])),
                     _j(log.get("character_changes",{})),
                     log.get("strand_type",""))
                )

            # artifacts
            conn.execute("DELETE FROM artifacts WHERE project_id=?", (pid,))
            for aid, a in ledger_dict.get("artifacts", {}).items():
                conn.execute(
                    """INSERT INTO artifacts(project_id, artifact_id, name, type,
                       grade, owner, description, created_at, destroyed)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (pid, aid, a.get("name",""), a.get("type",""),
                     a.get("grade",""), a.get("owner",""),
                     a.get("description",""), a.get("created_at",""),
                     int(a.get("destroyed",False)))
                )

            # factions
            conn.execute("DELETE FROM factions WHERE project_id=?", (pid,))
            for fid, f in ledger_dict.get("factions", {}).items():
                conn.execute(
                    """INSERT INTO factions(project_id, faction_id, name, type,
                       leader, members, description, status)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (pid, fid, f.get("name",""), f.get("type",""),
                     f.get("leader",""), _j(f.get("members",[])),
                     f.get("description",""), f.get("status","active"))
                )

            # ledger_locations
            conn.execute("DELETE FROM ledger_locations WHERE project_id=?", (pid,))
            for lid, loc in ledger_dict.get("locations", {}).items():
                conn.execute(
                    """INSERT INTO ledger_locations(project_id, location_id, name,
                       type, description, first_seen_chapter, faction)
                       VALUES(?,?,?,?,?,?,?)""",
                    (pid, lid, loc.get("name",""), loc.get("type",""),
                     loc.get("description",""),
                     loc.get("first_seen_chapter",0),
                     loc.get("faction",""))
                )

            # validation_warnings
            conn.execute("DELETE FROM validation_warnings WHERE project_id=?", (pid,))
            for w in ledger_dict.get("validation_warnings", []):
                conn.execute(
                    """INSERT INTO validation_warnings(project_id, chapter, title,
                       warnings, created_at)
                       VALUES(?,?,?,?,?)""",
                    (pid, w.get("chapter",0), w.get("title",""),
                     _j(w.get("warnings",[])),
                     w.get("created_at",""))
                )

        logger.debug(f"[DB] Ledger 已保存: pid={pid}")

    def load_ledger(self) -> Dict:
        """读取 TruthLedger 全量数据"""
        pid = self.get_project_id()
        if pid is None:
            return {}

        result = {
            "character_states": {},
            "foreshadowing": [],
            "chapter_logs": [],
            "artifacts": {},
            "factions": {},
            "locations": {},
            "validation_warnings": [],
        }

        # character_states → Dict[str, dict]
        for cs in self.query_all(
            "SELECT * FROM character_states WHERE project_id=? ORDER BY name", (pid,)):
            result["character_states"][cs["name"]] = {
                "name": cs["name"], "location": cs["location"],
                "emotion": cs["emotion"], "health": cs["health"],
                "realm": cs["realm"],
                "relationships": _jd(cs["relationships"], default={}),
                "possessions": _jd(cs["possessions"], default=[]),
                "secrets_known": _jd(cs["secrets_known"], default=[]),
                "last_seen_chapter": cs["last_seen_chapter"],
                "is_alive": bool(cs["is_alive"]),
                "arc_stage": cs["arc_stage"],
            }

        # foreshadowing → List[dict]
        for h in self.query_all(
            "SELECT * FROM foreshadowing WHERE project_id=? ORDER BY planted_chapter", (pid,)):
            result["foreshadowing"].append({
                "id": h["hook_id"], "content": h["content"],
                "planted_chapter": h["planted_chapter"],
                "planted_paragraph": h["planted_paragraph"],
                "expected_recovery_chapter": h["expected_recovery"],
                "status": h["status"],
                "related_characters": _jd(h["related_characters"], default=[]),
                "related_items": _jd(h["related_items"], default=[]),
                "deadline_chapter": h["deadline_chapter"],
                "recovery_chapter": h["recovery_chapter"],
                "note": h["note"], "arc_type": h["arc_type"],
                "strength": h["strength"], "hook_type": h["hook_type"],
            })

        # chapter_logs → List[dict]
        for cl in self.query_all(
            "SELECT * FROM chapter_logs WHERE project_id=? ORDER BY chapter", (pid,)):
            result["chapter_logs"].append({
                "chapter": cl["chapter"], "title": cl["title"],
                "summary": cl["summary"],
                "characters": _jd(cl["characters"], default=[]),
                "word_count": cl["word_count"], "location": cl["location"],
                "importance": cl["importance"],
                "key_choices": _jd(cl["key_choices"], default=[]),
                "costs": _jd(cl["costs"], default=[]),
                "new_foreshadowing": _jd(cl["new_foreshadowing"], default=[]),
                "resolved_foreshadowing": _jd(cl["resolved_foreshadowing"], default=[]),
                "character_changes": _jd(cl["character_changes"], default={}),
                "strand_type": cl["strand_type"],
            })

        # artifacts → Dict[str, dict]
        for a in self.query_all(
            "SELECT * FROM artifacts WHERE project_id=?", (pid,)):
            result["artifacts"][a["artifact_id"]] = {
                "id": a["artifact_id"], "name": a["name"],
                "type": a["type"], "grade": a["grade"],
                "owner": a["owner"], "description": a["description"],
                "created_at": a["created_at"],
                "destroyed": bool(a["destroyed"]),
            }

        # factions → Dict[str, dict]
        for f in self.query_all(
            "SELECT * FROM factions WHERE project_id=?", (pid,)):
            result["factions"][f["faction_id"]] = {
                "id": f["faction_id"], "name": f["name"],
                "type": f["type"], "leader": f["leader"],
                "members": _jd(f["members"], default=[]),
                "description": f["description"],
                "status": f["status"],
            }

        # locations → Dict[str, dict]
        for loc in self.query_all(
            "SELECT * FROM ledger_locations WHERE project_id=?", (pid,)):
            result["locations"][loc["location_id"]] = {
                "id": loc["location_id"], "name": loc["name"],
                "type": loc["type"], "description": loc["description"],
                "first_seen_chapter": loc["first_seen_chapter"],
                "faction": loc["faction"],
            }

        # validation_warnings → List[dict]
        for w in self.query_all(
            "SELECT * FROM validation_warnings WHERE project_id=? ORDER BY id DESC LIMIT 20", (pid,)):
            result["validation_warnings"].append({
                "chapter": w["chapter"], "title": w["title"],
                "warnings": _jd(w["warnings"], default=[]),
                "created_at": w["created_at"],
            })

        return result

    # ═══════════════════════════════════════════════════
    # WorldSettings CRUD
    # ═══════════════════════════════════════════════════

    def save_world(self, world_dict: Dict) -> None:
        """保存 WorldSettings 全量数据"""
        pid = self.get_project_id()
        if pid is None:
            return

        # ── 类型保护：防止角色数组/其他不匹配类型写入 world_settings_core ──
        # world_settings 必须是 dict（键值对设定），不能是 list（角色/物品数组）
        _ws = world_dict.get("world_settings", {})
        if not isinstance(_ws, dict):
            logger.warning(
                f"[save_world] 类型异常！world_settings 期望 dict，实际 {type(_ws).__name__}，强制重置为 {{}}"
            )
            _ws = {}
        # freeform 也必须是 dict
        _ff = world_dict.get("freeform", {})
        if not isinstance(_ff, dict):
            _ff = {}
        # narrative_style / era 必须是 dict
        _ns = world_dict.get("narrative_style", {})
        if not isinstance(_ns, dict):
            _ns = {}
        _era = world_dict.get("era", {})
        if not isinstance(_era, dict):
            _era = {}
        # world_rules / forces / locations / items / hard_constraints 必须是 list
        _wr = world_dict.get("world_rules", [])
        if not isinstance(_wr, list):
            _wr = []
        _fc = world_dict.get("forces", [])
        if not isinstance(_fc, list):
            _fc = []
        _loc = world_dict.get("locations", [])
        if not isinstance(_loc, list):
            _loc = []
        _it = world_dict.get("items", [])
        if not isinstance(_it, list):
            _it = []
        _hc = world_dict.get("hard_constraints", [])
        if not isinstance(_hc, list):
            _hc = []

        now = time.strftime("%Y-%m-%d %H:%M")
        with self.transaction() as conn:
            conn.execute(
                """UPDATE world_settings SET
                   magic_system=?, forces=?, world_locations=?, world_items=?,
                   hard_constraints=?, freeform=?, narrative_style=?, era=?,
                   world_rules=?, world_settings_core=?, updated=?
                   WHERE project_id=?""",
                (
                    _j(world_dict.get("magic_system", {})),
                    _j(_fc),
                    _j(_loc),
                    _j(_it),
                    _j(_hc),
                    _j(_ff),
                    _j(_ns),
                    _j(_era),
                    _j(_wr),
                    _j(_ws),
                    now,
                    pid,
                )
            )

    def load_world(self) -> Optional[Dict]:
        """读取 WorldSettings 全量数据"""
        pid = self.get_project_id()
        if pid is None:
            return None

        row = self.query_one("SELECT * FROM world_settings WHERE project_id=?", (pid,))
        if not row:
            return None

        # ── 类型保护：即使DB里存了错误类型，也要矫正后返回，避免内存污染 ──
        def _as_dict(val, default=None):
            if default is None: default = {}
            if isinstance(val, dict): return val
            if isinstance(val, str) and val.strip():
                try:
                    p = json.loads(val)
                    if isinstance(p, dict): return p
                except: pass
            return default

        def _as_list(val, default=None):
            if default is None: default = []
            if isinstance(val, list): return val
            if isinstance(val, str) and val.strip():
                try:
                    p = json.loads(val)
                    if isinstance(p, list): return p
                except: pass
            return default

        return {
            "magic_system": _as_dict(row["magic_system"], default={"name": "", "rules": [], "realms": []}),
            "forces": _as_list(row["forces"]),
            "locations": _as_list(row["world_locations"]),
            "items": _as_list(row["world_items"]),
            "hard_constraints": _as_list(row["hard_constraints"]),
            "freeform": _as_dict(row["freeform"]),
            "narrative_style": _as_dict(row["narrative_style"],
                                        default={"pov":"","tense":"","tone":"","pacing":"","description_style":""}),
            "era": _as_dict(row["era"],
                            default={"tech_level":"","society":"","geography":"","culture":"","social_attitude":""}),
            "world_rules": _as_list(row["world_rules"]),
            "world_settings": _as_dict(row["world_settings_core"]),
        }
