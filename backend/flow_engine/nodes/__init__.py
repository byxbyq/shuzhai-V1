# -*- coding: utf-8 -*-
"""
白城主 Flow Engine — 官方节点包

提供：
- AgentNode 适配器：将书斋 BaseAgent 包装为 Flow Engine 节点
- register_shuzhai_nodes()：一键注册 15 个书斋节点
- get_preset_pipelines()：获取预置写作流水线模板
"""

from backend.flow_engine.nodes.adapter import AgentNode, wrap_agent, wrap_all_agents
from backend.flow_engine.nodes.official import register_shuzhai_nodes, get_preset_pipelines
from backend.flow_engine.nodes.configurable import MiniPipelineNode, register_config_node

__all__ = [
    "AgentNode",
    "wrap_agent",
    "wrap_all_agents",
    "register_shuzhai_nodes",
    "get_preset_pipelines",
    "MiniPipelineNode",
    "register_config_node",
]
