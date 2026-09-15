# -*- coding: utf-8 -*-
"""
白城主 — 工作流持久化存储

用户编排好的 FlowGraph（节点+连线）持久化到 JSON 文件。
支持保存、加载、列表、删除、重命名。

存储路径: backend/flow_engine/nodes/workflows.json
"""

import json
import logging
import os
import uuid
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

_STORE_DIR = os.path.dirname(os.path.abspath(__file__))
_WORKFLOW_FILE = os.path.join(_STORE_DIR, "workflows.json")


def _read_store() -> List[dict]:
    """读取所有工作流，返回按创建时间倒序的列表"""
    if not os.path.exists(_WORKFLOW_FILE):
        return []
    try:
        with open(_WORKFLOW_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("[WorkflowStore] 读取失败: %s", e)
        return []


def _write_store(data: List[dict]) -> None:
    """写入所有工作流"""
    try:
        os.makedirs(_STORE_DIR, exist_ok=True)
        with open(_WORKFLOW_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error("[WorkflowStore] 写入失败: %s", e)


def save_workflow(name: str, nodes: List[dict], edges: List[dict], workflow_id: Optional[str] = None) -> dict:
    """
    保存工作流。

    Args:
        name: 工作流名称
        nodes: 节点列表 [{instance_id, node_id, node_name, inputs, x, y, ...}]
        edges: 连线列表 [{from_node, from_port, to_node, to_port, label}]
        workflow_id: 可选，传入时更新已有工作流；不传则新建

    Returns:
        {ok, id, name, saved_at}
    """
    store = _read_store()
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    if workflow_id:
        # 更新已有
        for i, w in enumerate(store):
            if w["id"] == workflow_id:
                store[i]["name"] = name
                store[i]["nodes"] = nodes
                store[i]["edges"] = edges
                store[i]["saved_at"] = now
                _write_store(store)
                logger.info("[WorkflowStore] 已更新: %s (%s)", name, workflow_id)
                return {"ok": True, "id": workflow_id, "name": name, "saved_at": now}
        return {"ok": False, "error": f"工作流 {workflow_id} 不存在"}

    # 新建
    new_id = "wf_" + uuid.uuid4().hex[:12]
    entry = {
        "id": new_id,
        "name": name,
        "nodes": nodes,
        "edges": edges,
        "created_at": now,
        "saved_at": now,
    }
    store.insert(0, entry)
    _write_store(store)
    logger.info("[WorkflowStore] 已保存: %s (%s), %d 节点 %d 连线", name, new_id, len(nodes), len(edges))
    return {"ok": True, "id": new_id, "name": name, "saved_at": now}


def load_workflow(workflow_id: str) -> Optional[dict]:
    """加载指定工作流的完整数据"""
    store = _read_store()
    for w in store:
        if w["id"] == workflow_id:
            return w
    return None


def list_workflows() -> List[dict]:
    """列出所有工作流（摘要，不含 nodes/edges 详情）"""
    store = _read_store()
    return [
        {
            "id": w["id"],
            "name": w["name"],
            "node_count": len(w.get("nodes", [])),
            "edge_count": len(w.get("edges", [])),
            "created_at": w.get("created_at", ""),
            "saved_at": w.get("saved_at", ""),
        }
        for w in store
    ]


def delete_workflow(workflow_id: str) -> bool:
    """删除工作流"""
    store = _read_store()
    new_store = [w for w in store if w["id"] != workflow_id]
    if len(new_store) == len(store):
        return False
    _write_store(new_store)
    logger.info("[WorkflowStore] 已删除: %s", workflow_id)
    return True


def rename_workflow(workflow_id: str, new_name: str) -> bool:
    """重命名工作流"""
    store = _read_store()
    for w in store:
        if w["id"] == workflow_id:
            w["name"] = new_name
            w["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            _write_store(store)
            logger.info("[WorkflowStore] 已重命名: %s → %s", workflow_id, new_name)
            return True
    return False
