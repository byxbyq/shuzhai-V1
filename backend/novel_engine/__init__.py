# -*- coding: utf-8 -*-
"""小说引擎包 - 六轴碰撞检测系统

提供角色关系图构建、碰撞检测、灵感生成等核心能力，
与书斋的 TruthLedger / VectorMemory 深度集成。
"""
from .six_axis_graph import (
    SixAxis,
    SixAxisEdge,
    ConvergenceEvent,
    SixAxisGraph,
)
from .engine_core import NovelEngineCore

__all__ = [
    "SixAxis",
    "SixAxisEdge",
    "ConvergenceEvent",
    "SixAxisGraph",
    "NovelEngineCore",
]
