# -*- coding: utf-8 -*-
"""书斋 V66 - 项目基础设施（路径安全、构造、持久化、项目管理）

SQLite 存储层：project.json / truth_ledger.json / world_meta.json → project.db
章节正文仍保留为 TXT 文件。
"""
import os, sys, json, time, logging, glob as _glob, tempfile
from typing import Optional, List, Dict, TYPE_CHECKING

if TYPE_CHECKING:  # 仅类型标注用：NovelProject 是子类（backend/project.py），运行期导入会循环
    from backend.project import NovelProject

logger = logging.getLogger(__name__)

# SQLite 存储层
from backend.db import ProjectDB, has_db


def _sync_world_to_ledger(world, ledger):
    """WorldSettings → TruthLedger 单向初始化同步

    只在 ledger 对应字段为空时才同步，避免覆盖已有数据。
    同步内容：forces → factions, items → artifacts, locations → locations
    """
    from backend.ledger import Faction, Artifact, Location

    synced_forces = 0
    synced_items = 0
    synced_locations = 0

    # 1. forces → factions（仅当 ledger.factions 为空时）
    if not ledger.factions and world.forces:
        for idx, force in enumerate(world.forces):
            name = force.get('name', '')
            if not name:
                continue
            fid = f"faction_init_{idx:03d}"
            desc_parts = []
            if force.get('territory'):
                desc_parts.append(f"领地: {force['territory']}")
            if force.get('attitude'):
                desc_parts.append(f"态度: {force['attitude']}")
            if force.get('description'):
                desc_parts.append(force['description'])
            ledger.factions[fid] = Faction(
                id=fid,
                name=name,
                type=force.get('attitude', ''),
                description=' | '.join(desc_parts),
                status='active'
            )
            synced_forces += 1

    # 2. items → artifacts（仅当 ledger.artifacts 为空时）
    if not ledger.artifacts and world.items:
        for idx, item in enumerate(world.items):
            name = item.get('name', '')
            if not name:
                continue
            aid = f"artifact_init_{idx:03d}"
            ledger.artifacts[aid] = Artifact(
                id=aid,
                name=name,
                type=item.get('nature', ''),
                description=item.get('description', ''),
                destroyed=False
            )
            synced_items += 1

    # 3. locations → locations（仅当 ledger.locations 为空时）
    if hasattr(ledger, 'locations') and not ledger.locations and world.locations:
        for idx, loc in enumerate(world.locations):
            name = loc.get('name', '')
            if not name:
                continue
            lid = f"location_init_{idx:03d}"
            ledger.locations[lid] = Location(
                id=lid,
                name=name,
                type=loc.get('type', ''),
                description=loc.get('description', ''),
                first_seen_chapter=loc.get('first_seen_chapter', 0) or 0,
                faction=''
            )
            synced_locations += 1

    # 如果有任何同步，标记为脏数据并保存
    if synced_forces > 0 or synced_items > 0 or synced_locations > 0:
        ledger.save()
        logger.info(f"[WorldSync] 已从 WorldSettings 同步到 Ledger: "
                   f"势力{synced_forces}个, 物品{synced_items}个, 地点{synced_locations}个")


class ProjectBaseMixin:
    """基础设施 Mixin：路径安全 + 原子写入 + 构造 + 持久化 + 项目创建/打开/列表"""

    # ── 静态工具方法 ──

    @staticmethod
    def _get_base_dir():
        """动态获取项目目录（支持用户隔离）"""
        from backend.runtime_paths import get_projects_dir
        return get_projects_dir()

    @staticmethod
    def _sanitize(name: str) -> str:
        import re
        s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip().strip('.')
        s = re.sub(r'\.\.+', '_', s)
        s = s.lstrip('/\\')
        return s[:50] if s else "untitled"

    @staticmethod
    def _is_safe_path(base_dir: str, target_path: str) -> bool:
        try:
            base_real = os.path.realpath(base_dir)
            target_real = os.path.realpath(target_path)
            common = os.path.commonpath([base_real, target_real])
            return common == base_real
        except Exception:
            return False

    @staticmethod
    def _cleanup_versioned_backups(file_path: str, keep: int = 3) -> None:
        """清理版本备份文件，只保留最近N个"""
        try:
            pattern = file_path + '.bak_*'
            baks = sorted(_glob.glob(pattern), reverse=True)
            for old_bak in baks[keep:]:
                try:
                    os.unlink(old_bak)
                except Exception:
                    pass
        except Exception:
            pass

    @staticmethod
    def _atomic_write_json(file_path: str, data) -> None:
        dir_path = os.path.dirname(file_path)
        os.makedirs(dir_path, exist_ok=True)
        raw = json.dumps(data, ensure_ascii=False, indent=2)
        if not raw or raw.strip() == '':
            raise ValueError("Cannot write empty JSON data")

        # 写入临时文件（同一目录确保同文件系统）
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix=".tmp_", suffix=".json", dir=dir_path
        )
        try:
            with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass
            raise

        # 替换目标文件，Windows 上可能需要重试
        bak_path = file_path + ".bak"
        last_err = None
        for attempt in range(5):
            try:
                # 先备份旧文件
                if os.path.exists(file_path):
                    try:
                        import shutil as _shutil
                        _shutil.copy2(file_path, bak_path)
                    except Exception:
                        pass
                os.replace(tmp_path, file_path)
                # 验证写入结果
                sz = os.path.getsize(file_path)
                if sz < 10:
                    raise IOError(f"写入后文件过小: {sz} bytes")
                # 保留.bak作为即时安全网（不删除）
                # 创建带时间戳的版本备份（保留最近3个）
                try:
                    import shutil as _shutil
                    from datetime import datetime as _dt
                    ts = _dt.now().strftime('%Y%m%d_%H%M%S')
                    ver_bak = file_path + f'.bak_{ts}'
                    _shutil.copy2(file_path, ver_bak)
                    ProjectBaseMixin._cleanup_versioned_backups(file_path)
                except Exception:
                    pass
                return
            except PermissionError as e:
                last_err = e
                import time as _time
                _time.sleep(0.3 * (attempt + 1))
            except Exception as e:
                last_err = e
                break

        # 所有重试失败，用新的临时文件再 replace
        tmp2_path = None
        try:
            tmp2_fd, tmp2_path = tempfile.mkstemp(
                prefix=".tmp2_", suffix=".json", dir=dir_path
            )
            with os.fdopen(tmp2_fd, 'w', encoding='utf-8') as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp2_path, file_path)
            logger.info("兜底写入成功: %s", file_path)
        except Exception as e2:
            logger.error("所有写入方式均失败: %s, err1=%s, err2=%s", file_path, last_err, e2)
            if tmp2_path and os.path.exists(tmp2_path):
                try:
                    os.unlink(tmp2_path)
                except Exception:
                    pass
            raise
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass

    # ── 构造 ──

    def _init_project_fields(self):
        """初始化所有项目字段（由 __init__ 调用）"""
        self.project_dir = ""
        self._db: Optional[ProjectDB] = None  # SQLite 存储层
        self.meta = {
            "title": "未命名小说",
            "genre": "",
            "created": time.strftime("%Y-%m-%d %H:%M"),
            "modified": time.strftime("%Y-%m-%d %H:%M"),
            "current_chapter": 0,
            "total_chapters": 0
        }
        self.chapters: List[Dict] = []
        self.volumes: List[Dict] = []
        self.novel_outline: Dict = {}  # 全书大纲（dict格式：theme/core_conflict/story_arc/...）
        self.brainstorm_cards: List[Dict] = []
        self.planning_cards: Dict = {"nodes": [], "edges": [], "meta": {}}  # 连线框画布数据
        self.world_settings: Dict = {}
        self.character_settings: Dict = {}
        self.characters: list = []
        self._chapter_cache: Dict[int, str] = {}
        self._snapshot_cache: Optional[list] = None
        self._dirty = False
        self.ledger = None

    # ── 持久化（SQLite）──

    def _get_db(self) -> ProjectDB:
        """获取当前项目的 SQLite 数据库管理器"""
        if self._db is None:
            self._db = ProjectDB.get(self.project_dir)
        return self._db

    def _save_meta(self):
        """保存项目元数据到 SQLite（事务写入）"""
        self.meta["modified"] = time.strftime("%Y-%m-%d %H:%M")
        db = self._get_db()
        # 如果还没有 project_id，先创建项目记录
        pid = db.get_project_id()
        if pid is None:
            pid = db.create_project(
                title=self.meta.get("title", "未命名"),
                genre=self.meta.get("genre", ""),
            )
        # 全量写入
        data = {
            "meta": self.meta,
            "chapters": self.chapters,
            "volumes": self.volumes,
            "novel_outline": self.novel_outline,
            "brainstorm_cards": self.brainstorm_cards,
            "planning_cards": self.planning_cards,
            "world_settings": self.world_settings,
            "character_settings": self.character_settings,
            "characters": self.characters,
        }
        db.save_project_meta(data)
        self._dirty = False

    def save_all(self):
        self._save_meta()
        if self.ledger:
            self.ledger.flush()

    # ── 项目管理 ──

    @classmethod
    def create(cls, title: str, genre: str = "") -> "NovelProject":
        from backend.ledger import TruthLedger
        slug = cls._sanitize(title)
        proj_dir = os.path.join(cls._get_base_dir(), slug)
        logger.info(f"[ProjectBase] 创建项目: title='{title}', dir={proj_dir}")
        proj = cls()
        proj._init_project_fields()
        proj.project_dir = proj_dir
        proj.meta["title"] = title
        proj.meta["genre"] = genre
        os.makedirs(proj.project_dir, exist_ok=True)
        os.makedirs(os.path.join(proj.project_dir, "chapters"), exist_ok=True)
        os.makedirs(os.path.join(proj.project_dir, "snapshots"), exist_ok=True)
        # SQLite: 创建项目记录
        db = proj._get_db()
        db.create_project(title=title, genre=genre)
        proj._save_meta()
        proj.ledger = TruthLedger(proj.project_dir)
        logger.info(f"[ProjectBase] 项目创建成功: {proj_dir}")
        return proj

    @classmethod
    def open(cls, project_dir: str) -> Optional["NovelProject"]:
        from backend.ledger import TruthLedger
        from backend.world_settings import WorldSettings
        from backend.db import ProjectDB, has_json
        logger.info(f"[ProjectBase] 打开项目: {project_dir}")
        base_dir = cls._get_base_dir()
        if not cls._is_safe_path(base_dir, project_dir):
            from backend.runtime_paths import get_data_dir
            public_dir = os.path.join(get_data_dir(), 'novel_projects')
            if not cls._is_safe_path(public_dir, project_dir):
                users_dir = os.path.join(get_data_dir(), 'users')
                if not cls._is_safe_path(users_dir, project_dir):
                    logger.warning(f"[ProjectBase] 项目路径不安全: {project_dir}")
                    return None

        # 自动迁移：如果只有 JSON 没有 DB，先执行迁移
        if has_json(project_dir) and not has_db(project_dir):
            logger.info(f"[ProjectBase] 检测到 JSON 无 DB，自动迁移: {project_dir}")
            try:
                # db_migrate.py 在项目根目录，需动态导入
                import importlib
                root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                sys_path_added = False
                if root_dir not in sys.path:
                    sys.path.insert(0, root_dir)
                    sys_path_added = True
                migrate_mod = importlib.import_module("db_migrate")
                if sys_path_added and root_dir in sys.path:
                    sys.path.remove(root_dir)
                migrate_mod.migrate_project(project_dir)
            except Exception as e:
                logger.warning(f"[ProjectBase] 自动迁移失败，继续从 JSON 加载: {e}")

        # 从 SQLite 加载
        db = ProjectDB.get(project_dir)
        data = db.load_project_meta()
        if data is None:
            # 回退：尝试从 JSON 加载（兼容旧项目）
            meta_path = os.path.join(project_dir, "project.json")
            if not os.path.exists(meta_path):
                logger.warning(f"[ProjectBase] 无数据: {project_dir}")
                return None
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.error(f"[ProjectBase] JSON加载失败: {e}")
                return None

        try:
            proj = cls()
            proj._init_project_fields()
            proj.project_dir = project_dir
            proj._db = db
            proj.meta = data.get("meta", proj.meta)
            proj.chapters = data.get("chapters", [])
            proj.world_settings = data.get("world_settings", {})
            proj.character_settings = data.get("character_settings", {})
            proj.characters = data.get("characters", [])
            proj.volumes = data.get("volumes", [])
            proj.novel_outline = data.get("novel_outline", {})
            if isinstance(proj.novel_outline, list):
                proj.novel_outline = {}
            proj.brainstorm_cards = data.get("brainstorm_cards", [])
            pc = data.get("planning_cards", {"nodes": [], "edges": [], "meta": {}})
            if not isinstance(pc, dict):
                pc = {"nodes": [], "edges": [], "meta": {}}
            proj.planning_cards = pc
            if not proj.volumes and proj.chapters:
                proj.rebuild_volumes_from_chapters()
            if hasattr(proj, "normalize_all_chapters"):
                proj.normalize_all_chapters()
            proj.ledger = TruthLedger(proj.project_dir)
            # WorldSettings → TruthLedger 单向同步（初始化时只同步一次，仅当 ledger 对应字段为空时）
            try:
                world = WorldSettings(proj.project_dir)
                _sync_world_to_ledger(world, proj.ledger)
            except Exception as e:
                logger.warning(f"[ProjectBase] WorldSettings→Ledger 同步失败: {e}")
            logger.info(f"[ProjectBase] 项目打开成功: {proj.meta.get('title', '')}, {len(proj.chapters)}章, {len(proj.volumes)}卷")
            return proj
        except Exception as e:
            logger.error(f"[ProjectBase] 项目打开失败: {project_dir}, 错误: {e}")
            return None

    @classmethod
    def list_all(cls) -> List[Dict]:
        projects = []
        seen_paths = set()

        def _scan_dir(base_dir):
            if not os.path.exists(base_dir):
                return
            for name in os.listdir(base_dir):
                full = os.path.join(base_dir, name)
                if full in seen_paths:
                    continue
                if not os.path.isdir(full):
                    continue
                meta_path = os.path.join(full, "project.json")
                db_path = os.path.join(full, "project.db")

                # 优先从 SQLite 读取
                if os.path.exists(db_path):
                    try:
                        db = ProjectDB.get(full)
                        data = db.load_project_meta()
                        if data:
                            meta = data.get("meta", {})
                            seen_paths.add(full)
                            projects.append({
                                "path": full,
                                "dir": full,
                                "title": meta.get("title", name),
                                "genre": meta.get("genre", ""),
                                "chapters": len(data.get("chapters", [])),
                                "modified": meta.get("modified", ""),
                            })
                            continue
                    except Exception as e:
                        logger.warning("SQLite 读取失败 %s: %s", full, e)

                # 回退到 JSON
                if os.path.exists(meta_path):
                    if os.path.getsize(meta_path) == 0:
                        logger.warning("跳过空项目文件 %s", meta_path)
                        continue
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        meta = data.get("meta", {})
                        seen_paths.add(full)
                        projects.append({
                            "path": full,
                            "dir": full,
                            "title": meta.get("title", name),
                            "genre": meta.get("genre", ""),
                            "chapters": len(data.get("chapters", [])),
                            "modified": meta.get("modified", ""),
                        })
                    except Exception as e:
                        logger.warning("跳过损坏项目 %s: %s", full, e)

        _scan_dir(cls._get_base_dir())

        from backend.runtime_paths import get_data_dir
        default_dir = os.path.join(get_data_dir(), 'novel_projects')
        if os.path.abspath(default_dir) != os.path.abspath(cls._get_base_dir()):
            _scan_dir(default_dir)

        users_dir = os.path.join(get_data_dir(), 'users')
        if os.path.exists(users_dir):
            for user_name in os.listdir(users_dir):
                user_projects = os.path.join(users_dir, user_name, 'projects')
                if os.path.isdir(user_projects):
                    _scan_dir(user_projects)

        projects.sort(key=lambda x: x.get("modified", ""), reverse=True)
        return projects