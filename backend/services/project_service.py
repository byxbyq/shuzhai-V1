# -*- coding: utf-8 -*-
"""项目服务层 - 管理全局项目状态

支持全局单例模式和按用户隔离两种模式：
- 默认使用全局单例（向后兼容），通过模块级 state 变量访问
- 通过 switch_user() 可切换到指定用户的独立状态
- 通过 AppState.get_for_user() 可获取指定用户状态而不影响全局
"""
import os
import logging
from typing import Optional, Dict

from backend.project import NovelProject

logger = logging.getLogger(__name__)
from backend.generator import ChapterGenerator
from backend.ledger import TruthLedger
from backend.world_settings import WorldSettings
from backend.services.vector_memory import VectorMemory
from backend.runtime_paths import get_projects_dir, get_frontend_dir, get_shared_memory_dir, get_last_project_file, set_current_user as _runtime_set_user

PROJECTS_DIR = get_projects_dir()
FRONTEND_DIR = get_frontend_dir()
SHARED_MEMORY_DIR = get_shared_memory_dir()

# 当前用户名（由中间件设置）
_current_user = 'default'

def set_current_user(username: str):
    """设置当前用户（登录后调用）"""
    global _current_user, PROJECTS_DIR
    _current_user = username or 'default'
    _runtime_set_user(_current_user)
    PROJECTS_DIR = get_projects_dir()
    os.makedirs(PROJECTS_DIR, exist_ok=True)

def get_current_user() -> str:
    return _current_user

# 全局状态（单例模式 + 按用户隔离）
class AppState:
    """应用状态容器，管理项目、生成器、账本等核心实例。

    支持两种使用模式：
    1. 全局单例模式：通过模块级 state 变量访问，所有调用共享同一状态
    2. 按用户隔离模式：通过 get_for_user() 获取指定用户的独立状态

    Attributes:
        project: 当前小说项目实例
        generator: 章节生成器实例
        ledger: 真相账本实例
        world: 世界设定实例
        vector_memory: 项目级向量记忆
        shared_vector_memory: 全局共享向量记忆
        username: 该状态所属的用户名
    """

    # 按用户存储的状态字典（类级，键为用户名，值为 AppState 实例）
    _per_user: Dict[str, 'AppState'] = {}

    def __init__(self, username: str = 'default'):
        """初始化 AppState 实例。

        Args:
            username: 该状态所属的用户名，默认为 'default'
        """
        self.project: Optional[NovelProject] = None
        self.generator: Optional[ChapterGenerator] = None
        self.ledger: Optional[TruthLedger] = None
        self.world: Optional[WorldSettings] = None
        self.vector_memory: Optional[VectorMemory] = None
        self.shared_vector_memory: Optional[VectorMemory] = None
        self.username: str = username

    @classmethod
    def get_for_user(cls, username: str) -> 'AppState':
        """获取指定用户的 AppState 实例，不存在则创建。

        此方法不影响全局 state，仅返回对应用户的状态对象。
        适合在需要并发处理多用户或进行单元测试的场景中使用。

        Args:
            username: 用户名，为空则使用 'default'

        Returns:
            对应用户的 AppState 实例
        """
        username = username or 'default'
        if username not in cls._per_user:
            cls._per_user[username] = cls(username=username)
        return cls._per_user[username]

    def cleanup(self) -> None:
        """安全释放当前状态持有的所有资源。

        依次关闭 vector_memory、刷新/关闭 ledger，然后将所有引用置为 None。
        调用后该状态对象不再持有项目资源，需重新加载项目。
        """
        logger.info(f"[AppState] Cleaning up state for user: {self.username}")

        # 关闭项目级向量记忆
        if self.vector_memory is not None and hasattr(self.vector_memory, 'close'):
            try:
                self.vector_memory.close()
            except Exception as e:
                logger.warning(f"[AppState] Failed to close vector_memory: {e}")

        # 关闭共享向量记忆
        if self.shared_vector_memory is not None and hasattr(self.shared_vector_memory, 'close'):
            try:
                self.shared_vector_memory.close()
            except Exception as e:
                logger.warning(f"[AppState] Failed to close shared_vector_memory: {e}")

        # 刷新并关闭账本
        if self.ledger is not None:
            if hasattr(self.ledger, 'flush'):
                try:
                    self.ledger.flush()
                except Exception as e:
                    logger.warning(f"[AppState] Failed to flush ledger: {e}")
            if hasattr(self.ledger, 'close'):
                try:
                    self.ledger.close()
                except Exception as e:
                    logger.warning(f"[AppState] Failed to close ledger: {e}")

        # 重置所有引用
        self.project = None
        self.generator = None
        self.ledger = None
        self.world = None
        self.vector_memory = None
        self.shared_vector_memory = None

        logger.info(f"[AppState] Cleanup complete for user: {self.username}")


state = AppState()


def switch_user(username: str) -> AppState:
    """切换当前全局状态到指定用户。

    保存当前用户状态到 AppState._per_user，然后从 _per_user 加载目标用户状态
    （若不存在则新建）。全局 state 对象保持不变，仅交换其内部属性，
    因此所有持有 state 引用的调用方都能立即看到切换后的状态。

    供 server.py 的认证中间件调用。

    Args:
        username: 目标用户名，为空则使用 'default'

    Returns:
        切换后的全局 state 对象
    """
    global _current_user

    username = username or 'default'

    # 已是当前用户，无需切换
    if username == _current_user:
        return state

    # 1. 保存当前用户状态到 _per_user
    _save_state_to_user(_current_user)
    logger.info(f"[switch_user] Saved state for user: {_current_user}")

    # 2. 更新当前用户标识及运行时路径
    _current_user = username
    set_current_user(username)

    # 3. 从 _per_user 加载目标用户状态到全局 state
    target_state = AppState.get_for_user(username)
    _load_state_into_global(target_state)

    logger.info(f"[switch_user] Switched to user: {username}")
    return state


def _save_state_to_user(username: str) -> None:
    """将当前全局 state 的内容保存到指定用户的存储中。

    Args:
        username: 要保存到的用户名
    """
    user_state = AppState.get_for_user(username)
    user_state.project = state.project
    user_state.generator = state.generator
    user_state.ledger = state.ledger
    user_state.world = state.world
    user_state.vector_memory = state.vector_memory
    user_state.shared_vector_memory = state.shared_vector_memory
    user_state.username = username


def _load_state_into_global(user_state: AppState) -> None:
    """将指定用户状态加载到全局 state 中（原地修改）。

    Args:
        user_state: 源状态对象
    """
    state.project = user_state.project
    state.generator = user_state.generator
    state.ledger = user_state.ledger
    state.world = user_state.world
    state.vector_memory = user_state.vector_memory
    state.shared_vector_memory = user_state.shared_vector_memory

def _save_last_project(project_dir: str):
    """Save last opened project path"""
    try:
        last_project_file = get_last_project_file()
        os.makedirs(os.path.dirname(last_project_file), exist_ok=True)
        with open(last_project_file, "w", encoding="utf-8") as f:
            f.write(project_dir)
    except Exception as e:
        logger.error(f"[Save Last Project] Error: {e}")

def get_ledger() -> Optional[TruthLedger]:
    # 必须与 project.ledger 保持同一实例：否则 get_ledger() 修改的是另一份内存副本，
    # GET hooks（读 project.ledger）看不到变更（伏笔 deadline/note 字段丢失的根因）
    if state.project and getattr(state.project, "ledger", None) is not None:
        state.ledger = state.project.ledger
        return state.ledger
    if state.ledger is None and state.project:
        state.ledger = TruthLedger(state.project.project_dir)
    return state.ledger

def get_world() -> Optional[WorldSettings]:
    if state.world is None and state.project:
        state.world = WorldSettings(state.project.project_dir)
    return state.world

def get_generator() -> Optional[ChapterGenerator]:
    """获取或创建 ChapterGenerator（懒加载，已创建则复用）"""
    if state.generator is None and state.project:
        state.generator = ChapterGenerator(state.project.project_dir, project=state.project)
    return state.generator

def get_vector_memory() -> Optional[VectorMemory]:
    if state.vector_memory is None and state.project:
        state.vector_memory = VectorMemory(state.project.project_dir)
    return state.vector_memory

def get_shared_vector_memory() -> VectorMemory:
    """获取跨项目共享的向量记忆实例"""
    if state.shared_vector_memory is None:
        os.makedirs(SHARED_MEMORY_DIR, exist_ok=True)
        state.shared_vector_memory = VectorMemory(SHARED_MEMORY_DIR)
    return state.shared_vector_memory

def create_project(title: str, genre: str = "", chapter_count: int = 10):
    """Create new project and reset services"""
    state.project = NovelProject.create(title, genre)
    state.project.meta["chapter_count"] = chapter_count
    state.project.meta["total_chapters"] = chapter_count
    state.project.meta["planned_chapters"] = chapter_count  # 用户设定的章数，不会被AI分卷覆盖
    # 先创建默认卷（后续add_chapter会自动将章节加入最后一个卷）
    state.project.add_volume("第一卷", "")
    # 创建指定数量的章节
    for i in range(chapter_count):
        state.project.add_chapter("第%d章" % (i + 1))
    state.project.save_all()
    state.generator = ChapterGenerator(state.project.project_dir)
    state.ledger = TruthLedger(state.project.project_dir)
    state.world = WorldSettings(state.project.project_dir)
    state.vector_memory = VectorMemory(state.project.project_dir)
    _save_last_project(state.project.project_dir)
    return state.project

def open_project(path: str):
    """Open existing project and reset services"""
    state.project = NovelProject.open(path)
    if not state.project:
        return None
    state.generator = ChapterGenerator(state.project.project_dir)
    state.ledger = TruthLedger(state.project.project_dir)
    state.world = WorldSettings(state.project.project_dir)
    state.vector_memory = VectorMemory(state.project.project_dir)
    _save_last_project(path)
    return state.project

def auto_init_project():
    """Auto-create or open last project on startup"""
    last_project_file = get_last_project_file()
    if os.path.exists(last_project_file):
        try:
            with open(last_project_file, "r", encoding="utf-8") as f:
                last_dir = f.read().strip()
            if os.path.exists(last_dir):
                state.project = NovelProject.open(last_dir)
                if state.project:
                    logger.info(f"[Auto-Init] Loaded last project: {state.project.meta.get('title', '')}")
                    return
        except Exception as e:
            logger.error(f"[Auto-Init] Failed to load last project: {e}")
    # Fallback to default
    default_dir = os.path.join(NovelProject._get_base_dir(), NovelProject._sanitize("书斋默认"))
    if os.path.exists(default_dir):
        state.project = NovelProject.open(default_dir)
    if not state.project:
        state.project = NovelProject.create("书斋默认", "小说")
        state.project.save_all()
    logger.info(f"[Auto-Init] Project: {state.project.meta.get('title', '')} ({state.project.project_dir})")

# 启动时自动初始化（延迟到 server.py 显式调用）
# auto_init_project()  # 改为由 server.py 启动时显式调用，避免 import 时副作用
_initialized = False

def ensure_initialized():
    global _initialized
    if not _initialized:
        _initialized = True
        auto_init_project()
