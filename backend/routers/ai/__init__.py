# -*- coding: utf-8 -*-
"""ai 子包"""
from fastapi import APIRouter

from .chat import router as chat_router
from .config import router as config_router
from .analysis import router as analysis_router
from .creative import router as creative_router
from .proxy_usage import router as proxy_usage_router

router = APIRouter(prefix="/api/ai")
router.include_router(chat_router)
router.include_router(config_router)
router.include_router(analysis_router)
router.include_router(creative_router)
router.include_router(proxy_usage_router)

# Re-export models
from ._models import (
    ChatRequest, AnalyzeContentRequest, BrainstormRequest,
    ExpandIdeaRequest, SensoryRequest, AIProxyRequest
)
