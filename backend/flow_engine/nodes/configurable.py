# -*- coding: utf-8 -*-
"""
白城主 MiniPipelineNode — AI 生成的配置式多步节点

支持 AI 联网搜索后自动生成的节点配置，无需写 Python 代码。
通过 JSON DSL 定义多步 API 调用链：上传 → 创建 → 轮询。

变量模板语法：
    ${input:port_name}     — 引用输入端口值
    ${step:step_name.key}  — 引用前序步骤提取的值
    ${env:VAR_NAME}        — 引用环境变量

用法：

    config = {
        "node_id": "hailuo.video",
        "node_name": "海螺视频生成",
        "node_category": "视频模型",
        "inputs": [
            {"name": "prompt", "type": "text", "description": "视频描述"},
            {"name": "reference_image", "type": "text", "description": "参考图URL"}
        ],
        "outputs": [
            {"name": "video_url", "type": "text", "description": "生成视频URL"}
        ],
        "steps": [...],
        "output_map": {"video_url": "${step:poll_result.video_url}"}
    }
    node = MiniPipelineNode.from_config(config)
"""

import os
import re
import time
import logging
from typing import Dict, Any, Optional

from backend.flow_engine.node import NodeBase, NodeInput, PortType, NodeStatus

logger = logging.getLogger(__name__)


# ── JSON 路径提取 ──

def _json_get(data: Any, path: str) -> Any:
    """简单的 JSON 路径提取：$.data.file_id 或 data.file_id"""
    path = path.lstrip("$").lstrip(".")
    if not path:
        return data
    parts = path.split(".")
    for part in parts:
        if isinstance(data, dict):
            data = data.get(part)
        elif isinstance(data, list):
            try:
                data = data[int(part)]
            except (IndexError, ValueError):
                return None
        else:
            return None
    return data


# ── 模板变量解析 ──

_VAR_RE = re.compile(r"\$\{(env|input|step):([^}]+)\}")


def _resolve_template(
    template: str,
    inputs: NodeInput,
    step_results: Dict[str, Any],
) -> str:
    """解析 ${env:} / ${input:} / ${step:} 模板变量"""

    def replacer(match):
        scope = match.group(1)
        path = match.group(2)

        if scope == "env":
            return os.environ.get(path, "")
        elif scope == "input":
            val = inputs.get(path)
            return str(val) if val is not None else ""
        elif scope == "step":
            # step:step_name.key
            if "." in path:
                step_name, key = path.split(".", 1)
            else:
                step_name, key = path, None
            val = step_results.get(step_name)
            if val and key:
                val = _json_get(val, f"$.{key}")
            return str(val) if val is not None else ""
        return ""

    return _VAR_RE.sub(replacer, str(template))


def _resolve_dict(
    obj: Any,
    inputs: NodeInput,
    step_results: Dict[str, Any],
) -> Any:
    """递归解析字典 / 列表 / 字符串中的模板变量"""
    if isinstance(obj, str):
        return _resolve_template(obj, inputs, step_results)
    elif isinstance(obj, dict):
        return {k: _resolve_dict(v, inputs, step_results) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_dict(item, inputs, step_results) for item in obj]
    return obj


# ── MiniPipelineNode ──

class MiniPipelineNodeConfigError(Exception):
    """节点配置错误"""
    pass


class MiniPipelineNode(NodeBase):
    """
    AI 生成的配置式多步节点。

    通过 JSON 配置定义多步 API 链，无需写代码。
    变量通过 ${input:} / ${step:} / ${env:} 模板引用。
    """

    node_category = "AI生成"

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        instance_id: Optional[str] = None,
    ):
        """
        直接传 config 构造，或之后调用 from_config() / load_from_config()。

        Args:
            config: 节点配置字典
            instance_id: 实例 ID
        """
        # 未显传 config 时，回退到子类的类级 _node_config（register_config_node 生成），
        # 否则 registry.create() 出来的实例 _config 为空，execute 会直接报"未加载配置"
        self._config = config or getattr(type(self), "_node_config", {}) or {}
        self._step_results: Dict[str, Any] = {}
        self._poll_interval_ms: int = 3000
        self._poll_timeout_ms: int = 300000

        if self._config:
            self._apply_config(self._config)

        super().__init__(instance_id=instance_id)

    # ── 配置加载 ──

    def _apply_config(self, config: Dict[str, Any]):
        """从配置字典设置节点元信息"""
        self.node_id = config.get("node_id", self.node_id)
        self.node_name = config.get("node_name", self.node_name)
        self.node_category = config.get("node_category", self.node_category)
        self.node_description = config.get("node_description", "")
        self._config = config

    def load_from_config(self, config: Dict[str, Any]):
        """
        运行时动态加载新配置（热更新）。

        Args:
            config: 节点配置字典，结构同 __init__ 文档。
        """
        self._apply_config(config)
        self._setup_ports()

    @classmethod
    def from_config(cls, config: Dict[str, Any], instance_id: Optional[str] = None):
        """
        从配置字典创建实例（类方法）。

        Args:
            config: 节点配置字典
            instance_id: 实例 ID

        Returns:
            MiniPipelineNode 实例
        """
        node = cls(config=config, instance_id=instance_id)
        node._setup_ports()
        return node

    # ── 端口声明 ──

    def _setup_ports(self):
        """根据配置声明输入输出端口"""
        # 清除已有端口
        self._input_defs.clear()
        self._output_defs.clear()

        for inp in self._config.get("inputs", []):
            port_type = PortType(inp.get("type", "text"))
            self.add_input(
                name=inp["name"],
                type=port_type,
                description=inp.get("description", ""),
                required=inp.get("required", False),
                default=inp.get("default"),
            )

        for out in self._config.get("outputs", []):
            port_type = PortType(out.get("type", "text"))
            self.add_output(
                name=out["name"],
                type=port_type,
                description=out.get("description", ""),
            )

    # ── 覆盖 setup（from_config 后自动调用） ──

    def setup(self):
        """子类可以覆盖，但 MiniPipelineNode 在 __init__ 中已处理"""
        if self._config:
            self._setup_ports()

    # ── 元信息透传（前端注册表/确认弹窗需要） ──

    def to_definition(self) -> dict:
        """导出节点类型定义；在基类基础上附加 run_mode/dependencies/run_code。"""
        base = super().to_definition()
        cfg = self._config or {}
        base["run_mode"] = cfg.get("run_mode", "http_api")
        base["dependencies"] = cfg.get("dependencies", {})
        if cfg.get("run_code"):
            base["run_code"] = cfg["run_code"]
        return base

    # ── 核心执行 ──

    async def execute(self):
        """按 run_mode 分派执行：

        - sdk_local / comfyui_bridge：走 BackendRouter（沙箱执行 run_code / ComfyUI 桥接）
        - http_api：按 steps 顺序执行第三方 API 调用链（含轮询/提取）
        """
        if not self._config:
            self.status = NodeStatus.FAILED
            self.outputs.set("error", "未加载配置")
            return

        run_mode = self._config.get("run_mode")

        # sdk_local / comfyui_bridge：三级后端标准化执行调度器
        if run_mode in ("sdk_local", "comfyui_bridge"):
            await self._run_router_backend(run_mode)
            return

        steps = self._config.get("steps", [])
        if not steps:
            self.status = NodeStatus.FAILED
            self.outputs.set("error", "配置中没有 steps")
            return

        self._step_results = {}
        import httpx

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                for step in steps:
                    step_name = step.get("name", f"step_{len(self._step_results)}")
                    logger.info(
                        "[MiniPipelineNode] 执行步骤: %s (%s)",
                        step_name,
                        step.get("api", {}).get("method", "GET"),
                    )

                    if "api" in step:
                        await self._run_api_step(client, step, step_name)
                    elif "poll" in step:
                        await self._run_poll_step(client, step, step_name)
                    else:
                        raise MiniPipelineNodeConfigError(
                            f"步骤 {step_name} 缺少 api 或 poll 字段"
                        )

                    logger.info(
                        "[MiniPipelineNode] 步骤完成: %s → %s",
                        step_name,
                        str(self._step_results.get(step_name, {}))[:100],
                    )

            # 映射输出
            output_map = self._config.get("output_map", {})
            for out_name, template in output_map.items():
                resolved = _resolve_template(
                    str(template), self.inputs, self._step_results
                )
                self.outputs.set(out_name, resolved)

            self.status = NodeStatus.COMPLETED

        except Exception as e:
            logger.error("[MiniPipelineNode] 执行失败: %s", e)
            self.status = NodeStatus.FAILED
            self.outputs.set("error", str(e))

    async def _run_router_backend(self, run_mode: str):
        """sdk_local / comfyui_bridge 后端：由 BackendRouter 统一调度。

        调度器内部完成：AST 高危阻断、沙箱/桥接执行、依赖预检提示。
        同步阻塞部分放入线程池，避免阻塞事件循环。
        """
        from backend.flow_engine.deps.backend_router import dispatch

        try:
            import asyncio
            result = await asyncio.to_thread(
                dispatch,
                self._config,
                inputs=self.inputs.to_dict(),
                params={},
            )
        except Exception as e:
            logger.error("[MiniPipelineNode] 后端调度异常: %s", e, exc_info=True)
            self.status = NodeStatus.FAILED
            self.outputs.set("error", f"后端调度异常: {e}")
            return

        if result.get("ok"):
            for k, v in (result.get("outputs") or {}).items():
                self.outputs.set(k, v)
            if result.get("dep_warnings"):
                self.outputs.set("dep_warnings", result["dep_warnings"])
            self.status = NodeStatus.COMPLETED
        else:
            self.status = NodeStatus.FAILED
            self.outputs.set("error", result.get("error") or "后端执行失败")
            if result.get("dep_warnings"):
                self.outputs.set("dep_warnings", result["dep_warnings"])

    async def _run_api_step(self, client, step: dict, step_name: str):
        """执行一个 HTTP API 步骤"""
        api = step["api"]
        method = api.get("method", "GET").upper()
        url = _resolve_template(api["url"], self.inputs, self._step_results)

        headers = _resolve_dict(
            api.get("headers", {}), self.inputs, self._step_results
        )
        body = _resolve_dict(
            api.get("body", {}), self.inputs, self._step_results
        )

        if method == "GET":
            resp = await client.get(url, headers=headers)
        elif method == "POST":
            body_type = api.get("body_type", "json")
            if body_type == "form":
                resp = await client.post(url, headers=headers, data=body)
            else:
                resp = await client.post(url, headers=headers, json=body)
        elif method == "PUT":
            resp = await client.put(url, headers=headers, json=body)
        else:
            raise MiniPipelineNodeConfigError(f"不支持的 HTTP 方法: {method}")

        if resp.status_code >= 400:
            raise MiniPipelineNodeConfigError(
                f"步骤 {step_name} HTTP {resp.status_code}: {resp.text[:500]}"
            )

        data = resp.json() if resp.text else {}
        self._step_results[step_name] = data

        # 提取指定字段
        extract = step.get("extract", {})
        for key, json_path in extract.items():
            val = _json_get(data, json_path)
            self._step_results.setdefault(step_name, {})
            if isinstance(self._step_results[step_name], dict):
                self._step_results[step_name][key] = val

    async def _run_poll_step(self, client, step: dict, step_name: str):
        """轮询步骤：反复请求直到条件满足或超时"""
        poll = step["poll"]
        url_template = poll["url"]
        until_condition = poll.get("until", "")  # JSON 路径条件，如 '$.data.status == "completed"'
        interval_ms = int(poll.get("interval_ms", 3000))
        timeout_ms = int(poll.get("timeout_ms", 300000))

        started = time.time()

        while True:
            url = _resolve_template(url_template, self.inputs, self._step_results)
            resp = await client.get(url)
            data = resp.json() if resp.text else {}

            # 检查条件
            if until_condition:
                satisfied = self._check_poll_condition(data, until_condition)
            else:
                satisfied = data != {}

            if satisfied:
                self._step_results[step_name] = data

                # 提取指定字段
                extract = step.get("extract", {})
                for key, json_path in extract.items():
                    val = _json_get(data, json_path)
                    self._step_results.setdefault(step_name, {})
                    if isinstance(self._step_results[step_name], dict):
                        self._step_results[step_name][key] = val
                return

            if (time.time() - started) * 1000 > timeout_ms:
                raise MiniPipelineNodeConfigError(
                    f"步骤 {step_name} 轮询超时（{timeout_ms}ms）"
                )

            await self._async_sleep(interval_ms / 1000)

    @staticmethod
    def _check_poll_condition(data: Any, condition: str) -> bool:
        """简易轮询条件解析。支持：

        - $.data.status == "completed"
        - $.data.progress >= 100
        """
        import operator

        ops = {
            "==": operator.eq,
            "!=": operator.ne,
            ">=": operator.ge,
            "<=": operator.le,
            ">": operator.gt,
            "<": operator.lt,
        }

        for op_str, op_func in ops.items():
            if op_str in condition:
                left_path, _, right_str = condition.partition(op_str)
                left_path = left_path.strip()
                right_str = right_str.strip().strip('"').strip("'")

                val = _json_get(data, left_path)
                # 尝试类型转换
                try:
                    right_val = int(right_str)
                except ValueError:
                    try:
                        right_val = float(right_str)
                    except ValueError:
                        right_val = right_str

                return op_func(val, right_val)

        # 无操作符时，检查存在性
        return _json_get(data, condition) is not None

    async def _async_sleep(self, seconds: float):
        """异步睡眠"""
        import asyncio
        await asyncio.sleep(seconds)


# ── 节点注册辅助 ──

def register_config_node(
    config: Dict[str, Any],
    registry=None,
) -> type:
    """
    从配置字典创建并注册一个 MiniPipelineNode 子类。

    Args:
        config: 节点配置字典
        registry: NodeRegistry 实例，默认用全局 registry

    Returns:
        创建的子类
    """
    from backend.flow_engine.registry import registry as global_registry

    reg = registry or global_registry
    node_id = config["node_id"]

    # 动态创建子类以便注册表区分
    class_name = f"MiniPipelineNode_{node_id.replace('.', '_')}"

    # 深拷贝 config 避免外部修改影响
    frozen_config = dict(config)

    def _setup_ports_for_subclass(self):
        """根据类级 _node_config 声明端口"""
        cfg = getattr(type(self), "_node_config", frozen_config)
        self._input_defs.clear()
        self._output_defs.clear()
        for inp in cfg.get("inputs", []):
            port_type = PortType(inp.get("type", "text"))
            self.add_input(
                name=inp["name"],
                type=port_type,
                description=inp.get("description", ""),
                required=inp.get("required", False),
                default=inp.get("default"),
            )
        for out in cfg.get("outputs", []):
            port_type = PortType(out.get("type", "text"))
            self.add_output(
                name=out["name"],
                type=port_type,
                description=out.get("description", ""),
            )

    SubClass = type(
        class_name,
        (MiniPipelineNode,),
        {
            "node_id": node_id,
            "node_name": config.get("node_name", node_id),
            "node_category": config.get("node_category", "AI生成"),
            "node_description": config.get("node_description", ""),
            "_node_config": frozen_config,
            "setup": _setup_ports_for_subclass,
        },
    )

    reg.register(SubClass)
    logger.info("[MiniPipelineNode] 已注册: %s", node_id)

    # 自动持久化保存
    try:
        from backend.flow_engine.nodes.store import save_config
        save_config(frozen_config)
    except Exception as e:
        logger.warning("[MiniPipelineNode] 持久化保存失败: %s", e)

    return SubClass
