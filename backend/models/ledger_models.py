# -*- coding: utf-8 -*-
"""书斋 V66 - Truth Ledger 数据模型（从 ledger.py 拆分）"""
from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class CharacterState:
    name: str
    location: str = ""
    emotion: str = ""
    health: str = "正常"
    realm: str = ""               # 修炼等级
    relationships: Dict[str, str] = field(default_factory=dict)
    possessions: List[str] = field(default_factory=list)
    secrets_known: List[str] = field(default_factory=list)
    last_seen_chapter: int = 0
    is_alive: bool = True
    arc_stage: str = ""
    archived: bool = False        # 归档标志：已退场/死亡角色归档后可在回忆/提及中自由使用

@dataclass
class Foreshadowing:
    id: str
    content: str
    planted_chapter: int
    planted_paragraph: str = ""
    expected_recovery_chapter: int = 0
    status: str = "planted"       # planted → active → recovered → abandoned
    related_characters: List[str] = field(default_factory=list)
    related_items: List[str] = field(default_factory=list)
    deadline_chapter: int = 0
    recovery_chapter: int = 0
    note: str = ""
    # H4: 悬念编排策略扩展字段
    arc_type: str = ""             # 悬念弧线类型: short(2-3章) / medium(5-8章) / long(全书)
    strength: int = 2              # 悬念强度 1-5 (1好奇/2关切/3迫切/4生存/5终极)
    hook_type: str = ""            # 钩子类型（13式之一）：突然揭示/紧急危机/未完成动作/身份反转/两难选择/神秘线索/时间限制/承诺威胁/离奇消失/言外之意/意象钩子/回声钩子/留白钩子

@dataclass
class ChapterLog:
    chapter: int
    title: str
    summary: str = ""
    characters: List[str] = field(default_factory=list)
    word_count: int = 0
    location: str = ""
    importance: str = "normal"
    key_choices: List[str] = field(default_factory=list)
    costs: List[str] = field(default_factory=list)
    new_foreshadowing: List[str] = field(default_factory=list)
    resolved_foreshadowing: List[str] = field(default_factory=list)
    character_changes: Dict[str, dict] = field(default_factory=dict)
    strand_type: str = ""           # H1: Strand Weave 线型 Q(Quest)/F(Fire)/C(Constellation)


@dataclass
class Artifact:
    """道具/功法设定"""
    id: str
    name: str
    type: str = ""                  # weapon / pill / technique / treasure / misc
    grade: str = ""                 # 品级：凡/灵/仙/神/圣
    owner: str = ""
    description: str = ""
    created_at: str = ""
    destroyed: bool = False


@dataclass
class Faction:
    """势力/组织设定"""
    id: str
    name: str
    type: str = ""                  # 宗门/家族/王朝/帮派/散修联盟
    leader: str = ""
    members: List[str] = field(default_factory=list)
    description: str = ""
    status: str = "active"          # active / disbanded / destroyed


@dataclass
class Location:
    """地点设定"""
    id: str
    name: str
    type: str = ""                  # city / mountain / sect / cave / misc
    description: str = ""
    first_seen_chapter: int = 0
    faction: str = ""               # 所属势力


@dataclass
class SubplotState:
    """支线追踪状态 — 独立于主线的支线剧情追踪

    状态机: dormant → active → advancing → resolved / abandoned
    """
    id: str
    title: str                        # 支线名称
    description: str = ""             # 支线描述
    status: str = "dormant"           # dormant(潜伏) → active(启动) → advancing(推进中) → resolved(已解决) / abandoned(已放弃)
    start_chapter: int = 0            # 开始章节
    last_progress_chapter: int = 0    # 最近推进章节
    resolve_chapter: int = 0          # 解决章节
    related_characters: List[str] = field(default_factory=list)  # 关联角色
    related_locations: List[str] = field(default_factory=list)   # 关联地点
    key_events: List[str] = field(default_factory=list)          # 关键事件记录
    priority: int = 2                 # 裁剪优先级: 1(高,主线关联) 2(中) 3(低)
    target_chapter: int = 0           # 预期解决章节
    note: str = ""                    # 备注


@dataclass
class Snapshot:
    """叙事状态快照 — 全书剧情节点完整副本"""
    snapshot_id: str
    version: int
    timestamp: str
    chapter: int
    data: dict                     # 完整 ledger 数据的深拷贝
