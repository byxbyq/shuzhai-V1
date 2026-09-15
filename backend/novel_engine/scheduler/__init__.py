# -*- coding: utf-8 -*-
"""
scheduler 包 - 世界时间轴、角色泳道管理、目标调度、碰撞检测、一致性校验、规则守卫

二期模块：
1. world_timeline - 世界时间轴（WorldTick, WorldTimeline）
2. swimlane_manager - 角色泳道管理器（LifecycleStage, ActionRecord, CharacterSwimlane, SwimlaneManager）
3. goal_scheduler - 目标调度器（GoalStatus, GoalLevel, Goal, GoalScheduler）

三期模块：
4. causal_collision_scheduler - 因果碰撞调度器（CollisionRecord, CausalCollisionScheduler）
5. consistency_checker - 全局一致性校验器（CheckLevel, ConsistencyIssue, ConsistencyChecker）
6. world_rule_guard - 世界观规则守卫层（GuardLevel, WorldRule, GuardViolation, WorldRuleGuard）

四期模块：
7. timeline_branch - 时序回溯分支存档（BranchNode, WorldSnapshot, TimelineBranch）
"""

# ─── 二期模块 ───
from .world_timeline import WorldTick, WorldTimeline
from .swimlane_manager import (
    LifecycleStage,
    ActionRecord,
    CharacterSwimlane,
    SwimlaneManager,
)
from .goal_scheduler import (
    GoalStatus,
    GoalLevel,
    Goal,
    GoalScheduler,
)

# ─── 三期模块 ───
from .causal_collision_scheduler import (
    CollisionRecord,
    CausalCollisionScheduler,
)
from .consistency_checker import (
    CheckLevel,
    ConsistencyIssue,
    ConsistencyChecker,
)
from .world_rule_guard import (
    GuardLevel,
    WorldRule,
    GuardViolation,
    WorldRuleGuard,
)

# ─── 四期模块 ───
from .timeline_branch import (
    BranchNode,
    WorldSnapshot,
    TimelineBranch,
)

__all__ = [
    # world_timeline
    "WorldTick",
    "WorldTimeline",
    # swimlane_manager
    "LifecycleStage",
    "ActionRecord",
    "CharacterSwimlane",
    "SwimlaneManager",
    # goal_scheduler
    "GoalStatus",
    "GoalLevel",
    "Goal",
    "GoalScheduler",
    # causal_collision_scheduler
    "CollisionRecord",
    "CausalCollisionScheduler",
    # consistency_checker
    "CheckLevel",
    "ConsistencyIssue",
    "ConsistencyChecker",
    # world_rule_guard
    "GuardLevel",
    "WorldRule",
    "GuardViolation",
    "WorldRuleGuard",
    # timeline_branch
    "BranchNode",
    "WorldSnapshot",
    "TimelineBranch",
]
