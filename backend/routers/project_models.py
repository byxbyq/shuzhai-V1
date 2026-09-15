# -*- coding: utf-8 -*-
"""项目请求模型 — 所有 Pydantic 模型"""
from pydantic import BaseModel
from typing import Optional, Dict, List

class ProjectCreate(BaseModel):
    title: str
    genre: str = ""
    length: int = 10

class ProjectOpen(BaseModel):
    path: str

class SettingsUpdate(BaseModel):
    world_settings: Optional[Dict] = None
    character_settings: Optional[Dict] = None
    characters: Optional[list] = None  # 人物档案列表
    narrative_style: Optional[Dict] = None  # 叙事风格
    era: Optional[Dict] = None  # 时代环境
    world_rules: Optional[list] = None  # 通用世界规则


class BrainstormCardsSave(BaseModel):
    cards: list
    graph: Optional[dict] = None  # C3: 图谱视图数据 {positions, edges}


class PlanningCardsSave(BaseModel):
    """连线框画布数据保存"""
    nodes: list = []           # 节点数组 [{id, type, title, summary, quotes, x, y, color, chapter_ref}]
    edges: list = []           # 连线数组 [{id, from, to, label, arrow}]
    meta: Optional[dict] = None  # 元信息 {last_saved, viewport...}


class OutlineSave(BaseModel):
    outline: str


class NovelOutlineSave(BaseModel):
    novel_outline: dict  # 全书大纲（dict格式：theme/core_conflict/story_arc/...）


class HookAdd(BaseModel):
    content: str
    chapter_index: int = 0
    status: str = "planned"
    deadline_chapter: Optional[int] = None
    # 伏笔对话框字段：planted_chapter 优先于 chapter_index；expected 同时写入 deadline
    planted_chapter: Optional[int] = None
    expected_recovery_chapter: Optional[int] = None
    related_characters: Optional[list] = None
    note: str = ""


class HookAdvance(BaseModel):
    id: str
    chapter_index: int = 0


class HookRecover(BaseModel):
    id: str
    chapter_index: int = 0


class HookAbandon(BaseModel):
    id: str
    reason: str = ""
# Volume models
class VolumeAdd(BaseModel):
    title: str
    outline: str = ""
    start_chapter: int = 0
    end_chapter: int = 0

class VolumeOp(BaseModel):
    vol_index: int

class VolumeRename(BaseModel):
    vol_index: int
    title: str

class VolumeOutlineUpdate(BaseModel):
    summary: str = ""
    theme: str = ""
    key_events: list = []
    character_arcs: list = []


class AIVolumeSplitRequest(BaseModel):
    volume_count: Optional[int] = None
    total_chapters: Optional[int] = None
    inspiration: Optional[str] = ""

class VolumeChapterRequest(BaseModel):
    chapter_index: int

class VolumeChaptersRequest(BaseModel):
    chapter_indices: List[int]
# Planning
class PlanningCheckRequest(BaseModel):
    """连线框对照校验请求（前端 wireframe-canvas 传 nodes/edges/chapter_text；
    原模型为空导致路由内 req.nodes 属性访问必招 AttributeError）"""
    nodes: List[dict] = []
    edges: List[dict] = []
    chapter_text: str = ""
# Diagnosis/Rename
class ProjectDelete(BaseModel):
    project_dir: str

class RenameEntity(BaseModel):
    old_name: str
    new_name: str
    scope: str = "all"  # all / characters / world_settings / outline / content

