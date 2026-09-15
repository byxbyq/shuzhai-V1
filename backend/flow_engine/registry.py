# -*- coding: utf-8 -*-
"""
白城主 Flow Engine — 节点注册表

类似 ComfyUI 的节点市场：通过 node_id 字符串匹配，允许 Python 显式注册
和自动发现（future：从插件目录扫描）。
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Type

from backend.flow_engine.node import NodeBase

logger = logging.getLogger(__name__)


class RegistryError(Exception):
    """节点注册/查找错误"""
    pass


class NodeRegistry:
    """
    节点注册中心。

    用法::

        registry = NodeRegistry()

        @registry.register
        class MyNode(NodeBase):
            node_id = "my_node"
            ...

        # 创建实例
        node = registry.create("my_node", params={"foo": "bar"})
    """

    def __init__(self):
        self._entries: Dict[str, Type[NodeBase]] = {}
        self._categories: Dict[str, List[str]] = {}  # category -> [node_ids]
        self._metadata: Dict[str, dict] = {}          # 缓存 to_definition()

    # ── 注册 ──

    def register(self, node_cls: Type[NodeBase]) -> Type[NodeBase]:
        """注册节点类（装饰器或直接调用均可）"""
        if not node_cls.node_id:
            raise RegistryError(f"节点类 {node_cls.__name__} 未定义 node_id")

        node_id = node_cls.node_id
        if node_id in self._entries and self._entries[node_id] is not node_cls:
            logger.warning(
                "[registry] 覆盖已注册节点: %s（%s → %s）",
                node_id,
                self._entries[node_id].__name__,
                node_cls.__name__,
            )

        self._entries[node_id] = node_cls
        category = getattr(node_cls, "node_category", "未分类")
        self._categories.setdefault(category, [])
        if node_id not in self._categories[category]:
            self._categories[category].append(node_id)

        # 预热元数据缓存
        try:
            dummy = node_cls()
            self._metadata[node_id] = dummy.to_definition()
        except Exception:
            self._metadata[node_id] = {
                "node_id": node_id,
                "node_name": getattr(node_cls, "node_name", node_id),
                "node_category": category,
            }

        logger.debug("[registry] 注册节点: %s（%s）", node_id, node_cls.node_name)
        return node_cls

    def register_many(self, classes: List[Type[NodeBase]]) -> None:
        """批量注册"""
        for cls in classes:
            self.register(cls)

    # ── 查询 ──

    def is_registered(self, node_id: str) -> bool:
        return node_id in self._entries

    def get_class(self, node_id: str) -> Type[NodeBase]:
        if node_id not in self._entries:
            raise RegistryError(f"节点未注册: {node_id}")
        return self._entries[node_id]

    def get_metadata(self, node_id: str) -> dict:
        """获取节点类型定义（前端注册表所需）"""
        if node_id not in self._metadata:
            self.get_class(node_id)  # 触发初始化
        return self._metadata.get(node_id, {})

    def list_all(self) -> List[str]:
        """列出所有已注册 node_id"""
        return list(self._entries.keys())

    def get_registry_for_frontend(self) -> List[dict]:
        """导出前端所需节点市场数据"""
        result = []
        for category, node_ids in self._categories.items():
            for nid in node_ids:
                meta = self.get_metadata(nid)
                result.append(meta)
        return result

    def get_categories(self) -> Dict[str, List[str]]:
        return dict(self._categories)

    # ── 创建实例 ──

    def create(
        self,
        node_id: str,
        params: Optional[dict] = None,
        instance_id: Optional[str] = None,
    ) -> NodeBase:
        """
        创建节点实例。

        Args:
            node_id: 节点类型标识
            params: 用户配置参数（注入节点 inputs）
            instance_id: 可指定实例 ID，否则自动生成
        """
        cls = self.get_class(node_id)
        node = cls(instance_id=instance_id)

        # 将用户参数注入 inputs（仅注入已声明的端口）
        if params:
            for key, value in params.items():
                if key in {p.name for p in node.get_input_defs()}:
                    node.inputs.set(key, value)

        return node


# ── 全局单例 ──

registry = NodeRegistry()
