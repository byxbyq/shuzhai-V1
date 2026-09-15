# -*- coding: utf-8 -*-
"""分镜 API 响应模型（SB-11 Shot 数据模型 Pydantic 化）

从 routers/storyboard.py 拆分的 Pydantic 模型：
  - 请求模型：StoryboardRequest / BatchStoryboardRequest / TemplateRequest / AsyncStoryboardRequest
  - 响应模型：StoryboardShotOut / StoryboardGlobalStyleOut / StoryboardGenerateResponse / ...
为 /generate、/batch、/history、/templates 等端点提供 OpenAPI 文档与响应校验。
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════
# 请求模型
# ═══════════════════════════════════════════

class StoryboardRequest(BaseModel):
    """分镜生成请求"""
    chapter_id: str = Field(default="", description="章节ID（可选，用于关联）")
    text: str = Field(..., description="小说文本片段（必填）")
    text_range: Optional[Dict[str, Any]] = Field(default=None, description="文本范围 {start, end}（可选）")
    options: Optional[Dict[str, Any]] = Field(default=None, description="生成选项 {target_tool, style_preset, shot_density, max_shots, language}")


class BatchStoryboardItem(BaseModel):
    """批量生成单项"""
    chapter_id: str = ""
    text: str = ""


class BatchStoryboardRequest(BaseModel):
    """批量生成请求"""
    texts: List[Dict[str, Any]] = Field(default_factory=list, description='[{"chapter_id": "xxx", "text": "..."}, ...]')
    options: Optional[Dict[str, Any]] = None


class TemplateRequest(BaseModel):
    """模板请求"""
    name: str
    target_tool: str = "通用"
    style_preset: str = "默认"
    shot_density: str = "medium"


class AsyncStoryboardRequest(BaseModel):
    """异步分镜请求"""
    task_type: str = "generate"  # generate | batch
    text: str = ""
    texts: List[Dict[str, Any]] = Field(default_factory=list)
    options: Optional[Dict[str, Any]] = None


# ═══════════════════════════════════════════
# 响应模型（SB-11）
# ═══════════════════════════════════════════

class CharacterPositionOut(BaseModel):
    """画面中的角色位置"""
    name: str = ""
    position: str = ""
    action: str = ""


class StoryboardShotOut(BaseModel):
    """单个分镜镜头（13 字段 Pydantic 化，对齐 StoryboardShot dataclass）"""
    index: int
    source_text: str = ""
    shot_type: str = "中景"
    camera_movement: str = "静态"
    duration_sec: float = 4.0
    transition: str = "切"
    lighting: str = ""
    color_palette: str = ""
    character_positions: List[CharacterPositionOut] = Field(default_factory=list)
    scene_description: str = ""
    sound_design: str = ""
    prompt_full: str = ""
    prompt_short: str = ""


class StoryboardGlobalStyleOut(BaseModel):
    """全局风格信息"""
    style_preset: str = "默认"
    target_tool: str = "通用"
    shot_density: str = "medium"
    language: str = "zh"
    style_notes: str = ""
    tool_guide: Dict[str, Any] = Field(default_factory=dict)


class StoryboardGenerateResponse(BaseModel):
    """分镜生成成功响应"""
    ok: bool = True
    storyboard_id: str = ""
    shots: List[StoryboardShotOut] = Field(default_factory=list)
    global_style: StoryboardGlobalStyleOut = Field(default_factory=StoryboardGlobalStyleOut)
    warnings: Optional[List[str]] = None
    world_conflicts: Optional[List[Dict[str, Any]]] = None


class StoryboardBatchResponse(BaseModel):
    """批量分镜生成响应"""
    ok: bool = True
    results: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class StoryboardHistoryItem(BaseModel):
    """历史记录条目"""
    history_id: str = ""
    chapter_id: str = ""
    storyboard_id: str = ""
    title: str = ""
    created_at: str = ""
    shots_count: int = 0
    style: str = ""


class StoryboardHistoryListResponse(BaseModel):
    """历史列表响应"""
    ok: bool = True
    items: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class StoryboardHistoryDetailResponse(BaseModel):
    """历史详情响应"""
    ok: bool = True
    history_id: str = ""
    chapter_id: str = ""
    storyboard_id: str = ""
    timestamp: Optional[int] = None
    shots: List[StoryboardShotOut] = Field(default_factory=list)
    global_style: StoryboardGlobalStyleOut = Field(default_factory=StoryboardGlobalStyleOut)
    warnings: Optional[List[str]] = None


class TemplateOut(BaseModel):
    """分镜模板条目"""
    template_id: str = ""
    name: str = ""
    target_tool: str = ""
    style_preset: str = ""
    shot_density: str = ""
    is_builtin: bool = False


class TemplateSaveResponse(BaseModel):
    """新增/更新模板响应"""
    ok: bool = True
    created: Optional[bool] = None
    updated: Optional[bool] = None
    name: str = ""
    target_tool: str = ""
    style_preset: str = ""
    shot_density: str = ""


class TemplateDeleteResponse(BaseModel):
    """删除模板响应"""
    ok: bool = True
    deleted: str = ""


class TemplateListResponse(BaseModel):
    """模板列表响应"""
    ok: bool = True
    templates: List[Dict[str, Any]] = Field(default_factory=list)


class OkResponse(BaseModel):
    """通用成功响应"""
    ok: bool = True
