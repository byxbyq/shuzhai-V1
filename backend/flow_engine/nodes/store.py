# -*- coding: utf-8 -*-
"""
白城主 — 节点配置持久化存储

所有通过 AI 生成、手动编写或下载的 MiniPipelineNode 配置，自动持久化到 JSON 文件。
服务重启后自动加载恢复，不会丢失。

存储路径: backend/flow_engine/nodes/config_nodes.json
"""

import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 持久化文件路径
_STORE_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = os.path.join(_STORE_DIR, "config_nodes.json")


def _read_store() -> Dict[str, dict]:
    """读取存储文件，返回 {node_id: config}"""
    if not os.path.exists(_CONFIG_FILE):
        return {}
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("[NodeStore] 读取失败，视为空: %s", e)
        return {}


def _write_store(data: Dict[str, dict]) -> None:
    """写入存储文件"""
    try:
        os.makedirs(_STORE_DIR, exist_ok=True)
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error("[NodeStore] 写入失败: %s", e)


def save_config(config: dict) -> bool:
    """
    持久化保存一个节点配置。

    Args:
        config: MiniPipelineNode 配置字典（必须含 node_id）

    Returns:
        True 表示保存成功
    """
    node_id = config.get("node_id")
    if not node_id:
        logger.error("[NodeStore] 保存失败: node_id 缺失")
        return False

    store = _read_store()
    store[node_id] = config
    _write_store(store)
    logger.info("[NodeStore] 已保存节点: %s", node_id)
    return True


def delete_config(node_id: str) -> bool:
    """删除一个节点配置"""
    store = _read_store()
    if node_id not in store:
        return False
    del store[node_id]
    _write_store(store)
    logger.info("[NodeStore] 已删除节点: %s", node_id)
    return True


def load_all_configs() -> List[dict]:
    """加载所有已保存的节点配置"""
    store = _read_store()
    return list(store.values())


def load_config(node_id: str) -> Optional[dict]:
    """加载指定节点配置"""
    store = _read_store()
    return store.get(node_id)


def get_saved_node_ids() -> List[str]:
    """获取所有已保存的 node_id"""
    return list(_read_store().keys())


def restore_all(registry=None) -> int:
    """
    从存储文件恢复所有节点到注册表。

    Args:
        registry: NodeRegistry 实例，默认全局

    Returns:
        成功恢复的节点数
    """
    from backend.flow_engine.nodes.configurable import register_config_node
    from backend.flow_engine.registry import registry as global_registry

    reg = registry or global_registry
    configs = load_all_configs()
    count = 0

    for config in configs:
        node_id = config.get("node_id", "")
        if reg.is_registered(node_id):
            logger.debug("[NodeStore] 节点已注册，跳过: %s", node_id)
            continue
        try:
            register_config_node(config, reg)
            count += 1
            logger.info("[NodeStore] 已恢复节点: %s", node_id)
        except Exception as e:
            logger.warning("[NodeStore] 恢复节点 %s 失败: %s", node_id, e)

    logger.info("[NodeStore] 恢复完成: %d/%d", count, len(configs))
    return count
