# -*- coding: utf-8 -*-
from fastapi import APIRouter, BackgroundTasks, Depends

from backend.services.project_service import state, get_generator, get_vector_memory
from backend.api_models import paginated, PaginationParams, err, ErrorCode
import logging

logger = logging.getLogger(__name__)

from ._utils import ChapterAdd, ChapterDelete, ChapterRename, ContentSave, _strip_edit_annotations, _update_writing_stats

router = APIRouter()

@router.get("/list")
def chapter_list(pagination: PaginationParams = Depends()):
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    chapters = [dict(ch) for ch in state.project.chapters]
    total = len(chapters)
    start = (pagination.page - 1) * pagination.page_size
    end = start + pagination.page_size
    page_items = chapters[start:end]
    return {
        **paginated(page_items, pagination.page, pagination.page_size, total),
        "current": state.project.meta.get("current_chapter", 0),
    }

@router.post("/add")
def add_chapter(data: ChapterAdd):
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    idx = state.project.add_chapter(data.title, data.vol_index)
    return {"ok": True, "index": idx}

@router.post("/delete")
def delete_chapter(data: ChapterDelete):
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    # 防御：越界/仅剩一章时明确报错，避免前端误以为删除成功（delete_chapter 内部会静默 return）
    if not (0 <= data.index < len(state.project.chapters)):
        return err(ErrorCode.INTERNAL_ERROR, "章节索引超出范围")
    if len(state.project.chapters) <= 1:
        return err(ErrorCode.INTERNAL_ERROR, "不能删除最后一章")
    state.project.delete_chapter(data.index)
    return {"ok": True}

@router.post("/rename")
def rename_chapter(data: ChapterRename):
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    if 0 <= data.index < len(state.project.chapters):
        state.project.chapters[data.index]["title"] = data.title
        state.project._save_meta()
        return {"ok": True}
    return err(ErrorCode.INTERNAL_ERROR, "章节索引超出范围")

@router.get("/load")
def load_chapter(index: int = 0):
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    content = state.project.get_content(index)
    title = state.project.chapters[index].get("title", "") if 0 <= index < len(state.project.chapters) else ""
    outline = ""
    blueprint = None
    if 0 <= index < len(state.project.chapters):
        outline = state.project.chapters[index].get("outline", "")
        blueprint = state.project.chapters[index].get("blueprint")
    return {"ok": True, "title": title, "content": content, "word_count": len(content), "outline": outline, "blueprint": blueprint}

def _post_save_analysis(project, content: str, index: int):
    """保存后的重计算：状态提取 + 向量记忆注入。
    在 BackgroundTasks 中异步执行，避免阻塞保存请求（大章节嵌入编码需几十秒）。
    失败仅记日志，不影响已完成的保存主流程。"""
    try:
        gen = get_generator()
        title = project.chapters[index].get("title", "") if index < len(project.chapters) else ""
        gen.apply_state_extraction(content, index + 1, title)
    except Exception as e:
        logger.warning(f"状态提取失败(后台): {e}")
    try:
        vm = get_vector_memory()
        if vm:
            from backend.services.vector_memory import MemoryType
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip() and len(p.strip()) > 50]
            title = project.chapters[index].get("title", "") if index < len(project.chapters) else ""
            for i, para in enumerate(paragraphs):
                vm.add_memory(
                    content=para,
                    memory_type=MemoryType.EVENT,
                    importance=0.6,
                    metadata={"chapter": index + 1, "chapter_title": title, "paragraph": i}
                )
            logger.info(f"向量记忆注入: 第{index+1}章 {len(paragraphs)}段")
    except Exception as e:
        logger.warning(f"向量记忆注入失败(后台): {e}")

@router.post("/save")
def save_chapter(data: ContentSave, background_tasks: BackgroundTasks):
    if not state.project: return {**err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目"), "warnings": []}
    old = state.project.get_content(data.index)
    warnings = []
    # 后端安全网：清除AI编辑批注
    content = _strip_edit_annotations(data.content)

    # 第一步：内容保存（主流程，失败直接返回错误）
    try:
        state.project.set_content(content, data.index)
    except Exception as e:
        logger.error(f"章节内容保存失败: {e}")
        return {**err(ErrorCode.INTERNAL_ERROR, f"内容保存失败: {e}"), "warnings": warnings}

    word_count = len(content)
    saved = old != content

    # 第二步：统计埋点（失败不影响主流程，记录警告）
    if saved:
        try:
            words_diff = len(content) - len(old)
            words_total = sum(ch.get("word_count", 0) for ch in state.project.chapters)
            _update_writing_stats(state.project.project_dir, data.index, words_diff, words_total)
        except Exception as e:
            msg = f"写作统计更新失败: {e}"
            logger.warning(msg)
            warnings.append(msg)

    # 第三/四步：状态提取 + 向量记忆注入（大章节嵌入编码很慢，异步后台执行，不阻塞保存响应）
    # 捕获当前 project 引用，避免后台任务执行时用户已切换项目导致写错项目
    if saved and len(content) > 500:
        background_tasks.add_task(_post_save_analysis, state.project, content, data.index)

    return {"ok": True, "saved": saved, "word_count": word_count, "warnings": warnings}

@router.post("/{index}/blueprint")
def save_chapter_blueprint(index: int, data: dict):
    """单独保存章节蓝图（含支线标记、人物节点等）"""
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    if index < 0 or index >= len(state.project.chapters):
        return err(ErrorCode.INTERNAL_ERROR, "章节索引越界")
    blueprint = data.get("blueprint", {})
    if not state.project.chapters[index].get("blueprint"):
        state.project.chapters[index]["blueprint"] = {}
    # 合并保存：保留原有字段，更新新字段
    state.project.chapters[index]["blueprint"].update(blueprint)
    state.project._save_meta()
    return {"ok": True}
