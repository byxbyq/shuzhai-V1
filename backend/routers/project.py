# -*- coding: utf-8 -*-
"""项目路由 — 项目管理核心 + 子路由 include"""
import os
import time
import shutil
import logging
from fastapi import APIRouter, Depends

from backend.services.project_service import state, create_project, open_project
from backend.project import NovelProject
from backend.api_models import paginated, PaginationParams
from backend.db import ProjectDB

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/project")

# ─── 请求模型 ───
from backend.routers.project_models import (
    ProjectCreate, ProjectOpen, ProjectDelete,
)

# ─── 项目管理核心 ───
@router.get("/status")
def api_status():
    return {"ok": True, "project": state.project.meta.get("title") if state.project else None, "version": "6.6"}

@router.post("/new")
def new_project(data: ProjectCreate):
    logger.info(f"创建新项目: title='{data.title}', genre='{data.genre}', chapters={data.length}")
    proj = create_project(data.title, data.genre, data.length)
    logger.info(f"项目创建成功: {proj.project_dir}")
    return {"ok": True, "title": data.title, "path": proj.project_dir}

@router.post("/open")
def open_project_route(data: ProjectOpen):
    logger.info(f"打开项目: {data.path}")
    proj = open_project(data.path)
    if not proj:
        logger.warning(f"项目打开失败: {data.path}")
        return {"ok": False, "error": "无法打开项目"}
    logger.info(f"项目打开成功: {proj.meta.get('title', '')}, 章节数: {len(proj.chapters)}")
    return {"ok": True, "title": proj.meta.get("title", ""), "chapters": len(proj.chapters)}

@router.get("/info")
def project_info():
    if not state.project:
        return {"ok": False, "error": "没有打开的项目"}
    return {
        "ok": True,
        "title": state.project.meta.get("title", ""),
        "genre": state.project.meta.get("genre", ""),
        "chapters": len(state.project.chapters),
        "current_chapter": state.project.meta.get("current_chapter", 0),
        "project_dir": state.project.project_dir,
        "planned_chapters": state.project.meta.get("planned_chapters", 0),
    }

@router.get("/list")
def list_projects(pagination: PaginationParams = Depends()):
    all_projects = NovelProject.list_all()
    total = len(all_projects)
    start = (pagination.page - 1) * pagination.page_size
    end = start + pagination.page_size
    return paginated(all_projects[start:end], pagination.page, pagination.page_size, total)

@router.post("/delete")
def delete_project(data: ProjectDelete):
    """删除小说项目（整个文件夹）"""
    project_dir = data.project_dir
    logger.info(f"删除项目请求: {project_dir}")
    # 安全检查：必须是 novel_projects 目录下的子目录
    base_dir = NovelProject._get_base_dir()
    if not project_dir.startswith(base_dir):
        logger.warning(f"删除项目失败: 非法路径 {project_dir}")
        return {"ok": False, "error": "非法路径"}
    if not os.path.exists(project_dir) or not os.path.isdir(project_dir):
        logger.warning(f"删除项目失败: 项目不存在 {project_dir}")
        return {"ok": False, "error": "项目不存在"}
    # 先释放对该项目数据库的占用（Windows 下打开的文件无法删除）
    if state.project and state.project.project_dir == project_dir:
        state.project = None
    ProjectDB.release(project_dir)
    # 重试删除：Windows 文件句柄释放有短暂延迟
    last_err = None
    for attempt in range(3):
        try:
            shutil.rmtree(project_dir)
            logger.info(f"项目删除成功: {project_dir}")
            return {"ok": True}
        except Exception as e:
            last_err = e
            time.sleep(0.5)
    logger.error(f"项目删除失败: {project_dir}, 错误: {last_err}")
    return {"ok": False, "error": "删除失败：文件被占用，请稍后重试"}

@router.post("/save")
def save_project():
    if not state.project: return {"ok": False, "error": "没有打开的项目"}
    state.project.save_all()
    return {"ok": True}



# ─── 子路由 include ───
from backend.routers.project_cards import router as cards_router
from backend.routers.project_workflow import router as workflow_router
from backend.routers.project_outline import router as outline_router
from backend.routers.project_volumes import router as volumes_router
from backend.routers.project_hooks import router as hooks_router
from backend.routers.project_rename import router as rename_router
from backend.routers.project_state_memory import router as state_memory_router
from backend.services.project_diagnosis import router as diagnosis_router

router.include_router(cards_router)
router.include_router(workflow_router)
router.include_router(outline_router)
router.include_router(volumes_router)
router.include_router(hooks_router)
router.include_router(rename_router)
router.include_router(state_memory_router)
router.include_router(diagnosis_router)
