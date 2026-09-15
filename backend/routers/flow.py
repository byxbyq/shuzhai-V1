# -*- coding: utf-8 -*-
"""
白城主 Flow Engine API
GET  /api/flow/registry    — 节点注册表 + 预置流水线
POST /api/flow/run          — 执行流程图
"""
import logging
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from backend.flow_engine.registry import registry
from backend.flow_engine.graph import FlowGraph, FlowGraphError
from backend.flow_engine.executor import FlowExecutor
from backend.flow_engine.nodes.official import register_shuzhai_nodes, get_preset_pipelines
from backend.flow_engine.ai_composer import compose_and_register
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/flow")

# ── 启动时注册书斋节点 ──
_initialized = False


def _ensure_registered():
    global _initialized
    if not _initialized:
        try:
            register_shuzhai_nodes()

            # 自动恢复已持久化的 AI 生成 / 手动配置节点
            from backend.flow_engine.nodes.store import restore_all
            restored_count = restore_all()
            if restored_count > 0:
                logger.info("[flow] 从持久化存储恢复了 %d 个配置节点", restored_count)

            _initialized = True
            logger.info("[flow] 书斋节点注册完成")
        except Exception as e:
            logger.warning("[flow] 节点注册失败: %s", e)


# ── Pydantic 模型 ──

class FlowEdgeModel(BaseModel):
    from_node: str
    from_port: str
    to_node: str
    to_port: str
    label: str = ""


class FlowRunRequest(BaseModel):
    nodes: List[Dict[str, Any]]          # [{instance_id, node_id, inputs}]
    edges: List[FlowEdgeModel]


# ── API ──

@router.get("/registry")
def get_registry():
    """返回节点注册表 + 预置流水线（供前端画布使用）。"""
    _ensure_registered()
    return {
        "ok": True,
        "nodes": registry.get_registry_for_frontend(),
        "categories": registry.get_categories(),
        "pipelines": get_preset_pipelines(),
    }


@router.post("/run")
def run_flow(req: FlowRunRequest):
    """执行流程图，同步返回各节点输出。"""
    _ensure_registered()

    g = FlowGraph()

    # 1. 实例化所有节点
    instance_map: Dict[str, Any] = {}
    for node_def in req.nodes:
        node_id = node_def.get("node_id", "")
        instance_id = node_def.get("instance_id", "")
        if not node_id:
            return err(ErrorCode.VALIDATION_ERROR, f"节点缺少 node_id: {node_def}")
        if not instance_id:
            return err(ErrorCode.VALIDATION_ERROR, f"节点缺少 instance_id: {node_def}")

        try:
            node = registry.create(node_id, instance_id=instance_id)
        except Exception as e:
            return err(ErrorCode.VALIDATION_ERROR, f"无法创建节点 {node_id}: {e}")

        # 设置初始输入（端口按声明判定，未注入过值的端口也能写入）
        inputs = node_def.get("inputs", {})
        declared_ports = {d.name for d in node.inputs.definitions}
        for port_name, value in inputs.items():
            if port_name in declared_ports or port_name in node.inputs:
                node.inputs.set(port_name, value)

        g.add_node(node)
        instance_map[instance_id] = node

    # 2. 建立连线
    for edge in req.edges:
        try:
            g.connect(edge.from_node, edge.from_port, edge.to_node, edge.to_port, edge.label)
        except FlowGraphError as e:
            return err(ErrorCode.VALIDATION_ERROR, str(e))

    # 3. 校验
    errors = g.validate()
    if errors:
        return err(ErrorCode.VALIDATION_ERROR, "流程图校验失败: " + "; ".join(errors))

    # 4. 执行
    executor = FlowExecutor(g)
    try:
        result = asyncio.run(executor.run())
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"执行异常: {e}")

    # 5. 汇总结果
    node_results = []
    for r in result.results:
        node_results.append({
            "instance_id": r.instance_id,
            "node_id": r.node_id,
            "node_name": r.node_name,
            "status": r.status.value,
            "duration_ms": round(r.duration_ms, 1),
            "outputs": r.outputs,
            "error": r.error,
        })

    return {
        "ok": True,
        "success": result.success,
        "total_duration_ms": round(result.total_duration_ms, 1),
        "results": node_results,
    }


# ── AI 编排 ──

class SixSeatRunRequest(BaseModel):
    chapter_index: int = 0
    project_dir: str = ""


@router.post("/six-seat/run")
def run_six_seat(req: SixSeatRunRequest):
    """P3-1：同步执行六席位流水线（大纲→正文→校验→修订→防幻觉→台账）。"""
    _ensure_registered()
    try:
        from backend.services.six_seat_pipeline import run_six_seats
        result = run_six_seats(chapter_index=req.chapter_index, project_dir=req.project_dir)
        return {"ok": True, **result}
    except Exception as e:
        logger.error("[flow] 六席位执行失败: %s", e, exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"六席位执行失败: {e}")


class ComposeRequest(BaseModel):
    prompt: str
    existing_node_ids: List[str] = []  # 用户引用的节点 ID 列表
    existing_graph: Optional[dict] = None  # 画布当前完整图 {"nodes":[...], "edges":[...]}
    rewrite: Optional[dict] = None  # 驳回重写 {"reason": "..."}，非空时触发重新生成


@router.post("/compose")
async def compose_flow(req: ComposeRequest):
    """一句话生成节点配置并自动连线。

    输入自然语言描述 → AI 联网搜索 → 生成 MiniPipelineNode 配置 → 注册 + 连线。
    传入 existing_graph 时在画布现有图上追加节点，返回完整图。
    rewrite.reason 非空时，将驳回原因追加到 prompt 重新生成（前端"驳回重写"）。
    """
    _ensure_registered()

    try:
        result = await compose_and_register(
            prompt=req.prompt,
            existing_node_ids=req.existing_node_ids or None,
            existing_graph=req.existing_graph,
            rewrite_reason=(req.rewrite or {}).get("reason", ""),
        )
    except Exception as e:
        logger.error("[flow.compose] 编排失败: %s", e)
        return err(ErrorCode.INTERNAL_ERROR, f"AI 编排失败: {e}")

    if not result.get("ok"):
        return {
            "ok": False,
            "error": result.get("error", "未知错误"),
            "raw_response": result.get("raw_response", ""),
        }

    return {
        "ok": True,
        "data": {
            "node_ids": result["node_ids"],
            "node_configs": result["node_configs"],
            "graph": result["graph"],
            "connections": result["connections"],
            "explanation": result["explanation"],
            "dependency_checks": result.get("dependency_checks", {}),
        },
    }


# ── 工作流持久化 ──

class WorkflowSaveRequest(BaseModel):
    name: str
    nodes: List[Dict[str, Any]]
    edges: List[FlowEdgeModel]
    workflow_id: str = ""  # 非空表示更新


class WorkflowLoadResponse(BaseModel):
    ok: bool
    data: Optional[Dict[str, Any]] = None
    error: str = ""


@router.get("/workflows")
def list_workflows():
    """列出所有已保存的工作流"""
    _ensure_registered()
    from backend.flow_engine.nodes.workflow_store import list_workflows as _list
    return {"ok": True, "workflows": _list()}


@router.post("/workflows")
def save_workflow(req: WorkflowSaveRequest):
    """保存工作流"""
    _ensure_registered()
    from backend.flow_engine.nodes.workflow_store import save_workflow as _save

    edges = [e.model_dump() for e in req.edges]
    result = _save(
        name=req.name,
        nodes=req.nodes,
        edges=edges,
        workflow_id=req.workflow_id or None,
    )
    if result.get("ok"):
        return {"ok": True, "data": result}
    return err(ErrorCode.VALIDATION_ERROR, result.get("error", "保存失败"))


@router.get("/workflows/{workflow_id}")
def load_workflow(workflow_id: str):
    """加载工作流"""
    _ensure_registered()
    from backend.flow_engine.nodes.workflow_store import load_workflow as _load

    wf = _load(workflow_id)
    if wf:
        return {"ok": True, "data": wf}
    return err(ErrorCode.NOT_FOUND, f"工作流 {workflow_id} 不存在")


@router.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: str):
    """删除工作流"""
    _ensure_registered()
    from backend.flow_engine.nodes.workflow_store import delete_workflow as _del

    if _del(workflow_id):
        return {"ok": True}
    return err(ErrorCode.NOT_FOUND, f"工作流 {workflow_id} 不存在")


class WorkflowRenameRequest(BaseModel):
    name: str


@router.put("/workflows/{workflow_id}")
def rename_workflow(workflow_id: str, req: WorkflowRenameRequest):
    """重命名工作流"""
    _ensure_registered()
    from backend.flow_engine.nodes.workflow_store import rename_workflow as _rename

    if not req.name.strip():
        return err(ErrorCode.VALIDATION_ERROR, "名称不能为空")
    if _rename(workflow_id, req.name.strip()):
        return {"ok": True}
    return err(ErrorCode.NOT_FOUND, f"工作流 {workflow_id} 不存在")


# ── ComfyUI 互通 ──

class ComfyUIExportRequest(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[FlowEdgeModel] = []


class ComfyUIImportRequest(BaseModel):
    workflow: Dict[str, Any]


@router.post("/comfyui/export")
def export_comfyui(req: ComfyUIExportRequest):
    """白城主图 → ComfyUI workflow JSON"""
    from backend.flow_engine.adapters.comfyui_adapter import export_to_comfyui

    try:
        workflow = export_to_comfyui(req.nodes, [e.model_dump() for e in req.edges])
        return {"ok": True, "workflow": workflow}
    except Exception as e:
        logger.error("[flow.comfyui.export] 失败: %s", e, exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"导出失败: {e}")


@router.post("/comfyui/import")
def import_comfyui(req: ComfyUIImportRequest):
    """ComfyUI workflow JSON → 白城主图（未知节点降级为可配置节点）"""
    _ensure_registered()
    from backend.flow_engine.adapters.comfyui_adapter import import_from_comfyui

    try:
        result = import_from_comfyui(req.workflow, registry)
        if not result.get("ok"):
            return err(ErrorCode.VALIDATION_ERROR, result.get("error", "导入失败"))
        return {
            "ok": True,
            "nodes": result["nodes"],
            "edges": result["edges"],
            "warnings": result.get("warnings", []),
        }
    except Exception as e:
        logger.error("[flow.comfyui.import] 失败: %s", e, exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"导入失败: {e}")
