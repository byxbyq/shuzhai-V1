# -*- coding: utf-8 -*-
"""
书斋 V66 — Agent 会话管理（自研）

提供单 Agent 会话（AgentSession）和多会话管理器（SessionManager），
支持消息历史记录、上下文压缩、会话持久化与恢复。

使用示例::

    sm = SessionManager()
    session = sm.create_session("outline_agent")
    session.add_message("user", "帮我生成第3章大纲")
    session.add_message("assistant", "好的，正在生成...")
    ctx = session.get_context()
    session.compact_context(max_messages=10)
    sm.close_session(session.session_id)
    restored = sm.restore_session(session.session_id)
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── AgentSession ──


class AgentSession:
    """单个 Agent 的独立会话。

    管理消息历史（context）、提供上下文压缩和序列化能力。

    Attributes:
        session_id: 会话唯一标识
        agent_id: 关联的 Agent ID
        created_at: 创建时间（UTC）
        last_active: 最后活跃时间（UTC）
    """

    def __init__(self, agent_id: str, session_id: Optional[str] = None):
        """初始化会话。

        Args:
            agent_id: 关联的 Agent ID
            session_id: 可选的会话 ID，不传则自动生成
        """
        self.session_id: str = session_id or uuid.uuid4().hex[:16]
        self.agent_id: str = agent_id
        self.context: List[Dict[str, str]] = []
        self.created_at: str = datetime.now(timezone.utc).isoformat()
        self.last_active: str = self.created_at

    # ── 消息管理 ──

    def add_message(self, role: str, content: str) -> None:
        """追加一条消息到历史上下文。

        Args:
            role: 消息角色（如 user / assistant / system）
            content: 消息内容
        """
        self.context.append({"role": role, "content": content})
        self.last_active = datetime.now(timezone.utc).isoformat()

    def get_context(self) -> List[Dict[str, str]]:
        """返回完整的消息历史列表。

        Returns:
            [{"role": str, "content": str}, ...]
        """
        return list(self.context)

    # ── 上下文压缩 ──

    def compact_context(self, max_messages: int = 20) -> None:
        """压缩上下文：保留最近 N 条消息，更早的用摘要替代。

        摘要形式为一条 system 角色消息，插入到 retained 之前。

        Args:
            max_messages: 保留的最近消息数量
        """
        if len(self.context) <= max_messages:
            return

        truncated = self.context[:-max_messages]
        retained = self.context[-max_messages:]

        # 生成摘要
        roles_summary = {}
        for msg in truncated:
            r = msg["role"]
            roles_summary[r] = roles_summary.get(r, 0) + 1

        summary_parts = [f"<摘要：更早的 {len(truncated)} 条消息>"]
        for role, count in roles_summary.items():
            summary_parts.append(f"  {role}: {count} 条")
        summary_text = "\n".join(summary_parts)

        self.context = [
            {"role": "system", "content": summary_text}
        ] + retained

        logger.debug(
            "[agent_session] 压缩会话 %s: %d → %d 条消息",
            self.session_id, len(truncated) + len(retained), len(self.context),
        )

    # ── 序列化 ──

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典，用于持久化。

        Returns:
            包含 session_id / agent_id / context / created_at / last_active 的字典
        """
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "context": self.context,
            "created_at": self.created_at,
            "last_active": self.last_active,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentSession":
        """从字典恢复会话实例。

        Args:
            data: to_dict() 产出的字典

        Returns:
            AgentSession 实例
        """
        session = cls(
            agent_id=data["agent_id"],
            session_id=data["session_id"],
        )
        session.context = data.get("context", [])
        session.created_at = data.get("created_at", session.created_at)
        session.last_active = data.get("last_active", session.last_active)
        return session


# ── SessionManager ──


class SessionManager:
    """多 Agent 会话管理器。

    负责会话的创建、查询、关闭和持久化恢复。

    Attributes:
        sessions: 当前活跃会话字典，key 为 session_id
    """

    def __init__(self):
        self.sessions: Dict[str, AgentSession] = {}

    # ── 会话生命周期 ──

    def create_session(self, agent_id: str) -> AgentSession:
        """创建新会话。

        Args:
            agent_id: 关联的 Agent ID

        Returns:
            新创建的 AgentSession 实例
        """
        session = AgentSession(agent_id=agent_id)
        self.sessions[session.session_id] = session
        logger.info(
            "[session_manager] 创建会话: session_id=%s, agent_id=%s",
            session.session_id, agent_id,
        )
        return session

    def get_session(self, session_id: str) -> Optional[AgentSession]:
        """根据 ID 获取会话。

        Args:
            session_id: 会话 ID

        Returns:
            AgentSession 或 None
        """
        return self.sessions.get(session_id)

    def list_sessions(self) -> List[AgentSession]:
        """列出所有活跃会话。

        Returns:
            AgentSession 列表
        """
        return list(self.sessions.values())

    def close_session(self, session_id: str) -> bool:
        """关闭指定会话并持久化到磁盘。

        持久化路径：``data/sessions/{session_id}.json``

        Args:
            session_id: 会话 ID

        Returns:
            True 表示关闭成功，False 表示会话不存在
        """
        session = self.sessions.pop(session_id, None)
        if session is None:
            logger.warning("[session_manager] 会话不存在: session_id=%s", session_id)
            return False

        self._persist_session(session)
        logger.info("[session_manager] 关闭会话: session_id=%s", session_id)
        return True

    def close_all(self) -> int:
        """关闭所有活跃会话并持久化。

        Returns:
            关闭的会话数量
        """
        count = len(self.sessions)
        for session_id in list(self.sessions.keys()):
            self.close_session(session_id)
        logger.info("[session_manager] 关闭全部会话: count=%d", count)
        return count

    # ── 持久化与恢复 ──

    @staticmethod
    def _session_path(session_id: str) -> str:
        """返回会话持久化文件路径"""
        base = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "data", "sessions",
        )
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, f"{session_id}.json")

    @staticmethod
    def _persist_session(session: AgentSession) -> None:
        """将会话序列化写入磁盘。

        Args:
            session: AgentSession 实例
        """
        path = SessionManager._session_path(session.session_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)
            logger.debug("[session_manager] 会话已持久化: path=%s", path)
        except OSError as e:
            logger.error("[session_manager] 会话持久化失败: path=%s, error=%s", path, e)

    def restore_session(self, session_id: str) -> Optional[AgentSession]:
        """从磁盘恢复已持久化的会话。

        恢复后会重新加入活跃会话池。

        Args:
            session_id: 会话 ID

        Returns:
            恢复的 AgentSession 实例，或 None（文件不存在/损坏）
        """
        path = self._session_path(session_id)
        if not os.path.exists(path):
            logger.warning("[session_manager] 会话文件不存在: path=%s", path)
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            session = AgentSession.from_dict(data)
            self.sessions[session.session_id] = session
            logger.info("[session_manager] 恢复会话: session_id=%s", session_id)
            return session
        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.error("[session_manager] 恢复会话失败: path=%s, error=%s", path, e)
            return None
