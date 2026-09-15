# -*- coding: utf-8 -*-
"""
白城主 Flow Engine — ComfyUI 适配器

在白城主 FlowGraph 与 ComfyUI workflow JSON 之间双向转换。

- 导出：白城主图 → ComfyUI workflow.json（可在 ComfyUI 中打开 / 继续编排）
- 导入：ComfyUI workflow.json → 白城主图（未知节点降级为可配置节点，保留端口与参数不丢数据）

ComfyUI 工作流格式说明：
- nodes: [{id, type, pos, size, flags, order, mode,
           inputs: [{name, type, link}], outputs: [{name, type, links}],
           properties, widgets_values}]
- links: [[linkId, fromNodeId, fromSlot, toNodeId, toSlot, type], ...]

设计原则（协议级适配，非逐节点特化）：
- 端口槽位 ↔ 端口名：通过端口数组顺序映射，与具体节点无关
- 类型映射：PortType ↔ ComfyUI 类型，维护两张可扩展映射表
- 未知节点兜底：导入时未注册节点降级为"可配置节点"，端口/参数原样保留
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════
# 类型映射表（可扩展）
# ═══════════════════════════════════════

# 白城主 PortType → ComfyUI 类型
WC_TO_COMFY: Dict[str, str] = {
    "string": "STRING",
    "text": "STRING",
    "number": "FLOAT",
    "boolean": "BOOLEAN",
    "json": "STRING",
    "image": "IMAGE",
    "video": "VIDEO",
    "audio": "AUDIO",
    "any": "*",
}

# ComfyUI 类型 → 白城主 PortType（张量/对象类型降级为 ANY，保证能连线）
COMFY_TO_WC: Dict[str, str] = {
    "STRING": "string",
    "INT": "number",
    "FLOAT": "number",
    "BOOLEAN": "boolean",
    "IMAGE": "image",
    "MASK": "image",
    "LATENT": "any",
    "MODEL": "any",
    "CLIP": "any",
    "VAE": "any",
    "CONDITIONING": "any",
    "CONTROL_NET": "any",
    "AUDIO": "audio",
    "VIDEO": "video",
    "*": "any",
    "COMBO": "string",
}

# 白城主 node_id → ComfyUI class_type（导出时优先使用；未配置则直接用 node_id 作为 type）
CLASS_TYPE_MAP: Dict[str, str] = {
    # 示例（按需扩展）：
    # "shuzhai.image_gen": "KSampler",
}

# 反查表：ComfyUI class_type → 白城主 node_id（导入时优先映射到已知节点）
COMFY_CLASS_MAP: Dict[str, str] = {v: k for k, v in CLASS_TYPE_MAP.items()}


def wc_to_comfy_type(port_type: str) -> str:
    """白城主端口类型 → ComfyUI 类型"""
    return WC_TO_COMFY.get(str(port_type).lower(), "STRING")


def comfy_to_wc_type(comfy_type: str) -> str:
    """ComfyUI 类型 → 白城主端口类型"""
    return COMFY_TO_WC.get(comfy_type, "any")


# ═══════════════════════════════════════
# 导出：白城主图 → ComfyUI workflow
# ═══════════════════════════════════════

def export_to_comfyui(nodes: List[dict], edges: List[dict]) -> dict:
    """
    将白城主图（workflow_store 格式）转换为 ComfyUI workflow JSON。

    Args:
        nodes: [{instance_id, node_id, node_name, inputs: [端口定义], outputs: [端口定义],
                 values: {端口名: 值}, x, y}]
        edges: [{from_node, from_port, to_node, to_port, label}]

    Returns:
        ComfyUI workflow dict（可直接保存为 .json 拖入 ComfyUI）
    """
    # 1. 白城主实例ID → ComfyUI 数字ID
    wc_to_comfy_id: Dict[str, int] = {}
    for idx, n in enumerate(nodes):
        wc_to_comfy_id[n.get("instance_id", "")] = idx + 1

    # 2. 构建 ComfyUI 节点（不含 links 信息，稍后回填）
    comfy_nodes: List[dict] = []
    output_links_map: Dict[tuple, List[int]] = {}  # (comfy_id, slot) -> [link_id, ...]
    input_link_map: Dict[tuple, int] = {}         # (comfy_id, input_idx) -> link_id
    link_records: List[list] = []                 # [linkId, fromId, fromSlot, toId, toSlot, type]
    connected_inputs_map: Dict[int, Dict[str, int]] = {}  # comfy_id -> {端口名: inputs 索引}

    next_link_id = 1

    for idx, n in enumerate(nodes):
        cid = idx + 1
        node_inputs = n.get("inputs") or []
        node_outputs = n.get("outputs") or []
        values = n.get("values") or {}

        # 输出端口
        outputs = []
        for p in node_outputs:
            ptype = p.get("type", "any") if isinstance(p, dict) else "any"
            outputs.append({
                "name": p.get("name", ""),
                "type": wc_to_comfy_type(ptype),
                "links": [],
            })

        # 输入端口：全部保留在 inputs（ComfyUI 官方习惯），
        # 有连线的 link 稍后回填；未连线项按端口顺序写入 widgets_values
        inputs = []
        widgets_values = []
        connected_inputs: Dict[str, int] = {}  # 端口名 -> input 索引
        for i, p in enumerate(node_inputs):
            pname = p.get("name", "") if isinstance(p, dict) else ""
            ptype = p.get("type", "any") if isinstance(p, dict) else "any"
            has_edge = any(
                e.get("to_node") == n.get("instance_id") and e.get("to_port") == pname
                for e in edges
            )
            inputs.append({
                "name": pname,
                "type": wc_to_comfy_type(ptype),
                "link": None,
            })
            if has_edge:
                connected_inputs[pname] = len(inputs) - 1
            else:
                # 未连线参数 → widgets_values（按端口定义顺序）
                val = values.get(pname)
                if val is None:
                    val = p.get("default") if isinstance(p, dict) else None
                widgets_values.append(val)

        connected_inputs_map[cid] = connected_inputs

        comfy_nodes.append({
            "id": cid,
            "type": CLASS_TYPE_MAP.get(n.get("node_id", ""), n.get("node_id", "")),
            "pos": [n.get("x", 0) or 0, n.get("y", 0) or 0],
            "size": [315, 98 + max(len(node_inputs), len(node_outputs), 1) * 22],
            "flags": {},
            "order": idx,
            "mode": 0,
            "inputs": inputs,
            "outputs": outputs,
            "properties": {"Node name for S&R": n.get("node_name", n.get("node_id", ""))},
            "widgets_values": widgets_values,
        })

        output_links_map[cid] = []

    # 3. 构建 links
    for e in edges:
        from_node = e.get("from_node", "")
        from_port = e.get("from_port", "")
        to_node = e.get("to_node", "")
        to_port = e.get("to_port", "")
        if from_node not in wc_to_comfy_id or to_node not in wc_to_comfy_id:
            logger.warning("[comfyui] 跳过无效连线: %s → %s", from_node, to_node)
            continue

        fcid = wc_to_comfy_id[from_node]
        tcid = wc_to_comfy_id[to_node]

        # 源端口槽位
        fnode = nodes[fcid - 1]
        from_slot = None
        ftype = "STRING"
        for i, p in enumerate(fnode.get("outputs") or []):
            if p.get("name") == from_port:
                from_slot = i
                ftype = wc_to_comfy_type(p.get("type", "any"))
                break
        if from_slot is None:
            logger.warning("[comfyui] 跳过无效连线: 源端口 %s.%s 不存在", from_node, from_port)
            continue

        # 目标端口槽位
        tnode = nodes[tcid - 1]
        to_slot = None
        for i, p in enumerate(tnode.get("inputs") or []):
            if p.get("name") == to_port:
                to_slot = i
                break
        if to_slot is None:
            logger.warning("[comfyui] 跳过无效连线: 目标端口 %s.%s 不存在", to_node, to_port)
            continue

        # 回填 input link
        input_idx = connected_inputs_map.get(tcid, {}).get(to_port)
        if input_idx is not None:
            comfy_nodes[tcid - 1]["inputs"][input_idx]["link"] = next_link_id

        link_records.append([next_link_id, fcid, from_slot, tcid, to_slot, ftype])
        output_links_map.setdefault((fcid, from_slot), []).append(next_link_id)
        next_link_id += 1

    # 回填 output links（按输出槽位）
    for n in comfy_nodes:
        cid = n["id"]
        for i, out in enumerate(n.get("outputs", [])):
            out["links"] = output_links_map.get((cid, i), [])

    return {
        "nodes": comfy_nodes,
        "links": link_records,
        "groups": [],
        "config": {},
        "extra": {},
        "version": 0.4,
    }


# ═══════════════════════════════════════
# 导入：ComfyUI workflow → 白城主图
# ═══════════════════════════════════════

def import_from_comfyui(workflow: dict, registry=None) -> dict:
    """
    将 ComfyUI workflow JSON 转换为白城主图（workflow_store 格式）。

    Args:
        workflow: ComfyUI workflow dict
        registry: NodeRegistry（用于判断已知节点；不传则全部按未知节点处理）

    Returns:
        {ok: True, nodes: [...], edges: [...], warnings: [...]}
        或 {ok: False, error: "..."}
    """
    warnings: List[str] = []
    comfy_nodes = workflow.get("nodes") or []
    comfy_links = workflow.get("links") or []

    if not comfy_nodes:
        return {"ok": False, "error": "工作流中没有节点"}

    # 1. ComfyUI 节点ID → 白城主节点（先建结构，端口名解析依赖 outputs/inputs）
    wc_nodes: List[dict] = []
    comfy_id_to_wc: Dict[int, str] = {}

    for cn in comfy_nodes:
        cid = cn.get("id")
        if cid is None:
            continue
        class_type = cn.get("type", "")
        wc_instance_id = "n" + str(cid)
        comfy_id_to_wc[cid] = wc_instance_id

        # 节点类型映射：优先反查表 → 已注册节点 → 降级为可配置节点
        mapped_id = COMFY_CLASS_MAP.get(class_type, "")
        if not mapped_id and registry is not None and registry.is_registered(class_type):
            mapped_id = class_type

        if mapped_id:
            category = "ComfyUI 导入"
            if registry is not None:
                meta = registry.get_metadata(mapped_id)
                category = meta.get("node_category", category) or category
        else:
            mapped_id = class_type
            category = "ComfyUI 导入"
            warnings.append(f"未知节点已降级为可配置节点: {class_type}")

        # 端口转换（统一使用 ComfyUI 原始定义，保证端口名一致、连线有效）
        inputs = []
        outputs = []
        values: Dict[str, Any] = {}

        for p in cn.get("inputs") or []:
            inputs.append({
                "name": p.get("name", ""),
                "type": comfy_to_wc_type(p.get("type", "*")),
                "label": p.get("name", ""),
                "description": "",
                "required": False,
            })

        for p in cn.get("outputs") or []:
            outputs.append({
                "name": p.get("name", ""),
                "type": comfy_to_wc_type(p.get("type", "*")),
                "label": p.get("name", ""),
                "description": "",
            })

        # widgets_values 回填到未连线输入（按顺序配对；多余部分存 _widgets 保留数据）
        widgets = cn.get("widgets_values") or []
        wi = 0
        for i, p in enumerate(cn.get("inputs") or []):
            if p.get("link") is None and wi < len(widgets):
                values[p.get("name", "")] = widgets[wi]
                wi += 1
        if wi < len(widgets):
            values["_widgets"] = widgets[wi:]
            warnings.append(f"{class_type}: {len(widgets) - wi} 个未命名参数已保留到 _widgets")

        pos = cn.get("pos") or [0, 0]
        wc_nodes.append({
            "instance_id": wc_instance_id,
            "node_id": mapped_id,
            "node_name": (cn.get("properties") or {}).get("Node name for S&R") or class_type,
            "node_category": category,
            "inputs": inputs,
            "outputs": outputs,
            "values": values,
            "x": pos[0] if len(pos) > 0 else 0,
            "y": pos[1] if len(pos) > 1 else 0,
        })

    # 2. 解析 links 表：[linkId, fromNodeId, fromSlot, toNodeId, toSlot, type]
    link_map: Dict[int, list] = {}
    for link in comfy_links:
        if not isinstance(link, list) or len(link) < 6:
            continue
        link_map[link[0]] = link

    # 3. 通过节点 inputs 的 link 重建边（避免重复）
    edges: List[dict] = []
    node_by_id: Dict[int, dict] = {cn.get("id"): cn for cn in comfy_nodes}

    for cn in comfy_nodes:
        cid = cn.get("id")
        if cid is None:
            continue
        for p in cn.get("inputs") or []:
            link_id = p.get("link")
            if link_id is None:
                continue
            link = link_map.get(link_id)
            if not link:
                continue
            _, from_id, from_slot, to_id, to_slot, _ = link
            if from_id not in node_by_id or from_id not in comfy_id_to_wc:
                warnings.append(f"跳过无效链接: 源节点 {from_id} 不存在")
                continue
            if to_id != cid:
                continue

            src_outputs = node_by_id[from_id].get("outputs") or []
            if from_slot >= len(src_outputs):
                warnings.append(f"跳过无效链接: 源端口槽位越界 {from_id}[{from_slot}]")
                continue

            from_port = src_outputs[from_slot].get("name", "")
            to_port = p.get("name", "")
            edges.append({
                "from_node": comfy_id_to_wc[from_id],
                "from_port": from_port,
                "to_node": comfy_id_to_wc[to_id],
                "to_port": to_port,
                "label": "",
            })

    # 统计孤儿链接（未被任何节点输入端口引用的 link）
    used_links = set()
    for cn in comfy_nodes:
        for p in cn.get("inputs") or []:
            if p.get("link") is not None:
                used_links.add(p["link"])
    orphan = [lid for lid in link_map if lid not in used_links]
    if orphan:
        warnings.append(f"跳过 {len(orphan)} 条未连接到任何输入端口的链接")

    return {
        "ok": True,
        "nodes": wc_nodes,
        "edges": edges,
        "warnings": warnings,
    }


# ═══════════════════════════════════════
# 运行时桥接（comfyui_bridge 三级后端兜底）
# ═══════════════════════════════════════

import httpx

DEFAULT_COMFYUI_URL = "http://127.0.0.1:8188"


def _comfyui_base_url() -> str:
    """获取 ComfyUI API 地址：环境变量 COMFYUI_API_URL 优先，否则默认 127.0.0.1:8188。"""
    import os
    return (os.environ.get("COMFYUI_API_URL") or DEFAULT_COMFYUI_URL).rstrip("/")


def is_comfyui_available(base_url: str = "") -> bool:
    """探测本地 ComfyUI 是否可用（GET /system_stats，2 秒超时）。"""
    url = (base_url or _comfyui_base_url()).rstrip("/")
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(f"{url}/system_stats")
            return resp.status_code == 200
    except Exception:
        return False


def run_comfyui_workflow(
    workflow: dict,
    inputs: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    base_url: str = "",
    timeout_s: float = 300.0,
) -> dict:
    """提交 ComfyUI workflow 并等待执行完成，返回统一结果结构。

    Args:
        workflow: ComfyUI workflow dict（含 nodes/links），会先转成 prompt 格式提交
        inputs:   端口输入（透传给 prompt 的顶层 inputs 字段）
        params:   额外参数（透传）

    Returns:
        {"ok": bool, "status": "completed"|"error"|"timeout",
         "outputs": dict, "error": str?, "prompt_id": str?}
    """
    url = (base_url or _comfyui_base_url()).rstrip("/")
    try:
        with httpx.Client(timeout=10.0) as client:
            # 标准 ComfyUI API：提交 {"prompt": workflow, "client_id": ...}
            payload: Dict[str, Any] = {"prompt": workflow}
            if inputs:
                payload["inputs"] = inputs
            if params:
                payload["params"] = params
            resp = client.post(f"{url}/prompt", json=payload)
            if resp.status_code != 200:
                return {
                    "ok": False,
                    "status": "error",
                    "outputs": {},
                    "error": f"ComfyUI /prompt HTTP {resp.status_code}: {resp.text[:500]}",
                    "prompt_id": None,
                }
            prompt_id = resp.json().get("prompt_id")

        # 轮询 /history/{prompt_id} 直到完成或超时
        import time
        t0 = time.time()
        with httpx.Client(timeout=5.0) as client:
            while time.time() - t0 < timeout_s:
                try:
                    hist = client.get(f"{url}/history/{prompt_id}")
                except Exception:
                    time.sleep(1.0)
                    continue
                if hist.status_code != 200:
                    time.sleep(1.0)
                    continue
                data = hist.json()
                entry = (data or {}).get(prompt_id)
                if entry is None:
                    time.sleep(1.0)
                    continue
                status = entry.get("status") or {}
                if status.get("completed") or status.get("status_str") == "success":
                    outputs = {}
                    for nid, out in (entry.get("outputs") or {}).items():
                        outputs[nid] = out
                    return {
                        "ok": True,
                        "status": "completed",
                        "outputs": outputs,
                        "prompt_id": prompt_id,
                    }
                if status.get("status_str") in ("error", "failed"):
                    msgs = status.get("messages") or []
                    err = "; ".join(str(m) for m in msgs)[:2000] or "ComfyUI 执行报错"
                    return {
                        "ok": False,
                        "status": "error",
                        "outputs": {},
                        "error": err,
                        "prompt_id": prompt_id,
                    }
                time.sleep(1.0)

        return {
            "ok": False,
            "status": "timeout",
            "outputs": {},
            "error": f"ComfyUI 执行超时（{timeout_s:.0f}s）",
            "prompt_id": prompt_id,
        }
    except Exception as e:
        logger.error("[comfyui] 桥接执行异常: %s", e, exc_info=True)
        return {
            "ok": False,
            "status": "error",
            "outputs": {},
            "error": f"ComfyUI 桥接执行异常: {e}",
            "prompt_id": None,
        }
