# -*- coding: utf-8 -*-
"""
书斋 V65 - 兼容导入层
此文件内容已拆分到 backend/agents/ 子包中。
保留此文件以兼容可能引用 backend.routers.agent 的其他模块。
"""

# 兼容导入：所有内容从 agents 子包导入
from backend.agents import router
from backend.agents.router import AgentRequest

# 暴露 router 和 AgentRequest，保持与原始接口一致
__all__ = ["router", "AgentRequest"]
