# -*- coding: utf-8 -*-
"""写作辅助路由   (薄转发层)

所有端点已拆分到 routers/writing_assist/ 子包，此文件保留向后兼容。
"""
from .writing_assist import preference_router, templates_router, creative_router

__all__ = ["preference_router", "templates_router", "creative_router"]
