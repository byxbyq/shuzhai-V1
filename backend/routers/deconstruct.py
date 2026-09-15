# -*- coding: utf-8 -*-
"""
书斋 V64 - 拆书分析路由
挂载在 /api/deconstruct/*
"""
import logging
import threading
from typing import Any, List
from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.project_service import state
from backend.services.deconstruct_service import DeconstructService
from backend.task_manager import task_manager
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/deconstruct")


# ============================================================
# 请求模型
# ============================================================

class AnalyzeRequest(BaseModel):
    content: str
    source_type: str = "paste"  # paste | file
    dimensions: list = ["structure", "characters", "worldbuilding", "theme", "plot_mechanics"]
    target_genre: str = ""


class TransformRequest(BaseModel):
    deconstruction: dict
    user_vision: dict  # {genre, tone, core_idea, constraints, ...}


class DimensionRequest(BaseModel):
    summary: str
    dimension: str  # structure | characters | worldbuilding | theme | plot_mechanics
    content_sample: str = ""


class ChunkSummarizeRequest(BaseModel):
    content: str
    chunk_index: int = 0
    total_chunks: int = 1


class ChunkMergeRequest(BaseModel):
    chunk_summaries: list  # ["摘要1", "摘要2", ...]


# ============================================================
# 端点
# ============================================================

@router.post("/chunk/summarize")
def chunk_summarize(data: ChunkSummarizeRequest):
    """增量拆书-第1步: 对单个文本块进行摘要"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    try:
        service = DeconstructService(state.project.project_dir)
        summary = service._summarize_chunk(data.content)
        return {"ok": True, "summary": summary, "chunk_index": data.chunk_index}
    except Exception as e:
        logger.error(f"分块摘要失败: {e}", exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")


@router.post("/chunk/merge")
def chunk_merge(data: ChunkMergeRequest):
    """增量拆书-第2步: 合并所有块摘要为全书梗概"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    try:
        service = DeconstructService(state.project.project_dir)
        merged = "\n\n---\n\n".join(data.chunk_summaries)
        # 如果合并后仍超过12000字，递归摘要
        if len(merged) > 12000 and len(data.chunk_summaries) > 2:
            mid = len(data.chunk_summaries) // 2
            part1 = service._summarize_chunk("\n\n".join(data.chunk_summaries[:mid]))
            part2 = service._summarize_chunk("\n\n".join(data.chunk_summaries[mid:]))
            merged = part1 + "\n\n" + part2
        # 最终摘要
        summary = service._summarize_chunk(merged[:10000]) if len(merged) > 5000 else merged
        return {"ok": True, "summary": summary}
    except Exception as e:
        logger.error(f"合并摘要失败: {e}", exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")


@router.post("/chunk/analyze")
def chunk_analyze(data: DimensionRequest):
    """增量拆书-第3步: 对单个维度进行分析"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    try:
        service = DeconstructService(state.project.project_dir)
        result = service.analyze_dimension(
            summary=data.summary,
            dimension=data.dimension,
            content_sample=data.content_sample,
        )
        return {"ok": True, "dimension": data.dimension, "result": result}
    except Exception as e:
        logger.error(f"维度分析失败: {e}", exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")


@router.post("/chunk/meta")
def chunk_meta(data: ChunkSummarizeRequest):
    """增量拆书-第0步: 提取源作品元信息"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    try:
        service = DeconstructService(state.project.project_dir)
        meta = service._extract_source_meta(data.content, len(data.content))
        return {"ok": True, "meta": meta}
    except Exception as e:
        logger.error(f"元信息提取失败: {e}", exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")

@router.post("/analyze")
def deconstruct_analyze(data: AnalyzeRequest):
    """
    拆书分析：接收文本内容，返回完整多维度拆书结果
    """
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")

    content = data.content.strip()
    if not content:
        return err(ErrorCode.VALIDATION_ERROR, "内容为空，请粘贴或上传待分析的小说文本")

    if len(content) < 100:
        return err(ErrorCode.VALIDATION_ERROR, "文本过短（少于100字），无法进行有意义的分析")

    try:
        service = DeconstructService(state.project.project_dir)

        dimensions = data.dimensions if data.dimensions else service.DEFAULT_DIMENSIONS

        logger.info(
            f"拆书分析请求: {len(content)}字, "
            f"source_type={data.source_type}, "
            f"dimensions={dimensions}"
        )

        # 执行拆书
        result = service.deconstruct(
            content=content,
            dimensions=dimensions,
            on_progress=None,  # 同步调用，暂不需要进度回调
        )

        # 统计各维度是否成功
        dimension_status = {}
        for dim in dimensions:
            dim_data = result.get(dim, {})
            dimension_status[dim] = {
                "label": service.DIMENSION_LABELS.get(dim, dim),
                "empty": not bool(dim_data),
            }

        return {
            "ok": True,
            "result": result,
            "stats": {
                "word_count": len(content),
                "dimensions_analyzed": len(dimensions),
                "dimension_status": dimension_status,
            },
        }

    except Exception as e:
        logger.error(f"拆书分析失败: {e}", exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"拆书分析失败: {str(e)}")


@router.post("/transform")
def deconstruct_transform(data: TransformRequest):
    """
    转化拆书结果：将拆书报告转化为用户自己的世界观+角色+大纲
    """
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")

    deconstruction = data.deconstruction
    user_vision = data.user_vision

    if not deconstruction:
        return err(ErrorCode.VALIDATION_ERROR, "拆书结果为空，请先执行拆书分析")

    if not user_vision:
        return err(ErrorCode.VALIDATION_ERROR, "用户构想为空，请填写类型、风格、核心创意等信息")

    try:
        service = DeconstructService(state.project.project_dir)

        logger.info(
            f"转化请求: genre={user_vision.get('genre', '未知')}, "
            f"tone={user_vision.get('tone', '未知')}"
        )

        result = service.transform(deconstruction, user_vision)

        # 统计生成结果
        worldview_count = len(result.get("worldview_cards", []))
        character_count = len(result.get("character_cards", []))
        chapter_count = len(result.get("outline_blueprint", {}).get("chapters", []))

        return {
            "ok": True,
            "result": result,
            "stats": {
                "worldview_cards": worldview_count,
                "character_cards": character_count,
                "chapters": chapter_count,
            },
        }

    except Exception as e:
        logger.error(f"转化失败: {e}", exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"转化失败: {str(e)}")


@router.post("/dimension")
def deconstruct_dimension(data: DimensionRequest):
    """
    单独分析某一维度（用于重新分析或细化）
    """
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")

    if not data.summary.strip():
        return err(ErrorCode.VALIDATION_ERROR, "摘要为空，请提供全书梗概")

    valid_dims = ["structure", "characters", "worldbuilding", "theme", "plot_mechanics"]
    if data.dimension not in valid_dims:
        return err(ErrorCode.VALIDATION_ERROR, f"无效维度: {data.dimension}，有效维度: {valid_dims}")

    try:
        service = DeconstructService(state.project.project_dir)

        logger.info(f"单维度分析: {data.dimension}")

        result = service.analyze_dimension(
            summary=data.summary,
            dimension=data.dimension,
            content_sample=data.content_sample,
        )

        return {
            "ok": True,
            "dimension": data.dimension,
            "result": result,
            "empty": not bool(result),
        }

    except Exception as e:
        logger.error(f"单维度分析失败: {e}", exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"分析失败: {str(e)}")


@router.get("/dimensions")
def get_supported_dimensions():
    """
    获取支持的拆书维度列表
    """
    return {
        "ok": True,
        "dimensions": [
            {"key": "structure", "label": "叙事结构", "desc": "分析小说的幕结构、节奏曲线和章节组织"},
            {"key": "characters", "label": "人物体系", "desc": "分析主角、反派、配角以及人物关系网络"},
            {"key": "worldbuilding", "label": "世界观设定", "desc": "分析力量体系、地理、社会结构和独特规则"},
            {"key": "theme", "label": "主题思想", "desc": "分析核心主题、反复出现的母题和价值冲突"},
            {"key": "plot_mechanics", "label": "情节技法", "desc": "分析钩子、悬念、揭示模式和反转设计"},
        ],
    }


# ═══════════════════════════════════════════
# P0-2 Phase 2：异步端点（后台任务模式）
# ═══════════════════════════════════════════

class AsyncDeconstructRequest(BaseModel):
    """异步拆书请求"""
    content: str
    source_type: str = "paste"
    dimensions: list = ["structure", "characters", "worldbuilding", "theme", "plot_mechanics"]
    target_genre: str = ""


def _do_deconstruct(
    info: Any,
    cancel_event: threading.Event,
    content: str,
    source_type: str,
    dimensions: List[str],
    target_genre: str,
):
    """后台线程中执行的拆书逻辑，支持取消令牌与进度上报。"""
    if not state.project:
        return {"ok": False, "error": "没有打开的项目"}

    tid = info.task_id
    content = content.strip()
    if not content:
        return {"ok": False, "error": "内容为空"}
    if len(content) < 100:
        return {"ok": False, "error": "文本过短（少于100字）"}

    service = DeconstructService(state.project.project_dir)
    valid_dims = [d for d in dimensions if d in service.DEFAULT_DIMENSIONS]
    if not valid_dims:
        return {"ok": False, "error": "未指定有效维度"}

    task_manager.update_progress(tid, 5, f"拆书分析开始，{len(content)}字，{len(valid_dims)}个维度")

    # 五维串行拆解，逐维度上报进度
    result = {}
    for i, dim in enumerate(valid_dims):
        if cancel_event.is_set():
            task_manager.update_progress(
                tid, int((i / max(len(valid_dims), 1)) * 95), "已取消"
            )
            return {"ok": False, "cancelled": True, "result": result}

        progress = 5 + int((i / max(len(valid_dims), 1)) * 90)
        task_manager.update_progress(
            tid, progress,
            f"正在分析 {service.DIMENSION_LABELS.get(dim, dim)}...",
        )

        try:
            # 单维度拆解需要先构建摘要
            summary = service._summarize_chunk(content[:5000]) if i == 0 else (
                service._summarize_chunk(content[:3000])
            )
            dim_result = service.analyze_dimension(
                summary=summary,
                dimension=dim,
                content_sample=content[:2000],
            )
            result[dim] = dim_result
        except Exception as e:
            logger.exception(f"维度 {dim} 分析异常")
            result[dim] = {"error": str(e)}

    task_manager.update_progress(tid, 98, "拆书分析完成，整理结果...")

    # 统计各维度状态
    dimension_status = {}
    for dim in valid_dims:
        dim_data = result.get(dim, {})
        dimension_status[dim] = {
            "label": service.DIMENSION_LABELS.get(dim, dim),
            "empty": not bool(dim_data) or dim_data.get("error") is not None,
        }

    return {
        "ok": True,
        "result": result,
        "stats": {
            "word_count": len(content),
            "dimensions_analyzed": len(valid_dims),
            "dimension_status": dimension_status,
        },
    }


@router.post("/start")
def deconstruct_start(data: AsyncDeconstructRequest):
    """异步提交拆书分析任务，立即返回 task_id。"""
    task_id = task_manager.submit(
        "deconstruct",
        _do_deconstruct,
        data.content,
        data.source_type,
        data.dimensions,
        data.target_genre,
    )
    return {"ok": True, "task_id": task_id}


@router.get("/status/{task_id}")
def deconstruct_status(task_id: str):
    """查询异步拆书任务的状态与进度。"""
    info = task_manager.get_status(task_id)
    if info is None:
        return err(ErrorCode.NOT_FOUND, f"任务不存在: {task_id}")
    return {"ok": True, **info.to_dict()}


@router.post("/cancel/{task_id}")
def deconstruct_cancel(task_id: str):
    """取消正在执行的异步拆书任务。"""
    ok = task_manager.cancel(task_id)
    if not ok:
        return err(ErrorCode.INTERNAL_ERROR, f"取消失败（任务不存在或已完成）")
    return {"ok": True, "cancelled": task_id}
