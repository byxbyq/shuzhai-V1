# -*- coding: utf-8 -*-
"""
白城主 Flow Engine — 三级后端标准化执行调度器

三级后端优先级（固定不变，见 deps/schema.py）：
    sdk_local       官方 Python SDK 原生调用（首选，主路径；run_code 由沙箱执行）
    comfyui_bridge  ComfyUI Adapter 桥接（次选，仅本地已部署 ComfyUI 时兜底）
    http_api        第三方 HTTP API 调用（末选，need_network/possible_cost 显式标注）

对外统一入口::

    result = BackendRouter.dispatch(node_config, inputs)
    # result = {"ok": bool, "status": "completed"|"blocked"|"error"|"unavailable",
    #           "outputs": dict, "error": str?, "backend": "sdk_local"|"comfyui_bridge"|"http_api"}
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.flow_engine.deps.run_sandbox import run_code_sandboxed

logger = logging.getLogger(__name__)


class BackendRouter:
    """三级后端路由调度器。"""

    # ── 主入口 ──

    @classmethod
    def dispatch(
        cls,
        node_config: Dict[str, Any],
        inputs: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """按 run_mode 路由到对应后端执行，返回统一结果结构。"""
        run_mode = node_config.get("run_mode", "http_api")
        inputs = inputs or {}
        params = params or {}

        if run_mode == "sdk_local":
            return cls._dispatch_sdk_local(node_config, inputs, params)
        if run_mode == "comfyui_bridge":
            return cls._dispatch_comfyui_bridge(node_config, inputs, params)
        if run_mode == "http_api":
            return cls._dispatch_http_api(node_config, inputs, params)

        return {
            "ok": False,
            "status": "error",
            "outputs": {},
            "error": f"未知 run_mode: {run_mode!r}",
            "backend": run_mode,
        }

    # ── sdk_local：官方 SDK 原生（run_code 沙箱执行） ──

    @classmethod
    def _dispatch_sdk_local(
        cls,
        node_config: Dict[str, Any],
        inputs: Dict[str, Any],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        run_code = node_config.get("run_code")
        if not run_code:
            return {
                "ok": False,
                "status": "error",
                "outputs": {},
                "error": "run_mode=sdk_local 但未提供 run_code（请通过 AI 编排或节点配置补充）",
                "backend": "sdk_local",
            }

        # 沙箱内执行 run_code：AST 高危阻断 + 子进程受限 + 超时
        result = run_code_sandboxed(run_code, inputs=inputs, params=params)
        result.setdefault("backend", "sdk_local")

        # 依赖预检失败时给出提示（不阻断执行，仅附加 note）
        deps = node_config.get("dependencies") or {}
        if deps:
            try:
                from backend.flow_engine.deps.dependency_manager import DependencyManager
                from backend.flow_engine.ai_composer import _PROJECT_ROOT
                dm = DependencyManager(_PROJECT_ROOT)
                verify = dm.verify_all(deps)
                if not verify.get("all_ok"):
                    result["dep_warnings"] = verify
            except Exception as e:
                logger.debug("[router] 依赖预检跳过: %s", e)

        return result

    # ── comfyui_bridge：ComfyUI Adapter 桥接（仅本地已部署） ──

    @classmethod
    def _dispatch_comfyui_bridge(
        cls,
        node_config: Dict[str, Any],
        inputs: Dict[str, Any],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            from backend.flow_engine.adapters.comfyui_adapter import is_comfyui_available, run_comfyui_workflow
        except ImportError:
            return {
                "ok": False,
                "status": "unavailable",
                "outputs": {},
                "error": "comfyui_adapter 未就绪（import 失败）",
                "backend": "comfyui_bridge",
            }

        if not is_comfyui_available():
            return {
                "ok": False,
                "status": "unavailable",
                "outputs": {},
                "error": "ComfyUI 未检测到本地部署（comfyui_bridge 兜底不可用，请检查 ComfyUI 地址或改用 sdk_local）",
                "backend": "comfyui_bridge",
            }

        try:
            workflow = node_config.get("comfyui_workflow") or {}
            result = run_comfyui_workflow(workflow, inputs=inputs, params=params)
            result.setdefault("backend", "comfyui_bridge")
            return result
        except Exception as e:
            logger.error("[router] comfyui_bridge 执行失败: %s", e, exc_info=True)
            return {
                "ok": False,
                "status": "error",
                "outputs": {},
                "error": f"ComfyUI 桥接执行失败: {e}",
                "backend": "comfyui_bridge",
            }

    # ── http_api：第三方 HTTP API（MiniPipelineNode steps 链路） ──

    @classmethod
    def _dispatch_http_api(
        cls,
        node_config: Dict[str, Any],
        inputs: Dict[str, Any],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        # http_api 链路由 MiniPipelineNode.execute() 走 steps 执行（含轮询/提取），
        # 调度器只做兜底：无 steps 时报错。
        steps = node_config.get("steps") or []
        if not steps:
            return {
                "ok": False,
                "status": "error",
                "outputs": {},
                "error": "run_mode=http_api 但配置中没有 steps（第三方 API 链路缺失）",
                "backend": "http_api",
            }
        return {
            "ok": False,
            "status": "error",
            "outputs": {},
            "error": "http_api 应由 MiniPipelineNode.execute() 执行 steps 链路，调度器兜底不应走到此处",
            "backend": "http_api",
        }


def dispatch(
    node_config: Dict[str, Any],
    inputs: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """模块级便捷入口。"""
    return BackendRouter.dispatch(node_config, inputs=inputs, params=params)
