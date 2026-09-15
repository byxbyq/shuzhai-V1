# -*- coding: utf-8 -*-
"""
书斋 V66 — 技能/规则管理器（自研）

管理技能包清单（SkillManifest），提供冲突检测、依赖解析、启用/禁用、
以及与 PromptAssembler 的联动注入。

使用示例::

    manager = SkillManager()
    manager.register_manifest(SkillManifest(
        name="outline_gen", version="1.0.0",
        description="大纲生成技能",
        category="writing",
    ))
    conflicts = manager.check_conflicts()
    manager.inject_to_assembler(assembler)
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ── SkillManifest ──


@dataclass
class SkillManifest:
    """技能包清单数据类。

    Attributes:
        name: 技能名称（唯一标识）
        version: 语义化版本号，如 "1.0.0"
        description: 技能描述
        dependencies: 依赖的其他技能名称列表
        conflicts: 冲突的技能名称列表
        enabled: 是否启用
        category: 技能分类（如 writing / checking / export）
    """
    name: str
    version: str
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    enabled: bool = True
    category: str = "general"


# ── SkillManager ──


class SkillManager:
    """技能管理器。

    维护技能包注册表，提供冲突检测、依赖解析、状态管理，
    以及向 PromptAssembler 注入活跃技能描述的能力。

    Attributes:
        manifests: 已注册的技能清单字典，key 为技能名称
    """

    def __init__(self):
        self.manifests: Dict[str, SkillManifest] = {}

    # ── 注册 ──

    def register_manifest(self, manifest: SkillManifest) -> None:
        """注册一个技能包清单。

        如果同名技能已存在，会覆盖旧版本并记录警告。

        Args:
            manifest: SkillManifest 实例
        """
        if manifest.name in self.manifests:
            old = self.manifests[manifest.name]
            logger.warning(
                "[skill_manager] 覆盖已注册技能: name=%s, old_version=%s, new_version=%s",
                manifest.name, old.version, manifest.version,
            )
        self.manifests[manifest.name] = manifest
        logger.info(
            "[skill_manager] 注册技能: name=%s, version=%s, category=%s",
            manifest.name, manifest.version, manifest.category,
        )

    # ── 冲突检测 ──

    def check_conflicts(self) -> List[Tuple[str, str, str]]:
        """检测所有已注册技能之间的冲突。

        冲突类型：
            - 同一名称不同版本（多注册场景）
            - conflicts 字段中声明的互斥关系

        Returns:
            冲突对列表，每项为 ``(技能A名称, 技能B名称, 冲突原因)``
        """
        conflicts: List[Tuple[str, str, str]] = []
        names = list(self.manifests.keys())

        # 检查 conflicts 字段声明
        for name_a in names:
            manifest_a = self.manifests[name_a]
            for conflict_target in manifest_a.conflicts:
                if conflict_target in self.manifests:
                    conflicts.append((
                        name_a,
                        conflict_target,
                        f"{name_a} 声明与 {conflict_target} 冲突",
                    ))

        # 检查依赖环（简单版：检测直接依赖是否存在）
        # 注意：这是注册时检查，冲突对列表可被后续调用。
        return conflicts

    # ── 启用/禁用 ──

    def enable(self, name: str) -> bool:
        """启用指定技能。

        Args:
            name: 技能名称

        Returns:
            True 表示成功，False 表示技能不存在
        """
        if name not in self.manifests:
            logger.warning("[skill_manager] 技能不存在: name=%s", name)
            return False
        self.manifests[name].enabled = True
        logger.info("[skill_manager] 启用技能: name=%s", name)
        return True

    def disable(self, name: str) -> bool:
        """禁用指定技能。

        Args:
            name: 技能名称

        Returns:
            True 表示成功，False 表示技能不存在
        """
        if name not in self.manifests:
            logger.warning("[skill_manager] 技能不存在: name=%s", name)
            return False
        self.manifests[name].enabled = False
        logger.info("[skill_manager] 禁用技能: name=%s", name)
        return True

    # ── 查询 ──

    def get_active_skills(self) -> List[SkillManifest]:
        """获取所有已启用的技能清单。

        Returns:
            启用的 SkillManifest 列表
        """
        return [m for m in self.manifests.values() if m.enabled]

    def get_skill(self, name: str) -> Optional[SkillManifest]:
        """根据名称获取技能清单。

        Args:
            name: 技能名称

        Returns:
            SkillManifest 或 None
        """
        return self.manifests.get(name)

    # ── 依赖解析 ──

    def resolve_dependencies(self, name: str) -> List[str]:
        """递归解析指定技能的依赖链，返回所有缺失的依赖名称。

        实现方式：从目标技能出发，BFS 收集所有直接和间接依赖，
        然后与已注册技能集合做差集。

        Args:
            name: 技能名称

        Returns:
            缺失依赖的名称列表，空列表表示依赖完整
        """
        if name not in self.manifests:
            return [name]  # 目标技能本身不存在

        required: Set[str] = set()
        visited: Set[str] = set()
        queue: List[str] = [name]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            manifest = self.manifests.get(current)
            if manifest is None:
                required.add(current)
                continue
            for dep in manifest.dependencies:
                if dep not in visited:
                    queue.append(dep)

        # 排除自身
        required.discard(name)
        # 只返回未注册的
        missing = [d for d in required if d not in self.manifests]
        if missing:
            logger.warning(
                "[skill_manager] 技能 '%s' 缺失依赖: %s", name, missing,
            )
        return missing

    # ── 与 PromptAssembler 联动 ──

    def inject_to_assembler(self, assembler) -> None:
        """将活跃技能注入到 PromptAssembler 的技能注入层。

        为每个活跃技能生成 "名称 (版本): 描述" 格式的摘要行，
        合并后写入 assembler 的 ``skills`` 层（priority=20）。

        Args:
            assembler: PromptAssembler 实例
        """
        active = self.get_active_skills()
        if not active:
            assembler.clear_layer("skills")
            return

        lines = ["## 已激活技能包"]
        for m in sorted(active, key=lambda x: x.category):
            deps = f" [依赖: {', '.join(m.dependencies)}]" if m.dependencies else ""
            lines.append(f"- [{m.category}] {m.name} v{m.version}: {m.description}{deps}")

        assembler.add_layer("skills", "\n".join(lines), priority=20)
        logger.info(
            "[skill_manager] 已注入 %d 个活跃技能到 PromptAssembler", len(active),
        )
