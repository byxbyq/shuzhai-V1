# -*- coding: utf-8 -*-
"""
书斋 V65 - Agent 注册表
替代 dispatcher.py 中硬编码的 54 条 if/elif 分支，
通过注册-查找模式实现意图到 Agent 的动态映射。
"""

import logging
from typing import Optional, List

from backend.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Agent 注册表。

    负责维护所有 Agent 实例，提供注册、查找、列表功能。
    使用单例模式确保全局只有一个注册表。

    使用示例::

        registry = AgentRegistry()
        registry.register(OutlineAgent())
        agent = registry.find("generate_outline")
        if agent:
            result = agent.run(params, context)
    """

    _instance: Optional["AgentRegistry"] = None

    def __new__(cls) -> "AgentRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._agents = []
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._agents: List[BaseAgent] = []
        self._initialized = True

    def register(self, agent: BaseAgent) -> None:
        """注册一个 Agent 实例。

        Args:
            agent: 继承 BaseAgent 的 Agent 实例

        Raises:
            ValueError: 如果 agent_id 重复
        """
        # 检查重复
        for existing in self._agents:
            if existing.agent_id == agent.agent_id:
                raise ValueError(
                    f"Agent ID '{agent.agent_id}' 已存在（{existing.agent_name}），"
                    f"无法注册 {agent.agent_name}"
                )
        self._agents.append(agent)
        logger.info(
            "[registry] 注册 Agent: id=%s name=%s keywords=%s",
            agent.agent_id, agent.agent_name, agent.intent_keywords,
        )

    def find(self, intent: str) -> Optional[BaseAgent]:
        """根据 intent 查找匹配的 Agent。

        遍历所有已注册的 Agent，调用 can_handle() 方法匹配。
        返回第一个匹配的 Agent，无匹配则返回 None。

        Args:
            intent: 意图名称字符串

        Returns:
            匹配的 Agent 实例，或 None
        """
        for agent in self._agents:
            if agent.can_handle(intent):
                logger.debug(
                    "[registry] 匹配 Agent: intent=%s -> agent=%s",
                    intent, agent.agent_name,
                )
                return agent
        logger.debug("[registry] 未找到匹配 Agent: intent=%s", intent)
        return None

    def list_all(self) -> List[dict]:
        """列出所有已注册的 Agent 信息。

        Returns:
            [{"agent_id": str, "agent_name": str, "keywords": [...], "state": str}, ...]
        """
        return [
            {
                "agent_id": a.agent_id,
                "agent_name": a.agent_name,
                "keywords": a.intent_keywords,
                "state": a.state.value,
            }
            for a in self._agents
        ]

    def unregister(self, agent_id: str) -> bool:
        """注销指定 Agent。

        Args:
            agent_id: 要注销的 Agent ID

        Returns:
            True 表示成功注销，False 表示未找到
        """
        for i, agent in enumerate(self._agents):
            if agent.agent_id == agent_id:
                self._agents.pop(i)
                logger.info("[registry] 注销 Agent: id=%s", agent_id)
                return True
        return False

    def clear(self) -> None:
        """清空所有注册的 Agent"""
        self._agents.clear()
        logger.info("[registry] 已清空所有 Agent")


# ── 全局注册表单例 ──
def get_registry() -> AgentRegistry:
    """获取全局 AgentRegistry 单例"""
    return AgentRegistry()