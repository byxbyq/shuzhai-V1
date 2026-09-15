# -*- coding: utf-8 -*-
"""
白城主 Flow Engine — Agent 适配器

将书斋现有的 BaseAgent 实例包装为 Flow Engine NodeBase，
复用 Agent 的 execute() 逻辑，通过端口映射实现数据流。

设计原则：
- 零侵入：不改动现有 Agent 代码
- 端口映射：Agent 的 params/context → 节点输入端口，result → 节点输出端口
- 节点即为 Agent 的 DAG 化封装
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from backend.flow_engine.node import NodeBase, PortType
from backend.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


# ── 动态 AgentNode 子类缓存 ──
_agent_node_classes: Dict[str, type] = {}


class AgentNode(NodeBase):
    """
    将 BaseAgent 实例适配为 Flow Engine 节点。

    自动映射：
    - 节点输入端口 ← Agent 的 intent_keywords 相关参数
    - 节点输出端口 → Agent.execute() 返回的 dict

    使用 from_agent() 创建节点实例，会自动创建类型正确的子类
    并注册到全局 registry。

    用法::

        from backend.agents.example_agents import OutlineAgent
        wrapped = AgentNode.from_agent(OutlineAgent())
        wrapped.inputs.set("message", "生成第3章大纲")
        await wrapped.execute()
        result = wrapped.outputs["reply"]
    """

    node_category = "书斋核心"

    def __init__(
        self,
        agent: Optional[BaseAgent] = None,
        instance_id: Optional[str] = None,
    ):
        self._agent = agent
        super().__init__(instance_id=instance_id)

    # ── 端口声明 ──

    def setup(self):
        """声明通用端口：输入 message + 章节索引，输出 reply + data"""
        self.add_input("message", PortType.STRING, "用户消息", required=False, default="")
        self.add_input("chapter_index", PortType.NUMBER, "章节索引", required=False, default=0)
        self.add_input("character", PortType.STRING, "角色名", required=False, default="")
        self.add_input("params", PortType.JSON, "额外参数", required=False, default={})
        self.add_output("reply", PortType.TEXT, "回复文本")
        self.add_output("data", PortType.JSON, "结构化数据")
        self.add_output("action", PortType.JSON, "前端操作")

    # ── 核心执行 ──

    async def execute(self) -> None:
        """将节点输入转为 Agent params/context，调用 Agent.run()，输出到端口"""
        # 构建 params
        params: dict = self.inputs.get("params", {}) or {}
        message = self.inputs.get("message", "")
        if message and "message" not in params:
            params["message"] = message
        chapter_index = self.inputs.get("chapter_index", 0)
        if chapter_index is not None:
            params["chapter_index"] = chapter_index
        character = self.inputs.get("character", "")
        if character:
            params["character"] = character

        # 构建 context（当前章节等）
        context = {"current_chapter_index": chapter_index}

        # 调用 Agent
        logger.debug(
            "[AgentNode] 调用 %s (params keys=%s)",
            self._agent.agent_name,
            list(params.keys()),
        )

        result = self._agent.run(params, context)

        # 输出到端口
        self.outputs["reply"] = result.get("reply", "")
        self.outputs["data"] = result.get("data") or {}
        self.outputs["action"] = result.get("action") or {}

    # ── 构造方法 ──

    @classmethod
    def from_agent(cls, agent: BaseAgent, instance_id: Optional[str] = None) -> "NodeBase":
        """
        从 Agent 实例创建节点。

        自动为每个 agent_id 创建唯一子类并缓存，
        确保 registry.register() 能按类区分不同 Agent。
        """
        agent_id = agent.agent_id
        if agent_id not in _agent_node_classes:
            node_cls = _make_agent_node_class(
                agent_id, agent.agent_name, agent.intent_keywords, agent
            )
            _agent_node_classes[agent_id] = node_cls
        else:
            node_cls = _agent_node_classes[agent_id]

        return node_cls(agent=agent, instance_id=instance_id)


def _make_agent_node_class(agent_id: str, agent_name: str, keywords: list, agent=None) -> type:
    """为特定 Agent 动态创建 AgentNode 子类。

    每个子类有唯一的 node_id，确保注册表按类区分不同 Agent。
    必须定义在 AgentNode 之后才能正确继承。
    agent 作为类属性持有，使 registry.create() 按类实例化时
    也能拿到原始 Agent 单例（否则 _agent 为 None）。
    """
    class DynamicAgentNode(AgentNode):
        node_id = f"shuzhai.{agent_id}"
        node_name = agent_name
        node_category = "书斋核心"
        node_description = (
            f"处理意图: {', '.join(keywords[:5])}"
            + (f" +{len(keywords) - 5}" if len(keywords) > 5 else "")
        )
        _default_agent = agent

        def __init__(self, agent=None, instance_id=None):
            super().__init__(
                agent=agent if agent is not None else type(self)._default_agent,
                instance_id=instance_id,
            )

    DynamicAgentNode.__name__ = f"AgentNode_{agent_id}"
    DynamicAgentNode.__qualname__ = f"AgentNode_{agent_id}"
    return DynamicAgentNode


def wrap_agent(agent: BaseAgent, instance_id: Optional[str] = None) -> AgentNode:
    """快捷函数：将一个 Agent 包装为 Flow Engine 节点"""
    return AgentNode.from_agent(agent, instance_id=instance_id)


def wrap_all_agents(agents: list) -> list:
    """批量包装"""
    return [wrap_agent(a) for a in agents]
