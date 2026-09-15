# -*- coding: utf-8 -*-
"""
书斋 V65 - 视频分镜路由
POST /api/storyboard/generate
POST /api/storyboard/batch
GET  /api/storyboard/history
GET  /api/storyboard/history/{history_id}
DELETE /api/storyboard/history/{history_id}
GET  /api/storyboard/templates
POST /api/storyboard/templates
DELETE /api/storyboard/templates/{template_id}
"""
import logging
import threading
from typing import Any
from fastapi import APIRouter

from backend.services.storyboard_service import StoryboardService
from backend.task_manager import task_manager
from backend.api_models import err, ErrorCode
# SB-11: 统一模型（请求 + Pydantic 响应模型）
from backend.models.storyboard_models import (
    StoryboardRequest,
    BatchStoryboardRequest,
    TemplateRequest,
    AsyncStoryboardRequest,
    StoryboardGenerateResponse,
    StoryboardBatchResponse,
    StoryboardHistoryListResponse,
    StoryboardHistoryDetailResponse,
    TemplateListResponse,
    TemplateSaveResponse,
    TemplateDeleteResponse,
    OkResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/storyboard")


# 线程安全的懒加载 service 实例（避免多 worker 下竞态）
_service = None
_service_lock = threading.Lock()


def _get_service() -> StoryboardService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:  # 双重检查锁定
                _service = StoryboardService()
    return _service


@router.post("/generate", response_model=StoryboardGenerateResponse)
def generate_storyboard(data: StoryboardRequest):
    """
    生成视频分镜脚本

    接收小说文本片段，返回详细的分镜脚本，
    包含每个镜头的画面描述、运镜、光影、色彩、
    音效设计，以及可直接用于 AI 视频工具的提示词。
    """
    # 检查项目是否打开
    # 检查文本是否为空
    text = (data.text or "").strip()
    if not text:
        return err(ErrorCode.VALIDATION_ERROR, "文本为空，请提供需要生成分镜的小说片段")

    # 检查文本长度（至少 50 字才能生成有意义的分镜）
    if len(text) < 50:
        return err(ErrorCode.VALIDATION_ERROR, f"文本过短（{len(text)}字），至少需要50字")

    try:
        options = data.options or {}
        service = _get_service()
        result = service.generate(text=text, options=options)

        logger.info(
            f"[Storyboard] 生成成功 storyboard_id={result['storyboard_id']}, "
            f"shots_count={len(result['shots'])}, "
            f"style={result['global_style'].get('style_preset')}"
        )

        return {"ok": True, **result}

    except Exception as e:
        logger.error(f"[Storyboard] 生成失败: {e}", exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")


# ── 批量生成 ────────────────────────────────────────────

@router.post("/batch", response_model=StoryboardBatchResponse)
def batch_storyboard(data: BatchStoryboardRequest):
    """
    批量生成分镜：接受多个章节文本，为每个章节独立生成分镜

    Args:
        data: BatchStoryboardRequest
            - texts: [{"chapter_id": "xxx", "text": "..."}, ...]
            - options: 全局选项
    """
    texts = data.texts or []
    if not texts:
        return err(ErrorCode.VALIDATION_ERROR, "文本列表为空")

    # 过滤掉过短文本
    valid_texts = []
    for item in texts:
        if isinstance(item, dict):
            t = (item.get("text", "") or "").strip()
            if len(t) >= 50:
                valid_texts.append(item)

    if not valid_texts:
        return err(ErrorCode.VALIDATION_ERROR, "没有足够长的文本（至少50字）")

    try:
        options = data.options or {}
        service = _get_service()
        results = service.batch_generate(texts=valid_texts, options=options)

        logger.info(f"[Storyboard] 批量生成完成 count={len(results)}")
        return {"ok": True, "results": results, "total": len(results)}

    except Exception as e:
        logger.error(f"[Storyboard] 批量生成失败: {e}", exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")


# ── 历史管理 ────────────────────────────────────────────

@router.get("/history", response_model=StoryboardHistoryListResponse)
def get_history():
    """获取历史分镜列表（按时间倒序）"""
    try:
        service = _get_service()
        items = service.get_history()
        return {"ok": True, "items": items, "total": len(items)}
    except Exception as e:
        logger.error(f"[Storyboard] 获取历史失败: {e}", exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")


@router.get("/history/{history_id}", response_model=StoryboardHistoryDetailResponse)
def load_history(history_id: str):
    """加载指定历史分镜的完整数据"""
    try:
        service = _get_service()
        data = service.load_history(history_id)
        if data is None:
            return err(ErrorCode.NOT_FOUND, f"历史记录不存在: {history_id}")
        return {"ok": True, "history_id": history_id, **data}
    except Exception as e:
        logger.error(f"[Storyboard] 加载历史失败: {e}", exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")


@router.delete("/history/{history_id}", response_model=OkResponse)
def delete_history(history_id: str):
    """删除指定历史分镜"""
    try:
        service = _get_service()
        success = service.delete_history(history_id)
        if not success:
            return err(ErrorCode.NOT_FOUND, f"历史记录不存在: {history_id}")
        return {"ok": True, "deleted": history_id}
    except Exception as e:
        logger.error(f"[Storyboard] 删除历史失败: {e}", exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")


# ── 模板管理 ────────────────────────────────────────────

@router.get("/templates", response_model=TemplateListResponse)
def get_templates():
    """列出所有分镜模板"""
    try:
        service = _get_service()
        templates = service.get_templates()
        return {"ok": True, "templates": templates}
    except Exception as e:
        logger.error(f"[Storyboard] 获取模板失败: {e}", exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")


@router.post("/templates", response_model=TemplateSaveResponse)
def add_template(data: TemplateRequest):
    """新增或更新自定义模板"""
    try:
        service = _get_service()
        result = service.add_template(
            name=data.name,
            target_tool=data.target_tool,
            style_preset=data.style_preset,
            shot_density=data.shot_density,
        )
        return {"ok": True, **result}
    except Exception as e:
        logger.error(f"[Storyboard] 添加模板失败: {e}", exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")


@router.delete("/templates/{template_id}", response_model=TemplateDeleteResponse)
def delete_template(template_id: str):
    """删除模板（内置模板不可删除）"""
    try:
        service = _get_service()
        success = service.delete_template(template_id)
        if not success:
            return err(ErrorCode.VALIDATION_ERROR, f"无法删除模板（内置模板不可删除或模板不存在）: {template_id}")
        return {"ok": True, "deleted": template_id}
    except Exception as e:
        logger.error(f"[Storyboard] 删除模板失败: {e}", exc_info=True)
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")


# ═══════════════════════════════════════════
# P0-2 Phase 2：异步端点（后台任务模式）
# ═══════════════════════════════════════════

def _do_storyboard(
    info: Any,
    cancel_event: threading.Event,
    task_type: str,
    text: str,
    texts: list,
    options: dict,
):
    """后台线程中执行的分镜生成逻辑，支持取消令牌与进度上报。"""
    tid = info.task_id
    service = _get_service()
    options = options or {}

    if task_type == "generate":
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "文本为空"}
        if len(text) < 50:
            return {"ok": False, "error": f"文本过短（{len(text)}字），至少需要50字"}

        task_manager.update_progress(tid, 20, "正在生成分镜脚本...")
        if cancel_event.is_set():
            return {"ok": False, "cancelled": True}

        result = service.generate(text=text, options=options)
        task_manager.update_progress(tid, 100, "分镜生成完成")
        return {"ok": True, **result}

    elif task_type == "batch":
        valid_texts = []
        for item in (texts or []):
            if isinstance(item, dict):
                t = (item.get("text", "") or "").strip()
                if len(t) >= 50:
                    valid_texts.append(item)

        if not valid_texts:
            return {"ok": False, "error": "没有足够长的文本（至少50字）"}

        total = len(valid_texts)
        task_manager.update_progress(tid, 5, f"批量分镜生成开始，共 {total} 项")

        results = []
        for i, item in enumerate(valid_texts):
            if cancel_event.is_set():
                task_manager.update_progress(
                    tid, int((i / max(total, 1)) * 95), "已取消"
                )
                return {"ok": False, "cancelled": True, "results": results}

            progress = 5 + int((i / max(total, 1)) * 90)
            chapter_id = item.get("chapter_id", "")
            task_manager.update_progress(
                tid, progress,
                f"正在生成分镜 {i+1}/{total} ({chapter_id})...",
            )

            try:
                single_result = service.generate(text=item["text"], options=options)
                results.append(single_result)
            except Exception as e:
                logger.exception(f"批量分镜第 {i+1} 项失败")
                results.append({"error": str(e), "chapter_id": chapter_id})

        task_manager.update_progress(tid, 100, f"批量分镜完成，{len(results)}/{total}")
        return {"ok": True, "results": results, "total": len(results)}

    else:
        return {"ok": False, "error": f"未知的 task_type: {task_type}"}


@router.post("/start")
def storyboard_start(data: AsyncStoryboardRequest):
    """异步提交分镜生成任务，立即返回 task_id。"""
    task_id = task_manager.submit(
        "storyboard",
        _do_storyboard,
        data.task_type,
        data.text or "",
        data.texts or [],
        data.options or {},
    )
    return {"ok": True, "task_id": task_id}


@router.get("/status/{task_id}")
def storyboard_status(task_id: str):
    """查询异步分镜任务的状态与进度。"""
    info = task_manager.get_status(task_id)
    if info is None:
        return err(ErrorCode.NOT_FOUND, f"任务不存在: {task_id}")
    return {"ok": True, **info.to_dict()}


@router.post("/cancel/{task_id}")
def storyboard_cancel(task_id: str):
    """取消正在执行的异步分镜任务。"""
    ok = task_manager.cancel(task_id)
    if not ok:
        return err(ErrorCode.INTERNAL_ERROR, f"取消失败（任务不存在或已完成）")
    return {"ok": True, "cancelled": task_id}
