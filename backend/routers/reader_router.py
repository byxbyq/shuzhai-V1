# -*- coding: utf-8 -*-
"""阅读器路由 - /api/reader/*
   支持阅读任意项目（不依赖 state.project 单例），阅读进度持久化。
"""
import os
import json
import time
from fastapi import APIRouter
from pydantic import BaseModel

from backend.runtime_paths import get_projects_dir, get_data_dir
from backend.api_models import err, ErrorCode
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reader")


def _reader_data_file():
    """阅读进度/书架数据的JSON文件路径（按用户隔离）"""
    base = get_data_dir()
    user_dir = os.path.join(base, 'users', _get_user())
    os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, 'reader_data.json')


def _get_user():
    from backend.runtime_paths import get_current_user
    return get_current_user()


def _load_reader_data():
    """加载阅读器数据（进度 + 书架）"""
    f = _reader_data_file()
    if os.path.exists(f):
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                return json.load(fh)
        except Exception as e:
            logger.warning("加载阅读器数据失败: %s", e)
    return {"progress": {}, "bookshelf": []}


def _save_reader_data(data):
    """保存阅读器数据"""
    f = _reader_data_file()
    with open(f, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _read_project_meta(project_path):
    """直接从文件读取项目元数据（不依赖 state.project）"""
    meta_file = os.path.join(project_path, 'project.json')
    if not os.path.exists(meta_file):
        return None
    try:
        with open(meta_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning("读取项目元数据失败: %s", e)
        return None


def _read_chapter_content(project_path, chapter_index):
    """直接从文件读取章节内容"""
    data = _read_project_meta(project_path)
    if not data:
        return None
    chapters = data.get('chapters', [])
    if chapter_index < 0 or chapter_index >= len(chapters):
        return None
    ch = chapters[chapter_index]
    ch_idx = ch.get('index', chapter_index + 1)
    cf = os.path.join(project_path, 'chapters', f'chapter_{ch_idx:03d}.txt')
    content = ''
    if os.path.exists(cf):
        with open(cf, 'r', encoding='utf-8') as f:
            content = f.read()
    return {
        'title': ch.get('title', f'第{chapter_index+1}章'),
        'content': content,
        'word_count': len(content),
    }


def _get_project_name(project_path):
    """从路径提取项目名"""
    return os.path.basename(project_path.rstrip('/\\'))


# ── API 路由 ──

@router.get("/bookshelf")
def get_bookshelf():
    """获取书架：当前用户项目 + 默认项目库"""
    data = _load_reader_data()
    books = []
    seen_paths = set()

    # 1. 当前用户的项目
    user_dir = get_projects_dir()
    # 2. 默认项目库（所有用户可读）
    default_dir = os.path.join(get_data_dir(), 'novel_projects')

    for projects_dir in [user_dir, default_dir]:
        if not os.path.exists(projects_dir):
            continue
        for name in os.listdir(projects_dir):
            full = os.path.join(projects_dir, name)
            meta_path = os.path.join(full, 'project.json')
            if not (os.path.isdir(full) and os.path.exists(meta_path)):
                continue
            if full in seen_paths:
                continue
            seen_paths.add(full)
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    pdata = json.load(f)
                meta = pdata.get('meta', {})
                chapters = pdata.get('chapters', [])
                total_words = sum(c.get('word_count', 0) for c in chapters)
                if len(chapters) == 0:
                    continue  # 跳过没有章节的项目

                # 阅读进度
                prog = data.get('progress', {}).get(full, {})

                books.append({
                    'path': full,
                    'name': name,
                    'title': meta.get('title', name),
                    'genre': meta.get('genre', ''),
                    'chapter_count': len(chapters),
                    'total_words': total_words,
                    'modified': meta.get('modified', ''),
                    'reading': {
                        'chapter': prog.get('chapter', 0),
                        'scroll': prog.get('scroll', 0),
                        'updated': prog.get('updated', ''),
                    },
                    'is_favorite': full in data.get('bookshelf', []),
                })
            except Exception as e:
                logger.warning(f"读取项目 {name} 失败: {e}")

    books.sort(key=lambda x: x.get('modified', ''), reverse=True)
    return {"ok": True, "books": books}


@router.get("/chapter")
def reader_load_chapter(project: str, index: int):
    """加载指定项目的指定章节（阅读模式）"""
    result = _read_chapter_content(project, index)
    if result is None:
        # 尝试获取章节列表
        data = _read_project_meta(project)
        if data is None:
            return err(ErrorCode.NOT_FOUND, "项目不存在")
        return err(ErrorCode.NOT_FOUND, "章节不存在")

    # 同时返回章节列表
    pdata = _read_project_meta(project)
    chapters = pdata.get('chapters', []) if pdata else []
    chapter_list = [{'title': c.get('title', ''), 'word_count': c.get('word_count', 0)} for c in chapters]
    meta = pdata.get('meta', {}) if pdata else {}

    return {
        "ok": True,
        "title": result['title'],
        "content": result['content'],
        "word_count": result['word_count'],
        "chapter_index": index,
        "total_chapters": len(chapters),
        "chapter_list": chapter_list,
        "project_title": meta.get('title', _get_project_name(project)),
    }


class ProgressSave(BaseModel):
    project: str
    chapter: int
    scroll: float = 0.0

@router.post("/progress")
def save_progress(data: ProgressSave):
    """保存阅读进度"""
    rdata = _load_reader_data()
    rdata.setdefault('progress', {})[data.project] = {
        'chapter': data.chapter,
        'scroll': data.scroll,
        'updated': time.strftime('%Y-%m-%d %H:%M'),
    }
    _save_reader_data(rdata)
    return {"ok": True}


@router.get("/progress")
def get_progress(project: str):
    """获取某项目的阅读进度"""
    rdata = _load_reader_data()
    prog = rdata.get('progress', {}).get(project, {})
    return {"ok": True, "progress": prog}


class BookshelfToggle(BaseModel):
    project: str

@router.post("/bookshelf/toggle")
def toggle_bookshelf(data: BookshelfToggle):
    """添加/移除书架收藏"""
    rdata = _load_reader_data()
    shelf = rdata.get('bookshelf', [])
    if data.project in shelf:
        shelf.remove(data.project)
        in_shelf = False
    else:
        shelf.append(data.project)
        in_shelf = True
    rdata['bookshelf'] = shelf
    _save_reader_data(rdata)
    return {"ok": True, "in_bookshelf": in_shelf}
