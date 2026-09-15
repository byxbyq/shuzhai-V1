# -*- coding: utf-8 -*-
"""书斋 V66 - SQLite 存储层

替代 JSON 文件的持久化方案。每个项目目录下生成 project.db，
chapter 正文仍保留为 TXT 文件，向量记忆仍保留为 index.json + vectors.npy。

设计原则：
- SQLite 做主存储，JSON 列存深层嵌套数据（blueprint/assessment 等）
- 事务保证跨表写入的原子性（不再需要 tempfile 原子写入）
- API 层不变——NovelProject/TruthLedger/WorldSettings 内存对象不变，
  只改 _save/_load 的底层实现
"""

import sqlite3
import json
import os
import logging
import time
import threading
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_VERSION = 2  # 用于未来 schema 迁移
# v1→v2: characters 表加 cognitive_boundary/goals 字段

# ═══════════════════════════════════════════════════
# Schema
# ═══════════════════════════════════════════════════

SCHEMA_SQL = """
-- 项目元数据（一行 = 一个项目）
CREATE TABLE IF NOT EXISTS projects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT    NOT NULL DEFAULT '',
    genre           TEXT    DEFAULT '',
    created         TEXT    DEFAULT '',
    modified        TEXT    DEFAULT '',
    current_chapter INTEGER DEFAULT 0,
    total_chapters  INTEGER DEFAULT 0,
    novel_outline   TEXT    DEFAULT '{}',    -- JSON: theme/core_conflict/story_arc...
    brainstorm_cards TEXT   DEFAULT '[]',    -- JSON: 灵感卡片数组
    planning_cards  TEXT    DEFAULT '{"nodes":[],"edges":[],"meta":{}}', -- JSON: 连线框画布数据（节点+连线+元信息）
    world_settings  TEXT    DEFAULT '{}',    -- JSON: 旧格式自由文本设定
    character_settings TEXT DEFAULT '{}',    -- JSON: 角色设定
    db_version      INTEGER DEFAULT {ver}
);

-- 卷结构
CREATE TABLE IF NOT EXISTS volumes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    idx             INTEGER NOT NULL,        -- 卷序号（0-based）
    title           TEXT    DEFAULT '',
    outline         TEXT    DEFAULT '{}',    -- JSON: summary/theme/key_events/character_arcs
    chapter_indices TEXT    DEFAULT '[]',    -- JSON: [1,2,3,...] 章节索引列表
    UNIQUE(project_id, idx)
);

-- 章节元数据
CREATE TABLE IF NOT EXISTS chapters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    idx             INTEGER NOT NULL,        -- 章序号（1-based）
    title           TEXT    DEFAULT '',
    word_count      INTEGER DEFAULT 0,
    created         TEXT    DEFAULT '',
    modified        TEXT    DEFAULT '',
    outline         TEXT    DEFAULT '',      -- 纯文本大纲
    status          TEXT    DEFAULT 'draft', -- draft/final
    pov             TEXT    DEFAULT '',
    scene_labels    TEXT    DEFAULT '[]',    -- JSON
    blueprint       TEXT    DEFAULT '{}',    -- JSON: AI 生成蓝图
    assessment      TEXT    DEFAULT '{}',    -- JSON: AI 评估数据
    locked          INTEGER DEFAULT 0,       -- BOOLEAN
    UNIQUE(project_id, idx)
);

-- 人物档案
CREATE TABLE IF NOT EXISTS characters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name            TEXT    NOT NULL,
    identity        TEXT    DEFAULT '',
    faction         TEXT    DEFAULT '',
    goal            TEXT    DEFAULT '',      -- 旧字段，保留兼容
    goals           TEXT    DEFAULT '[]',    -- JSON: [{text, weight}] 多目标
    appearance      TEXT    DEFAULT '',
    personality     TEXT    DEFAULT '',
    backstory       TEXT    DEFAULT '',
    abilities       TEXT    DEFAULT '',
    relationships   TEXT    DEFAULT '{}',    -- JSON: 关系映射
    arc             TEXT    DEFAULT '',
    cognitive_boundary TEXT DEFAULT '',      -- 认知边界
    extra           TEXT    DEFAULT '{}',    -- JSON: 其他字段
    UNIQUE(project_id, name)
);

-- ═══ TruthLedger ═══

-- 角色运行时状态
CREATE TABLE IF NOT EXISTS character_states (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name            TEXT    NOT NULL,
    location        TEXT    DEFAULT '',
    emotion         TEXT    DEFAULT '',
    health          TEXT    DEFAULT '正常',
    realm           TEXT    DEFAULT '',
    relationships   TEXT    DEFAULT '{}',    -- JSON: Dict[str,str]
    possessions     TEXT    DEFAULT '[]',    -- JSON: List[str]
    secrets_known   TEXT    DEFAULT '[]',    -- JSON: List[str]
    last_seen_chapter INTEGER DEFAULT 0,
    is_alive        INTEGER DEFAULT 1,       -- BOOLEAN
    arc_stage       TEXT    DEFAULT '',
    UNIQUE(project_id, name)
);

-- 伏笔
CREATE TABLE IF NOT EXISTS foreshadowing (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    hook_id         TEXT    NOT NULL,        -- 原始 ID: hook_001_01
    content         TEXT    NOT NULL,
    planted_chapter INTEGER NOT NULL,
    planted_paragraph TEXT  DEFAULT '',
    expected_recovery INTEGER DEFAULT 0,
    status          TEXT    DEFAULT 'planted', -- planted/active/recovered/abandoned
    related_characters TEXT DEFAULT '[]',
    related_items   TEXT    DEFAULT '[]',
    deadline_chapter INTEGER DEFAULT 0,
    recovery_chapter INTEGER DEFAULT 0,
    note            TEXT    DEFAULT '',
    arc_type        TEXT    DEFAULT '',       -- short/medium/long
    strength        INTEGER DEFAULT 2,        -- 1-5
    hook_type       TEXT    DEFAULT '',
    UNIQUE(project_id, hook_id)
);

-- 章节日志
CREATE TABLE IF NOT EXISTS chapter_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    chapter         INTEGER NOT NULL,
    title           TEXT    NOT NULL,
    summary         TEXT    DEFAULT '',
    characters      TEXT    DEFAULT '[]',     -- JSON: List[str]
    word_count      INTEGER DEFAULT 0,
    location        TEXT    DEFAULT '',
    importance      TEXT    DEFAULT 'normal',
    key_choices     TEXT    DEFAULT '[]',
    costs           TEXT    DEFAULT '[]',
    new_foreshadowing TEXT  DEFAULT '[]',
    resolved_foreshadowing TEXT DEFAULT '[]',
    character_changes TEXT DEFAULT '{}',      -- JSON: Dict[str,dict]
    strand_type     TEXT    DEFAULT ''
);

-- 道具/功法
CREATE TABLE IF NOT EXISTS artifacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    artifact_id     TEXT    NOT NULL,         -- 原始 ID
    name            TEXT    NOT NULL,
    type            TEXT    DEFAULT '',
    grade           TEXT    DEFAULT '',
    owner           TEXT    DEFAULT '',
    description     TEXT    DEFAULT '',
    created_at      TEXT    DEFAULT '',
    destroyed       INTEGER DEFAULT 0,
    UNIQUE(project_id, artifact_id)
);

-- 势力/组织
CREATE TABLE IF NOT EXISTS factions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    faction_id      TEXT    NOT NULL,
    name            TEXT    NOT NULL,
    type            TEXT    DEFAULT '',
    leader          TEXT    DEFAULT '',
    members         TEXT    DEFAULT '[]',     -- JSON: List[str]
    description     TEXT    DEFAULT '',
    status          TEXT    DEFAULT 'active',
    UNIQUE(project_id, faction_id)
);

-- 地点（Ledger 内）
CREATE TABLE IF NOT EXISTS ledger_locations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    location_id     TEXT    NOT NULL,
    name            TEXT    NOT NULL,
    type            TEXT    DEFAULT '',
    description     TEXT    DEFAULT '',
    first_seen_chapter INTEGER DEFAULT 0,
    faction         TEXT    DEFAULT '',
    UNIQUE(project_id, location_id)
);

-- 校验警告
CREATE TABLE IF NOT EXISTS validation_warnings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    chapter         INTEGER DEFAULT 0,
    title           TEXT    DEFAULT '',
    warnings        TEXT    DEFAULT '[]',     -- JSON: List[str]
    created_at      TEXT    DEFAULT ''
);

-- ═══ WorldSettings ═══

-- 世界设定（一行 = 一个项目的全部设定）
CREATE TABLE IF NOT EXISTS world_settings (
    project_id      INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    magic_system    TEXT    DEFAULT '{}',     -- JSON
    forces          TEXT    DEFAULT '[]',     -- JSON: [{name,territory,attitude,description}]
    world_locations TEXT    DEFAULT '[]',     -- JSON: [{name,type,description,first_seen_chapter}]
    world_items     TEXT    DEFAULT '[]',     -- JSON: [{name,nature,description,...}]
    hard_constraints TEXT   DEFAULT '[]',     -- JSON: List[str] 或 List[dict]
    freeform        TEXT    DEFAULT '{}',     -- JSON: Dict[str,str]
    narrative_style TEXT    DEFAULT '{}',     -- JSON: {pov,tense,tone,pacing,description_style}
    era             TEXT    DEFAULT '{}',     -- JSON: {tech_level,society,geography,culture}
    world_rules     TEXT    DEFAULT '[]',     -- JSON: List[str]
    world_settings_core TEXT DEFAULT '{}',    -- JSON: 自由格式核心设定
    updated         TEXT    DEFAULT ''
);

-- ═══ 其他 ═══

-- 时间线对照
CREATE TABLE IF NOT EXISTS timeline (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    volume_index    INTEGER NOT NULL,
    chapter_index   INTEGER NOT NULL,
    planned         TEXT    DEFAULT '',
    actual          TEXT    DEFAULT '',
    divergences     TEXT    DEFAULT '[]',
    annotation      TEXT    DEFAULT '',
    last_compared   TEXT    DEFAULT '',
    characters      TEXT    DEFAULT '[]',
    events          TEXT    DEFAULT '[]',
    foreshadowing   TEXT    DEFAULT '{}',
    new_settings    TEXT    DEFAULT '[]',
    bridge          TEXT    DEFAULT '{}',
    UNIQUE(project_id, volume_index, chapter_index)
);

-- 写作统计
CREATE TABLE IF NOT EXISTS writing_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    date            TEXT    NOT NULL,
    words_added     INTEGER DEFAULT 0,
    words_total     INTEGER DEFAULT 0,
    chapters_touched TEXT   DEFAULT '[]',
    UNIQUE(project_id, date)
);

-- 工作流状态
CREATE TABLE IF NOT EXISTS workflow_state (
    project_id      INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    current_step    TEXT    DEFAULT '',
    completed_steps TEXT    DEFAULT '[]',
    step_status     TEXT    DEFAULT '{}',
    updated         TEXT    DEFAULT ''
);

-- 审计日志
CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    ts              TEXT    DEFAULT '',
    action          TEXT    DEFAULT '',
    target          TEXT    DEFAULT '',
    detail          TEXT    DEFAULT '{}'
);

-- 蒸馏摘要
CREATE TABLE IF NOT EXISTS state_memory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    chapter_index   INTEGER NOT NULL,
    distilled_at    TEXT    DEFAULT '',
    characters      TEXT    DEFAULT '[]',
    events          TEXT    DEFAULT '[]',
    foreshadowing   TEXT    DEFAULT '{}',
    new_settings    TEXT    DEFAULT '[]',
    bridge          TEXT    DEFAULT '{}',
    UNIQUE(project_id, chapter_index)
);

-- Schema 版本号（用于迁移检测）
CREATE TABLE IF NOT EXISTS _meta (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);
""".replace("{ver}", str(DB_VERSION))


# ═══════════════════════════════════════════════════
# Connection Manager
# ═══════════════════════════════════════════════════

from backend.db_ledger_world import LedgerWorldMixin

class ProjectDB(LedgerWorldMixin):
    """每个项目的 SQLite 数据库管理器"""

    _instances: Dict[str, "ProjectDB"] = {}
    _lock = threading.RLock()  # 可重入锁，避免 _ensure_schema → connect 死锁

    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.db_path = os.path.join(project_dir, "project.db")
        self._conn: Optional[sqlite3.Connection] = None
        self._conn_lock = threading.RLock()  # 可重入锁

    @classmethod
    def get(cls, project_dir: str) -> "ProjectDB":
        """获取或创建 ProjectDB 实例（单例模式，按 project_dir）"""
        with cls._lock:
            if project_dir not in cls._instances:
                cls._instances[project_dir] = cls(project_dir)
            return cls._instances[project_dir]

    @classmethod
    def release(cls, project_dir: str):
        """释放指定项目目录的 DB 连接"""
        with cls._lock:
            inst = cls._instances.pop(project_dir, None)
            if inst:
                inst.close()

    def connect(self) -> sqlite3.Connection:
        """获取数据库连接（懒初始化，WAL 模式）"""
        with self._conn_lock:
            if self._conn is None:
                os.makedirs(self.project_dir, exist_ok=True)
                self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA foreign_keys=ON")
                self._conn.execute("PRAGMA busy_timeout=5000")
                self._conn.row_factory = sqlite3.Row
                self._ensure_schema()
                logger.info(f"[DB] 已连接: {self.db_path}")
            return self._conn

    def close(self):
        """关闭连接"""
        with self._conn_lock:
            if self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def _ensure_schema(self):
        """确保表结构存在"""
        conn = self.connect()
        conn.executescript(SCHEMA_SQL)
        # 迁移：为旧库补充 planning_cards 列（CREATE TABLE IF NOT EXISTS 不会添加新列）
        try:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(projects)")]
            if 'planning_cards' not in cols:
                conn.execute(
                    "ALTER TABLE projects ADD COLUMN planning_cards TEXT DEFAULT '{\"nodes\":[],\"edges\":[],\"meta\":{}}'"
                )
        except Exception:
            pass
        # v2 迁移：characters 表新增 cognitive_boundary / goals
        try:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(characters)")]
            if 'goals' not in cols:
                conn.execute(
                    "ALTER TABLE characters ADD COLUMN goals TEXT DEFAULT '[]'"
                )
                # 将旧 goal 单目标迁移为多目标格式
                conn.execute(
                    """UPDATE characters SET goals = json_array(
                        json_object('text', goal, 'weight', 1.0)
                    ) WHERE goal != '' AND goals = '[]'"""
                )
            if 'cognitive_boundary' not in cols:
                conn.execute(
                    "ALTER TABLE characters ADD COLUMN cognitive_boundary TEXT DEFAULT ''"
                )
        except Exception:
            pass
        # 写入版本号
        conn.execute(
            "INSERT OR REPLACE INTO _meta(key, value) VALUES('db_version', ?)",
            (str(DB_VERSION),)
        )
        conn.commit()

    @contextmanager
    def transaction(self):
        """事务上下文管理器"""
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        """执行单条 SQL"""
        conn = self.connect()
        return conn.execute(sql, params)

    def executemany(self, sql: str, params_list) -> sqlite3.Cursor:
        """批量执行"""
        conn = self.connect()
        return conn.executemany(sql, params_list)

    def query_one(self, sql: str, params=()) -> Optional[sqlite3.Row]:
        """查询一行"""
        cur = self.execute(sql, params)
        return cur.fetchone()

    def query_all(self, sql: str, params=()) -> List[sqlite3.Row]:
        """查询所有行"""
        cur = self.execute(sql, params)
        return cur.fetchall()

    # ═══════════════════════════════════════════════════
    # Project CRUD
    # ═══════════════════════════════════════════════════

    def create_project(self, title: str, genre: str = "") -> int:
        """创建新项目记录，返回 project_id"""
        now = time.strftime("%Y-%m-%d %H:%M")
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO projects(title, genre, created, modified, novel_outline,
                   brainstorm_cards, world_settings, character_settings, db_version)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (title, genre, now, now, '{}', '[]', '{}', '{}', DB_VERSION)
            )
            pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            # 同时创建 world_settings 行
            conn.execute(
                """INSERT INTO world_settings(project_id, narrative_style, era)
                   VALUES(?, ?, ?)""",
                (pid,
                 json.dumps({"pov":"","tense":"","tone":"","pacing":"","description_style":""}, ensure_ascii=False),
                 json.dumps({"tech_level":"","society":"","geography":"","culture":"","social_attitude":""}, ensure_ascii=False))
            )
            # 创建 workflow_state 行
            conn.execute(
                "INSERT INTO workflow_state(project_id) VALUES(?)",
                (pid,)
            )
        logger.info(f"[DB] 创建项目: id={pid}, title={title}")
        return pid

    def get_project_id(self) -> Optional[int]:
        """获取当前项目的 project_id（每个 DB 只有一个项目）"""
        row = self.query_one("SELECT id FROM projects LIMIT 1")
        return row[0] if row else None

    def save_project_meta(self, data: Dict) -> None:
        """保存 project.json 的全部数据（事务写入）"""
        pid = self.get_project_id()
        if pid is None:
            logger.error("[DB] save_project_meta: 无项目记录")
            return

        meta = data.get("meta", {})
        now = time.strftime("%Y-%m-%d %H:%M")

        with self.transaction() as conn:
            # 更新 projects 主表
            conn.execute(
                """UPDATE projects SET
                   title=?, genre=?, created=?, modified=?, current_chapter=?,
                   total_chapters=?, novel_outline=?, brainstorm_cards=?,
                   planning_cards=?, world_settings=?, character_settings=?, db_version=?
                   WHERE id=?""",
                (
                    meta.get("title", ""),
                    meta.get("genre", ""),
                    meta.get("created", now),
                    now,
                    meta.get("current_chapter", 0),
                    meta.get("total_chapters", 0),
                    _j(data.get("novel_outline", {})),
                    _j(data.get("brainstorm_cards", [])),
                    _j(data.get("planning_cards", {"nodes": [], "edges": [], "meta": {}})),
                    _j(data.get("world_settings", {})),
                    _j(data.get("character_settings", {})),
                    DB_VERSION,
                    pid,
                )
            )

            # 更新 chapters（先删后插，保持与 project.json 的完全同步）
            conn.execute("DELETE FROM chapters WHERE project_id=?", (pid,))
            chapters = data.get("chapters", [])
            if chapters:
                conn.executemany(
                    """INSERT INTO chapters(project_id, idx, title, word_count,
                       created, modified, outline, status, pov, scene_labels,
                       blueprint, assessment, locked)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [(
                        pid,
                        c.get("index", 0),
                        c.get("title", ""),
                        c.get("word_count", 0),
                        c.get("created", ""),
                        c.get("modified", ""),
                        c.get("outline", ""),
                        c.get("status", "draft"),
                        c.get("pov", ""),
                        _j(c.get("scene_labels", [])),
                        _j(c.get("blueprint", {})),
                        _j(c.get("assessment", {})),
                        int(c.get("locked", False)),
                    ) for c in chapters]
                )

            # 更新 volumes
            conn.execute("DELETE FROM volumes WHERE project_id=?", (pid,))
            volumes = data.get("volumes", [])
            if volumes:
                conn.executemany(
                    """INSERT INTO volumes(project_id, idx, title, outline, chapter_indices)
                       VALUES(?,?,?,?,?)""",
                    [(
                        pid,
                        v.get("index", 0),
                        v.get("title", ""),
                        _j(v.get("outline", {})),
                        _j(v.get("chapters", [])),
                    ) for v in volumes]
                )

            # 更新 characters
            conn.execute("DELETE FROM characters WHERE project_id=?", (pid,))
            chars = data.get("characters", [])
            if chars:
                conn.executemany(
                    """INSERT INTO characters(project_id, name, identity, faction, goal, goals,
                       appearance, personality, backstory, abilities, relationships, arc, cognitive_boundary, extra)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [(
                        pid,
                        c.get("name", ""),
                        c.get("identity", ""),
                        c.get("faction", ""),
                        c.get("goal", ""),
                        _j(c.get("goals", [])),
                        c.get("appearance", ""),
                        c.get("personality", ""),
                        c.get("backstory", ""),
                        _j(c.get("abilities", "")),
                        _j(c.get("relationships", {})),
                        c.get("arc", ""),
                        c.get("cognitive_boundary", ""),
                        _j({k: v for k, v in c.items()
                            if k not in ("name","identity","faction","goal","goals",
                                         "appearance","personality","backstory",
                                         "abilities","relationships","arc","cognitive_boundary")}),
                    ) for c in chars]
                )

        logger.debug(f"[DB] 项目元数据已保存: pid={pid}")

    def load_project_meta(self) -> Optional[Dict]:
        """读取项目的全部元数据（等价于原 project.json）"""
        pid = self.get_project_id()
        if pid is None:
            return None

        proj_row = self.query_one("SELECT * FROM projects WHERE id=?", (pid,))
        if not proj_row:
            return None

        # 重建 project.json 格式的 dict
        data = {
            "meta": {
                "title": proj_row["title"],
                "genre": proj_row["genre"],
                "created": proj_row["created"],
                "modified": proj_row["modified"],
                "current_chapter": proj_row["current_chapter"],
                "total_chapters": proj_row["total_chapters"],
            },
            "chapters": [],
            "volumes": [],
            "novel_outline": _jd(proj_row["novel_outline"], default={}),
            "brainstorm_cards": _jd(proj_row["brainstorm_cards"], default=[]),
            "planning_cards": _jd(proj_row["planning_cards"], default={"nodes": [], "edges": [], "meta": {}}) if "planning_cards" in proj_row.keys() else {"nodes": [], "edges": [], "meta": {}},
            "world_settings": _jd(proj_row["world_settings"], default={}),
            "character_settings": _jd(proj_row["character_settings"], default={}),
            "characters": [],
        }

        # chapters
        for ch in self.query_all(
            "SELECT * FROM chapters WHERE project_id=? ORDER BY idx", (pid,)):
            data["chapters"].append({
                "index": ch["idx"],
                "title": ch["title"],
                "word_count": ch["word_count"],
                "created": ch["created"],
                "modified": ch["modified"],
                "outline": ch["outline"],
                "status": ch["status"],
                "pov": ch["pov"],
                "scene_labels": _jd(ch["scene_labels"], default=[]),
                "blueprint": _jd(ch["blueprint"], default={}),
                "assessment": _jd(ch["assessment"], default={}),
                "locked": bool(ch["locked"]),
            })

        # volumes
        for vol in self.query_all(
            "SELECT * FROM volumes WHERE project_id=? ORDER BY idx", (pid,)):
            data["volumes"].append({
                "index": vol["idx"],
                "title": vol["title"],
                "outline": _jd(vol["outline"], default={}),
                "chapters": _jd(vol["chapter_indices"], default=[]),
            })

        # characters
        for char in self.query_all(
            "SELECT * FROM characters WHERE project_id=? ORDER BY id", (pid,)):
            c = {
                "name": char["name"],
                "identity": char["identity"],
                "faction": char["faction"],
                "goal": char["goal"],
                "goals": _jd(char["goals"], default=[]),
                "appearance": char["appearance"],
                "personality": char["personality"],
                "backstory": char["backstory"],
                "abilities": char["abilities"],
                "relationships": _jd(char["relationships"], default=[]),
                "arc": char["arc"],
                "cognitive_boundary": char["cognitive_boundary"] or "",
            }
            # 合入 extra 字段
            extra = _jd(char["extra"], default={})
            if extra:
                c.update(extra)
            data["characters"].append(c)

        return data

    # ═══════════════════════════════════════════════════
    # TruthLedger CRUD
    # ═══════════════════════════════════════════════════


# ═══════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════

def _j(obj) -> str:
    """Python 对象 → JSON 字符串（用于 SQLite TEXT 列）"""
    if isinstance(obj, str):
        return obj  # 已经是 JSON 字符串
    return json.dumps(obj, ensure_ascii=False)

def _jd(text, default=None) -> Any:
    """JSON 字符串 → Python 对象（从 SQLite TEXT 列读回）

    default: 空值时返回的默认值。
      - None (默认) → 返回原始空值（None / ''）
      - dict/list 等 → 返回该默认值
    """
    if not text or text == '':
        return default if default is not None else (text or None)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text  # 可能是纯文本字段（如 outline）

def has_db(project_dir: str) -> bool:
    """检查项目目录下是否已有 project.db"""
    return os.path.exists(os.path.join(project_dir, "project.db"))

def has_json(project_dir: str) -> bool:
    """检查项目目录下是否还有 project.json（用于迁移检测）"""
    return os.path.exists(os.path.join(project_dir, "project.json"))
