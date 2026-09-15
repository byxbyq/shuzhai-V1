# -*- coding: utf-8 -*-
"""
书斋 V66 — 多 Agent 圆桌讨论（自研）

通过 AgentRegistry 获取 Agent 实例，组织多轮结构化讨论。
每轮：主持人抛出议题 → 参与者并发响应 → 收集汇总 → 下一轮。
max_rounds 轮后由主持人做最终总结。

使用示例::

    session = RoundtableSession(
        topic="第3章剧情走向",
        participants=["outline_agent", "character_agent", "world_agent"],
        moderator="outline_agent",
        max_rounds=2,
    )
    result = await session.run(context={"chapter_index": 2})
    # result = {"topic": str, "rounds": [...], "final_summary": str}
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RoundtableSession:
    """多 Agent 圆桌讨论会话。

    通过书斋现有的 AgentRegistry 调度机制，组织多个 Agent 围绕
    同一话题进行多轮结构化讨论。

    Attributes:
        topic: 讨论话题
        participants: 参与者 Agent ID 列表
        moderator: 主持人 Agent ID（为 None 时由系统主持）
        max_rounds: 最大讨论轮次
    """

    def __init__(
        self,
        topic: str,
        participants: List[str],
        moderator: Optional[str] = None,
        max_rounds: int = 3,
    ):
        """初始化圆桌会话。

        Args:
            topic: 讨论话题
            participants: 参与者 Agent ID 列表
            moderator: 主持人 Agent ID，None 表示系统自动主持
            max_rounds: 最大轮次，默认 3
        """
        self.topic: str = topic
        self.participants: List[str] = participants
        self.moderator: Optional[str] = moderator
        self.max_rounds: int = max(1, max_rounds)

    # ── Agent 实例获取 ──

    @staticmethod
    def _get_registry():
        """获取全局 AgentRegistry 单例（延迟导入避免循环引用）"""
        from backend.agents.agent_registry import get_registry
        return get_registry()

    @staticmethod
    def _get_agent(agent_id: str):
        """根据 agent_id 从注册表中获取 Agent 实例。

        Args:
            agent_id: Agent ID

        Returns:
            BaseAgent 子类实例或 None
        """
        registry = RoundtableSession._get_registry()
        for info in registry.list_all():
            if info["agent_id"] == agent_id:
                return registry.find(info["keywords"][0]) if info["keywords"] else None
        # 回退：遍历所有注册 agent 按 agent_id 匹配
        for agent in registry._agents:
            if agent.agent_id == agent_id:
                return agent
        return None

    # ── 执行 ──

    async def run(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """执行圆桌讨论。

        每轮流程：
            1. 系统生成本轮议题（基于前轮汇总）
            2. 所有参与者并发给出观点
            3. 收集观点并生成本轮总结
            4. 若未达最大轮次，将总结注入下一轮上下文

        Args:
            context: 初始上下文（如章节索引、当前内容等）

        Returns:
            dict::

                {
                    "topic": str,
                    "rounds": [
                        {
                            "round": int,
                            "issue": str,
                            "contributions": [{"agent": str, "reply": str}, ...],
                            "summary": str,
                        },
                        ...
                    ],
                    "final_summary": str,
                }
        """
        ctx = dict(context) if context else {}
        rounds: List[Dict[str, Any]] = []
        accumulated_context: str = ""

        for round_num in range(1, self.max_rounds + 1):
            logger.info(
                "[roundtable] 开始第 %d/%d 轮讨论: topic=%s",
                round_num, self.max_rounds, self.topic,
            )

            # ── 1. 生成本轮议题 ──
            if round_num == 1:
                issue = f"话题：{self.topic}\n请各 Agent 从自身专业角度给出分析。"
            else:
                issue = self._generate_issue(round_num, rounds, accumulated_context)

            # ── 2. 参与者并发响应 ──
            tasks = []
            for agent_id in self.participants:
                tasks.append(self._query_agent(agent_id, issue, ctx))

            agent_results = await asyncio.gather(*tasks, return_exceptions=True)

            contributions: List[Dict[str, str]] = []
            for agent_id, result in zip(self.participants, agent_results):
                if isinstance(result, Exception):
                    logger.error(
                        "[roundtable] Agent '%s' 第 %d 轮响应失败: %s",
                        agent_id, round_num, result,
                    )
                    contributions.append({
                        "agent": agent_id,
                        "reply": f"[错误] {str(result)}",
                    })
                else:
                    contributions.append({
                        "agent": agent_id,
                        "reply": result or "",
                    })

            # ── 3. 生成本轮总结 ──
            round_summary = self._summarize_round(round_num, issue, contributions)

            round_record = {
                "round": round_num,
                "issue": issue,
                "contributions": contributions,
                "summary": round_summary,
            }
            rounds.append(round_record)

            # ── 4. 累积上下文 ──
            accumulated_context += f"\n[第{round_num}轮总结] {round_summary}"

        # ── 5. 最终总结 ──
        final_summary = self._final_summarize(rounds, accumulated_context)

        logger.info(
            "[roundtable] 圆桌讨论完成: topic=%s, rounds=%d, participants=%d",
            self.topic, len(rounds), len(self.participants),
        )

        return {
            "topic": self.topic,
            "rounds": rounds,
            "final_summary": final_summary,
        }

    # ── 内部辅助方法 ──

    async def _query_agent(
        self, agent_id: str, issue: str, context: Dict[str, Any],
    ) -> str:
        """向单个 Agent 发起查询，返回其回复文本。

        优先通过 Agent 的 ``execute`` 方法调用，失败时回退到简单文本响应。

        Args:
            agent_id: Agent ID
            issue: 本轮议题文本
            context: 上下文字典

        Returns:
            Agent 的回复文本
        """
        agent = self._get_agent(agent_id)
        if agent is None:
            return f"[Agent '{agent_id}' 未注册]"

        # 构建调用参数
        params = {
            "_intent": "roundtable_discussion",
            "message": issue,
        }
        ctx = dict(context)
        ctx["roundtable_topic"] = self.topic

        try:
            # 使用 Agent 的 run 方法（带状态追踪）
            result = agent.run(params, ctx)
            return result.get("reply", "") or str(result)
        except Exception as e:
            logger.error(
                "[roundtable] Agent '%s' 调用失败: %s", agent_id, e,
            )
            return f"[调用失败] {str(e)}"

    def _generate_issue(
        self,
        round_num: int,
        previous_rounds: List[Dict[str, Any]],
        accumulated_context: str,
    ) -> str:
        """生成本轮讨论议题（系统主持）。

        如果指定了 moderator，尝试通过主持人 Agent 生成议题；
        否则由系统基于前轮汇总自动生成。

        Args:
            round_num: 当前轮次
            previous_rounds: 前几轮的记录
            accumulated_context: 累积的上下文文本

        Returns:
            本轮议题文本
        """
        if self.moderator:
            moderator_agent = self._get_agent(self.moderator)
            if moderator_agent:
                try:
                    issue_prompt = (
                        f"你是讨论主持人。话题：{self.topic}\n"
                        f"已进行 {round_num - 1} 轮讨论，汇总如下：\n"
                        f"{accumulated_context}\n\n"
                        f"请提出第 {round_num} 轮的讨论议题（一句话即可）："
                    )
                    result = moderator_agent.run(
                        {"_intent": "roundtable_moderate", "message": issue_prompt},
                        {},
                    )
                    return result.get("reply", "") or self._default_issue(round_num)
                except Exception as e:
                    logger.warning(
                        "[roundtable] 主持人 Agent 生成议题失败: %s", e,
                    )

        return self._default_issue(round_num)

    def _default_issue(self, round_num: int) -> str:
        """系统默认议题生成"""
        prompts = {
            1: f"话题：{self.topic}\n请各 Agent 从自身专业角度给出分析。",
            2: "基于上一轮的讨论，请各 Agent 针对不同观点进行回应或补充。",
            3: "请各 Agent 提出具体建议或行动方案。",
        }
        if round_num in prompts:
            return prompts[round_num]
        return f"第 {round_num} 轮：请围绕话题 '{self.topic}' 进行更深入的探讨，提出优化或补充意见。"

    def _summarize_round(
        self,
        round_num: int,
        issue: str,
        contributions: List[Dict[str, str]],
    ) -> str:
        """生成本轮总结。

        如果有主持人 Agent，通过主持人生成；否则系统自动拼接。

        Args:
            round_num: 当前轮次
            issue: 本轮议题
            contributions: 各 Agent 的观点

        Returns:
            本轮总结文本
        """
        # 拼接所有观点
        contrib_text = "\n".join(
            f"- {c['agent']}: {c['reply'][:200]}"
            for c in contributions
        )

        if self.moderator:
            moderator_agent = self._get_agent(self.moderator)
            if moderator_agent:
                try:
                    summary_prompt = (
                        f"讨论话题：{self.topic}\n"
                        f"第 {round_num} 轮议题：{issue}\n"
                        f"参与者观点：\n{contrib_text}\n\n"
                        "请用 2-3 句话总结本轮讨论的要点和分歧："
                    )
                    result = moderator_agent.run(
                        {"_intent": "roundtable_moderate", "message": summary_prompt},
                        {},
                    )
                    return result.get("reply", "") or self._default_summary(contrib_text)
                except Exception as e:
                    logger.warning(
                        "[roundtable] 主持人 Agent 生成总结失败: %s", e,
                    )

        return self._default_summary(contrib_text)

    def _default_summary(self, contrib_text: str) -> str:
        """系统默认总结（简单拼接）"""
        lines = contrib_text.strip().split("\n")
        agent_count = len(lines)
        return (
            f"本轮共 {agent_count} 位参与者发表观点。"
            f"核心要点涉及 {'、'.join(line.split(':')[0].strip('- ') for line in lines[:3])} 等方面。"
        )

    def _final_summarize(
        self,
        rounds: List[Dict[str, Any]],
        accumulated_context: str,
    ) -> str:
        """生成最终总结。

        优先通过主持人 Agent 生成；否则系统自动拼接各轮总结。

        Args:
            rounds: 全部讨论轮次记录
            accumulated_context: 累积的上下文

        Returns:
            最终总结文本
        """
        if self.moderator:
            moderator_agent = self._get_agent(self.moderator)
            if moderator_agent:
                try:
                    final_prompt = (
                        f"讨论话题：{self.topic}\n"
                        f"经过 {len(rounds)} 轮讨论，汇总如下：\n\n"
                        f"{accumulated_context}\n\n"
                        "请做最终总结（200 字以内），包括："
                        "1) 共识要点 2) 核心分歧 3) 行动建议"
                    )
                    result = moderator_agent.run(
                        {"_intent": "roundtable_moderate", "message": final_prompt},
                        {},
                    )
                    return result.get("reply", "") or self._default_final(rounds)
                except Exception as e:
                    logger.warning(
                        "[roundtable] 主持人 Agent 生成最终总结失败: %s", e,
                    )

        return self._default_final(rounds)

    def _default_final(self, rounds: List[Dict[str, Any]]) -> str:
        """系统默认最终总结"""
        parts = [f"## 圆桌讨论总结：{self.topic}"]
        for r in rounds:
            parts.append(f"\n### 第 {r['round']} 轮")
            parts.append(r["summary"])
        parts.append(f"\n共 {len(rounds)} 轮讨论，{len(self.participants)} 位参与者。")
        return "\n".join(parts)
