# -*- coding: utf-8 -*-
"""书斋 V66 - 项目管理（薄组合类）

职责拆分：
  - project_base.py     → ProjectBaseMixin     基础设施 + 持久化 + 项目创建/打开/列表
  - project_chapters.py → ProjectChaptersMixin  章节 CRUD + 快照 + 前文上下文
  - project_volumes.py  → ProjectVolumesMixin   卷 CRUD + 自动重建 + 大纲解析
  - project_content.py  → ProjectContentMixin   大纲读写 + 全书大纲 + 灵感卡片 + 伏笔
"""
from backend.project_base import ProjectBaseMixin
from backend.project_chapters import ProjectChaptersMixin
from backend.project_volumes import ProjectVolumesMixin
from backend.project_content import ProjectContentMixin


class NovelProject(ProjectBaseMixin, ProjectChaptersMixin, ProjectVolumesMixin, ProjectContentMixin):
    """小说项目 — 724行上帝类已拆为 4 个独立 Mixin，此处仅负责组合"""

    def __init__(self):
        self._init_project_fields()