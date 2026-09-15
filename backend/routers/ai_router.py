# -*- coding: utf-8 -*-
"""AI路由 - /api/ai/*   (薄转发层)

所有端点已拆分到 routers/ai/ 子包，此文件保留向后兼容。
"""
from .ai import router

# Re-export models
from .ai._models import (
    ChatRequest, AnalyzeContentRequest, BrainstormRequest,
    ExpandIdeaRequest, SensoryRequest, AIProxyRequest
)

__all__ = [
    "router",
    "ChatRequest", "AnalyzeContentRequest", "BrainstormRequest",
    "ExpandIdeaRequest", "SensoryRequest", "AIProxyRequest",
]
