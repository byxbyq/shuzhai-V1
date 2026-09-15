# -*- coding: utf-8 -*-
"""
白城主 Flow Engine — 流程图模型

FlowGraph 持有：
- nodes: List[NodeBase]（实例）
- edges: List[Edge]

支持：
- DAG 合法性校验（无环）
- Kahn 拓扑排序，返回可并行批次
- 图序列化 / 反序列化
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from backend.flow_engine.node import NodeBase, PortType, NodeInput, NodeOutput

logger = logging.getLogger(__name__)


class FlowGraphError(Exception):
    """流程图错误（环/缺失节点/类型不匹配）"""
    pass


@dataclass
class Edge:
    """节点间连线"""
    id: str
    from_node: str          # 源节点 instance_id
    from_port: str          # 源节点输出端口名
    to_node: str            # 目标节点 instance_id
    to_port: str            # 目标节点输入端口名
    label: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from": {"node": self.from_node, "port": self.from_port},
            "to": {"node": self.to_node, "port": self.to_port},
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Edge":
        return cls(
            id=d["id"],
            from_node=d["from"]["node"],
            from_port=d["from"]["port"],
            to_node=d["to"]["node"],
            to_port=d["to"]["port"],
            label=d.get("label", ""),
        )


class FlowGraph:
    """流程图：节点实例 + 连线"""

    def __init__(self, graph_id: Optional[str] = None):
        self.graph_id = graph_id or "g_" + __import__("uuid").uuid4().hex[:8]
        self._nodes: Dict[str, NodeBase] = {}      # instance_id -> NodeBase
        self._edges: List[Edge] = []

    # ── 节点操作 ──

    def add_node(self, node: NodeBase) -> NodeBase:
        if node.instance_id in self._nodes:
            raise FlowGraphError(f"节点实例已存在: {node.instance_id}")
        self._nodes[node.instance_id] = node
        return node

    def get_node(self, instance_id: str) -> Optional[NodeBase]:
        return self._nodes.get(instance_id)

    def remove_node(self, instance_id: str) -> None:
        if instance_id not in self._nodes:
            raise FlowGraphError(f"节点不存在: {instance_id}")
        self._nodes.pop(instance_id)
        self._edges = [e for e in self._edges
                       if e.from_node != instance_id and e.to_node != instance_id]

    @property
    def nodes(self) -> List[NodeBase]:
        return list(self._nodes.values())

    # ── 边操作 ──

    def connect(
        self,
        from_node: str,
        from_port: str,
        to_node: str,
        to_port: str,
        label: str = "",
    ) -> Edge:
        """连接两个节点端口。自动校验类型兼容性。"""
        src = self._nodes.get(from_node)
        dst = self._nodes.get(to_node)
        if src is None:
            raise FlowGraphError(f"源节点不存在: {from_node}")
        if dst is None:
            raise FlowGraphError(f"目标节点不存在: {to_node}")
        if from_node == to_node:
            raise FlowGraphError("不能连接节点自身")

        # 校验端口存在
        src_ports = {p.name for p in src.get_output_defs()}
        dst_ports = {p.name for p in dst.get_input_defs()}
        if from_port not in src_ports:
            raise FlowGraphError(f"源节点输出端口不存在: {from_node}.{from_port}（可用: {src_ports}）")
        if to_port not in dst_ports:
            raise FlowGraphError(f"目标节点输入端口不存在: {to_node}.{to_port}（可用: {dst_ports}）")

        # 防重复
        for e in self._edges:
            if e.from_node == from_node and e.from_port == from_port \
               and e.to_node == to_node and e.to_port == to_port:
                raise FlowGraphError("该连线已存在")

        edge = Edge(
            id=f"e_{len(self._edges)}_{from_node[:6]}_{to_node[:6]}",
            from_node=from_node,
            from_port=from_port,
            to_node=to_node,
            to_port=to_port,
            label=label,
        )
        self._edges.append(edge)

        # 连接后立即校验成环
        if self._has_cycle():
            self._edges.remove(edge)
            raise FlowGraphError("连线会导致图中出现环，已回滚")

        return edge

    def remove_edge(self, edge_id: str) -> None:
        self._edges = [e for e in self._edges if e.id != edge_id]

    @property
    def edges(self) -> List[Edge]:
        return list(self._edges)

    # ── DAG 校验 ──

    @staticmethod
    def _types_compatible(src: PortType, dst: PortType) -> bool:
        """判断两个端口类型是否兼容。
        - ANY 可与任何类型兼容
        - TEXT 和 STRING 互相兼容
        """
        if src == PortType.ANY or dst == PortType.ANY:
            return True
        if src == dst:
            return True
        text_string = {PortType.TEXT, PortType.STRING}
        if src in text_string and dst in text_string:
            return True
        return False

    def _has_cycle(self) -> bool:
        """基于 DFS 检测环"""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {nid: WHITE for nid in self._nodes}
        adj: Dict[str, List[str]] = {nid: [] for nid in self._nodes}
        for e in self._edges:
            adj[e.from_node].append(e.to_node)

        def dfs(nid: str) -> bool:
            color[nid] = GRAY
            for nxt in adj[nid]:
                if color[nxt] == GRAY:
                    return True  # 发现环
                if color[nxt] == WHITE and dfs(nxt):
                    return True
            color[nid] = BLACK
            return False

        for nid in self._nodes:
            if color[nid] == WHITE and dfs(nid):
                return True
        return False

    def validate(self) -> List[str]:
        """完整校验，返回错误列表（空 = 合法）"""
        errors: List[str] = []

        if not self._nodes:
            errors.append("图中没有节点")
            return errors

        # 环检测
        if self._has_cycle():
            errors.append("图中存在环，不允许循环依赖")

        # 节点输入依赖检查：required 端口必须有连线或默认值
        for nid, node in self._nodes.items():
            connected_inputs: Set[str] = {
                e.to_port for e in self._edges if e.to_node == nid
            }
            for pdef in node.get_input_defs():
                if pdef.required and pdef.name not in connected_inputs \
                   and pdef.default is None:
                    errors.append(
                        f"节点[{node.node_name}]的必填输入「{pdef.label or pdef.name}」未连接"
                    )

        # 类型兼容检查
        for e in self._edges:
            src = self._nodes[e.from_node]
            dst = self._nodes[e.to_node]
            src_port = next((p for p in src.get_output_defs() if p.name == e.from_port), None)
            dst_port = next((p for p in dst.get_input_defs() if p.name == e.to_port), None)
            if src_port and dst_port:
                if not self._types_compatible(src_port.type, dst_port.type):
                    errors.append(
                        f"连线 {src.node_name}.{e.from_port} → {dst.node_name}.{e.to_port} "
                        f"类型不兼容: {src_port.type.value} ≠ {dst_port.type.value}"
                    )

        return errors

    def is_valid(self) -> bool:
        return not self.validate()

    # ── 拓扑排序 ──

    def topological_batches(self) -> List[List[str]]:
        """
        Kahn 算法拓扑排序，返回按执行批次分组的节点 instance_id。
        同一批内节点无依赖关系，可并行执行。
        抛出 FlowGraphError 表示存在环。
        """
        if self._has_cycle():
            raise FlowGraphError("图中存在环，无法执行")

        in_degree: Dict[str, int] = {nid: 0 for nid in self._nodes}
        adj: Dict[str, List[str]] = {nid: [] for nid in self._nodes}
        for e in self._edges:
            adj[e.from_node].append(e.to_node)
            in_degree[e.to_node] += 1

        from collections import deque
        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        if not queue:
            raise FlowGraphError("图没有起点节点（所有节点都有依赖）")

        batches: List[List[str]] = []
        visited_count = 0

        while queue:
            batch = list(queue)
            queue.clear()
            batches.append(batch)
            visited_count += len(batch)
            for nid in batch:
                for nxt in adj[nid]:
                    in_degree[nxt] -= 1
                    if in_degree[nxt] == 0:
                        queue.append(nxt)

        if visited_count != len(self._nodes):
            raise FlowGraphError("图无法完全排序（存在环）")

        return batches

    # ── 序列化 ──

    def to_dict(self) -> dict:
        """序列化为 JSON 可传输格式。节点数据与端口定义分离。"""
        nodes_data = []
        for nid, node in self._nodes.items():
            node_data = {
                "instance_id": node.instance_id,
                "node_id": node.node_id,
                "node_name": node.node_name,
                "params": {},   # 用户配置的参数（运行时由外部注入）
                "status": node.status.value,
                "error": node.error,
                "inputs": node.inputs.to_dict(),
                "outputs": node.outputs.to_dict(),
            }
            nodes_data.append(node_data)

        return {
            "graph_id": self.graph_id,
            "nodes": nodes_data,
            "edges": [e.to_dict() for e in self._edges],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def from_dict(self, data: dict, node_factory=None) -> None:
        """
        从 dict 重建图。node_factory: Callable[[node_id, params], NodeBase]
        若未提供 factory，仅重建拓扑骨架（节点以占位对象填充，无法执行）。
        """
        self.graph_id = data.get("graph_id", self.graph_id)
        self._nodes.clear()
        self._edges.clear()

        for nd in data.get("nodes", []):
            if node_factory is not None:
                node = node_factory(nd.get("node_id", ""), nd.get("params", {}))
            else:
                node = _PlaceholderNode(nd.get("node_id", "unknown"), nd.get("instance_id", ""))
            self._nodes[node.instance_id] = node

        for ed in data.get("edges", []):
            self._edges.append(Edge.from_dict(ed))


class _PlaceholderNode(NodeBase):
    """反序列化时无 factory 的占位节点"""

    node_id = "placeholder"
    node_name = "占位节点"

    def __init__(self, node_id: str, instance_id: str):
        self.node_id = node_id
        self.instance_id = instance_id or self._generate_id()
        self.status = self.status
        self.error = None
        self._input_defs = []
        self._output_defs = []
        self.inputs = NodeInput(self._input_defs)
        self.outputs = NodeOutput(self._output_defs)

    async def execute(self) -> None:
        pass

    def _generate_id(self) -> str:
        return "placeholder_" + __import__("uuid").uuid4().hex[:8]
