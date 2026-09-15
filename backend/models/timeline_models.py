# -*- coding: utf-8 -*-
"""时间线 API 请求模型（从 routers/timeline.py 拆分）"""
from pydantic import BaseModel


class PlannedUpdate(BaseModel):
    planned: str

class ActualUpdate(BaseModel):
    actual: str
    divergences: list = []

class AnnotationUpdate(BaseModel):
    annotation: str

class DivergenceStatusUpdate(BaseModel):
    divergence_index: int
    status: str  # 待处理 / 已接受 / 已修复

class DivergenceUpdate(BaseModel):
    divergence_index: int
    type: str = ""
    item: str = ""
    note: str = ""
    status: str = ""  # 可选更新

class DivergenceAdd(BaseModel):
    type: str = "修改"
    item: str = ""
    note: str = ""
    status: str = "待处理"

class CompareRequest(BaseModel):
    chapter_index: int = 0
    planned_text: str = ""  # 计划文本（章节大纲），空则从项目读取
    chapter_text: str = ""  # 正文，空则从项目读取

class DivergenceFixRequest(BaseModel):
    """AI修复偏离的请求体"""
    pass
