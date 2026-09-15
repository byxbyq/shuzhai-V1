# -*- coding: utf-8 -*-
"""
书斋 V66 — 工具守卫模块

为 function calling 提供安全白名单机制。维护工具注册表，
所有工具调用必须经过白名单验证，未注册的工具调用将被拦截。

公开函数:
    register_tool(name, func, category, description) -> None
    is_allowed(tool_name) -> bool
    get_allowed_tools(category=None) -> list
    guard_call(tool_name, func, *args, **kwargs) -> Any
    enable_category(category) -> None
    disable_category(category) -> None
    SecurityError — 自定义安全异常

用法示例:
    from .tool_guard import register_tool, guard_call

    register_tool("web_search", _web_search, category="network", description="搜索网页")
    result = guard_call("web_search", _web_search, "DeepSeek V4 价格")
"""

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """工具安全异常：当调用未注册或已禁用的工具时抛出。"""

    def __init__(self, tool_name: str, message: str = ""):
        self.tool_name = tool_name
        msg = message or f"工具 '{tool_name}' 不在白名单中，调用被拦截"
        super().__init__(msg)


# ── 工具注册表 ──────────────────────────────────
# 结构: {tool_name: {"func": callable, "category": str, "description": str, "enabled": bool}}
_tool_registry: Dict[str, dict] = {}

# 按类别批量启用的状态追踪
_category_enabled: Dict[str, bool] = {}


def register_tool(
    name: str,
    func: Callable,
    category: str = "general",
    description: str = ""
) -> None:
    """向白名单注册一个工具。

    Args:
        name: 工具名称（唯一标识）
        func: 工具对应的可调用对象
        category: 工具分类，用于批量管理
        description: 工具功能描述
    """
    _tool_registry[name] = {
        "func": func,
        "category": category,
        "description": description,
        "enabled": True,
    }
    logger.debug(f"[工具守卫] 已注册工具: '{name}' (分类: {category})")


def unregister_tool(name: str) -> None:
    """从白名单中移除一个工具。

    Args:
        name: 工具名称
    """
    if name in _tool_registry:
        del _tool_registry[name]
        logger.debug(f"[工具守卫] 已移除工具: '{name}'")


def is_allowed(tool_name: str) -> bool:
    """检查工具是否在白名单中且已启用。

    Args:
        tool_name: 工具名称

    Returns:
        True 如果工具已注册且处于启用状态
    """
    if tool_name not in _tool_registry:
        return False
    tool_info = _tool_registry[tool_name]
    if not tool_info.get("enabled", True):
        return False
    # 检查所属类别是否被禁用
    category = tool_info.get("category", "general")
    if category in _category_enabled and not _category_enabled[category]:
        return False
    return True


def get_allowed_tools(category: Optional[str] = None) -> List[Dict]:
    """获取白名单中的工具列表。

    Args:
        category: 按分类过滤，None 表示返回全部

    Returns:
        工具信息列表，每项包含 name / category / description / enabled 字段
    """
    result = []
    for name, info in _tool_registry.items():
        if category is not None and info.get("category") != category:
            continue
        result.append({
            "name": name,
            "category": info.get("category", "general"),
            "description": info.get("description", ""),
            "enabled": info.get("enabled", True) and is_allowed(name),
        })
    return result


def guard_call(tool_name: str, func: Callable, *args, **kwargs) -> Any:
    """带白名单验证的工具调用包装器。

    调用前检查工具是否在白名单中，不在则抛出 SecurityError。

    Args:
        tool_name: 工具名称
        func: 工具对应的可调用对象
        *args, **kwargs: 传递给工具的参数

    Returns:
        工具的返回值

    Raises:
        SecurityError: 工具不在白名单中或已被禁用
    """
    if tool_name not in _tool_registry:
        raise SecurityError(
            tool_name,
            f"工具 '{tool_name}' 未注册，调用被拦截。"
            f"请先使用 register_tool() 注册该工具。"
        )

    if not is_allowed(tool_name):
        tool_info = _tool_registry[tool_name]
        category = tool_info.get("category", "general")
        raise SecurityError(
            tool_name,
            f"工具 '{tool_name}' (分类: {category}) 已被禁用，调用被拦截。"
        )

    logger.info(f"[工具守卫] 允许调用工具: '{tool_name}'")
    return func(*args, **kwargs)


def enable_category(category: str) -> None:
    """批量启用指定分类下的所有工具。

    Args:
        category: 工具分类名
    """
    _category_enabled[category] = True
    for name, info in _tool_registry.items():
        if info.get("category") == category:
            info["enabled"] = True
    logger.info(f"[工具守卫] 已启用分类 '{category}' 下的所有工具")


def disable_category(category: str) -> None:
    """批量禁用指定分类下的所有工具。

    禁用后，is_allowed() 将对属于该类别的工具返回 False，
    guard_call() 将抛出 SecurityError。

    Args:
        category: 工具分类名
    """
    _category_enabled[category] = False
    for name, info in _tool_registry.items():
        if info.get("category") == category:
            info["enabled"] = False
    logger.info(f"[工具守卫] 已禁用分类 '{category}' 下的所有工具")


def clear_registry() -> None:
    """清空工具注册表（仅用于测试）。"""
    _tool_registry.clear()
    _category_enabled.clear()
