# -*- coding: utf-8 -*-
"""
节点 Schema 定义（白城主 Flow Engine 扩展版）

在原有 node_config（node_id/node_name/inputs/outputs/params/steps）基础上，
为"自然语言建图 + 本地执行"新增三个字段：

- dependencies: 依赖清单（pip 包 / 模型文件 / 系统二进制）
- run_code:     代码执行模式下的子进程执行代码（SDK 直连）
- run_mode:     当前节点走哪一级执行链路，用于日志排查与前端标签

三级后端优先级（固定不变）：
    sdk_local      官方 Python SDK 原生调用（首选，主路径）
    comfyui_bridge ComfyUI Adapter 桥接（次选，兼容兜底）
    http_api       第三方 HTTP API 调用（末选，need_network/possible_cost）

本模块仅定义结构与校验，不包含任何执行逻辑。
"""

from typing import Any, Dict, List, Tuple

# ── run_mode 枚举 ──

RUN_MODE_SDK_LOCAL = "sdk_local"
RUN_MODE_COMFYUI_BRIDGE = "comfyui_bridge"
RUN_MODE_HTTP_API = "http_api"

RUN_MODES = (
    RUN_MODE_SDK_LOCAL,
    RUN_MODE_COMFYUI_BRIDGE,
    RUN_MODE_HTTP_API,
)

# http_api 模式必须显式标注的风险字段
HTTP_API_FLAGS = ("need_network", "possible_cost")

# ── 节点完整 Schema 示例（H3 视频生成） ──

NODE_SCHEMA_EXAMPLE: Dict[str, Any] = {
    "node_id": "h3.video",
    "node_name": "H3 视频生成",
    "node_category": "视频模型",
    "inputs": [
        {"name": "prompt", "type": "text", "required": True},
    ],
    "outputs": [
        {"name": "video", "type": "video"},
    ],
    "params": {},
    "dependencies": {
        "pip": ["torch>=2.1", "huggingface_hub", "hailuo-h3"],
        "models": [
            {"repo_id": "MiniMaxAI/H3", "path": "models/H3", "size_approx": "15GB"},
        ],
        "system": ["ffmpeg"],
    },
    "run_code": (
        "import json, sys\n"
        "with open(sys.argv[1], encoding='utf-8') as f:\n"
        "    payload = json.load(f)\n"
        "prompt = payload['inputs']['prompt']\n"
        "# ... 官方 SDK 推理逻辑 ...\n"
        "print(json.dumps({'ok': True, 'outputs': {'video': '/abs/path/out.mp4'}}))\n"
    ),
    "run_mode": "sdk_local",
}

# ── 字段校验 ──

def validate_node_config(nc: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """校验单个节点配置是否符合扩展 Schema。

    Returns:
        (ok, errors): errors 为可读错误列表，空列表表示通过。
    """
    errors: List[str] = []
    if not isinstance(nc, dict):
        return False, ["节点配置必须是对象"]

    node_id = nc.get("node_id")
    if not node_id or not isinstance(node_id, str):
        errors.append("缺少 node_id")

    run_mode = nc.get("run_mode")
    if run_mode is not None and run_mode not in RUN_MODES:
        errors.append(f"run_mode 非法: {run_mode!r}，可选 {RUN_MODES}")

    # 依赖结构校验
    deps = nc.get("dependencies")
    if deps is not None:
        deps_ok, dep_errors = validate_dependencies(deps)
        if not deps_ok:
            errors.extend(dep_errors)

    # http_api 必须带风险标注
    if run_mode == RUN_MODE_HTTP_API:
        for flag in HTTP_API_FLAGS:
            if not nc.get(flag):
                errors.append(f"run_mode=http_api 时必须显式标注 {flag}: true")

    # run_code 与 run_mode 一致性
    run_code = nc.get("run_code")
    if run_mode == RUN_MODE_SDK_LOCAL and not run_code:
        errors.append("run_mode=sdk_local 时必须提供 run_code")
    if run_code and not isinstance(run_code, str):
        errors.append("run_code 必须是字符串")

    return (len(errors) == 0, errors)


def validate_dependencies(deps: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """校验 dependencies 结构。"""
    errors: List[str] = []
    if not isinstance(deps, dict):
        return False, ["dependencies 必须是对象"]

    # pip: 字符串列表
    pip_list = deps.get("pip", [])
    if not isinstance(pip_list, list) or not all(isinstance(x, str) for x in pip_list):
        errors.append("dependencies.pip 必须是字符串数组，如 ['torch>=2.1']")

    # system: 字符串列表
    sys_list = deps.get("system", [])
    if not isinstance(sys_list, list) or not all(isinstance(x, str) for x in sys_list):
        errors.append("dependencies.system 必须是字符串数组，如 ['ffmpeg']")

    # models: 对象数组
    model_list = deps.get("models", [])
    if not isinstance(model_list, list):
        errors.append("dependencies.models 必须是数组")
    else:
        for m in model_list:
            if not isinstance(m, dict):
                errors.append("dependencies.models 每一项必须是对象")
                continue
            if not m.get("repo_id"):
                errors.append("模型项缺少 repo_id")
            if not m.get("path"):
                errors.append("模型项缺少 path")

    return (len(errors) == 0, errors)


def build_sdk_node(
    node_id: str,
    node_name: str,
    inputs: List[Dict[str, Any]],
    outputs: List[Dict[str, Any]],
    dependencies: Dict[str, Any],
    run_code: str,
    params: Dict[str, Any] = None,
    node_category: str = "自定义",
) -> Dict[str, Any]:
    """构造一个标准 sdk_local 代码执行节点（AI 生成节点的统一出口）。"""
    return {
        "node_id": node_id,
        "node_name": node_name,
        "node_category": node_category,
        "inputs": inputs,
        "outputs": outputs,
        "params": params or {},
        "dependencies": dependencies,
        "run_code": run_code,
        "run_mode": RUN_MODE_SDK_LOCAL,
    }
