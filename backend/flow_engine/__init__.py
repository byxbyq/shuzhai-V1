# -*- coding: utf-8 -*-
"""
白城主 Flow Engine — 通用 DAG 节点编排引擎

独立于书斋业务逻辑，提供：
- 节点注册与发现（Plugin Registry）
- DAG 图建模与拓扑排序
- 异步并行执行器
- 节点间数据传递协议

命名由来：白城主——统领万千节点的城主，亦为书斋之主。
"""

from backend.flow_engine.node import (
    NodeBase,
    NodeInput,
    NodeOutput,
    NodeStatus,
    PortType,
    PortDefinition,
)
from backend.flow_engine.graph import FlowGraph, Edge, FlowGraphError
from backend.flow_engine.registry import NodeRegistry, registry
from backend.flow_engine.executor import FlowExecutor, NodeResult, ExecutionResult
from backend.flow_engine.nodes.adapter import AgentNode, wrap_agent, wrap_all_agents
from backend.flow_engine.nodes.official import register_shuzhai_nodes, get_preset_pipelines

__version__ = "0.1.0"
__all__ = [
    "NodeBase",
    "NodeInput",
    "NodeOutput",
    "NodeStatus",
    "PortType",
    "PortDefinition",
    "FlowGraph",
    "Edge",
    "FlowGraphError",
    "NodeRegistry",
    "registry",
    "FlowExecutor",
    "NodeResult",
    "ExecutionResult",
    "AgentNode",
    "wrap_agent",
    "wrap_all_agents",
    "register_shuzhai_nodes",
    "get_preset_pipelines",
]
