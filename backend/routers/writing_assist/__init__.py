# -*- coding: utf-8 -*-
"""writing_assist 子包"""
from .preference import preference_router
from .templates import templates_router
from .creative import creative_router

__all__ = ["preference_router", "templates_router", "creative_router"]
