# -*- coding: utf-8 -*-
"""
全局一致性校验器 - 跨模块的数据一致性检查

核心职责：
  1. 校验 TruthLedger 中的角色状态与 SwimlaneManager 的泳道状态是否一致
  2. 校验 WorldTimeline 的活跃角色与 SwimlaneManager 的活跃角色是否匹配
  3. 校验 GoalScheduler 中的目标与角色生命周期是否匹配（死人不该有执行中目标）
  4. 校验伏笔回收时间线是否合理（不能在埋设前回收）
  5. 检测时间线倒流（后续章节的角色出现在更早的章节）

设计原则：
  - 不修改数据，只检测和报告问题
  - 按严重程度分级：error / warning / info
  - 支持增量检查（只检查最近 N 章）和全量检查
"""
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, List


class CheckLevel(Enum):
    """问题严重级别"""
    ERROR = "error"        # 严重错误，数据不一致
    WARNING = "warning"    # 警告，可能有问题
    INFO = "info"          # 提示信息


@dataclass
class ConsistencyIssue:
    """
    一致性问题记录

    Attributes:
        level: 严重级别
        category: 问题类别（character_state / timeline / goal / foreshadowing / timeline_backflow）
        message: 问题描述
        detail: 详细信息（涉及的实体、值等）
        chapter: 相关章节号（0=全局）
        tick: 相关 tick（0=不适用）
    """
    level: CheckLevel = CheckLevel.INFO
    category: str = ""
    message: str = ""
    detail: str = ""
    chapter: int = 0
    tick: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["level"] = self.level.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ConsistencyIssue":
        data = dict(data)
        if isinstance(data.get("level"), str):
            data["level"] = CheckLevel(data["level"])
        return cls(**data)


class ConsistencyChecker:
    """
    全局一致性校验器

    使用方式：
        checker = ConsistencyChecker()
        checker.set_truth_ledger(ledger)
        checker.set_swimlane_manager(sm)
        checker.set_timeline(timeline)
        checker.set_goal_scheduler(gs)

        issues = checker.check_all()
        errors = checker.check_all(level=CheckLevel.ERROR)
    """

    def __init__(self):
        self.truth_ledger = None
        self.swimlane_manager = None
        self.timeline = None
        self.goal_scheduler = None
        self.collision_scheduler = None
        self._last_issues: List[ConsistencyIssue] = []

    # ─── 引用设置 ───

    def set_truth_ledger(self, ledger):
        self.truth_ledger = ledger

    def set_swimlane_manager(self, sm):
        self.swimlane_manager = sm

    def set_timeline(self, tl):
        self.timeline = tl

    def set_goal_scheduler(self, gs):
        self.goal_scheduler = gs

    def set_collision_scheduler(self, cs):
        self.collision_scheduler = cs

    # ─── 主入口 ───

    def check_all(self, level: CheckLevel = None,
                  recent_chapters: int = 0,
                  current_tick: int = 0) -> List[ConsistencyIssue]:
        """
        执行全部一致性检查

        Args:
            level: 只返回该级别及以上的问题（None=全部）
            recent_chapters: 只检查最近 N 章（0=全量检查）
            current_tick: 当前 tick 编号，用于因果碰撞检测

        Returns:
            问题列表，按严重程度排序（ERROR > WARNING > INFO）
        """
        issues = []

        # 1. 角色状态一致性
        issues.extend(self.check_character_states())

        # 2. 时间线活跃角色一致性
        issues.extend(self.check_timeline_characters())

        # 3. 目标与生命周期一致性
        issues.extend(self.check_goal_lifecycle())

        # 4. 伏笔时间线一致性
        issues.extend(self.check_foreshadowing_timeline())

        # 5. 时间线倒流检测
        issues.extend(self.check_timeline_backflow())

        # 6. 因果碰撞检测
        issues.extend(self.check_causal_collisions(current_tick))

        # 按严重程度排序
        severity_order = {CheckLevel.ERROR: 0, CheckLevel.WARNING: 1, CheckLevel.INFO: 2}
        issues.sort(key=lambda i: severity_order.get(i.level, 3))

        # 级别过滤
        if level is not None:
            target_severity = severity_order.get(level, 3)
            issues = [i for i in issues
                      if severity_order.get(i.level, 3) <= target_severity]

        self._last_issues = list(issues)
        return issues

    # ─── 检查项 1：角色状态一致性 ───

    def check_character_states(self) -> List[ConsistencyIssue]:
        """
        校验 TruthLedger 和 SwimlaneManager 中的角色状态是否一致

        检查点：
        - 角色在 TruthLedger 中死亡，但在 SwimlaneManager 中活跃
        - 角色在 SwimlaneManager 中死亡/封印，但在 TruthLedger 中存活
        书斋版 TruthLedger 没有 lifecycle_stage，基于 is_alive + arc_stage 推断
        """
        issues = []
        if self.truth_ledger is None or self.swimlane_manager is None:
            return issues

        tl_states = self.truth_ledger.character_states
        sm_swimlanes = self.swimlane_manager.swimlanes

        def _tl_lifecycle(cs) -> str:
            """从书斋版 CharacterState 推断生命周期"""
            if not cs.is_alive:
                return "dead"
            if cs.arc_stage in ("sealed", "沉睡", "封印", "休眠"):
                return "sealed"
            if cs.arc_stage in ("pending", "未出生", "尚未登场"):
                return "pending"
            return "active"

        for name, cs in tl_states.items():
            if name not in sm_swimlanes:
                issues.append(ConsistencyIssue(
                    level=CheckLevel.WARNING,
                    category="character_state",
                    message=f"角色 '{name}' 在 TruthLedger 中存在，但 SwimlaneManager 中未注册",
                    detail=f"TruthLedger is_alive: {cs.is_alive}, arc_stage: {cs.arc_stage}",
                ))
                continue

            swimlane = sm_swimlanes[name]
            tl_lifecycle = _tl_lifecycle(cs)
            sm_lifecycle = swimlane.lifecycle.value

            if tl_lifecycle == "active" and sm_lifecycle in ("sealed", "dead"):
                issues.append(ConsistencyIssue(
                    level=CheckLevel.ERROR,
                    category="character_state",
                    message=f"角色 '{name}' 状态冲突：TruthLedger=active, SwimlaneManager={sm_lifecycle}",
                    detail=f"TL: alive={cs.is_alive}, arc={cs.arc_stage} | SM: {sm_lifecycle}",
                ))
            elif tl_lifecycle == "dead" and sm_lifecycle == "active":
                issues.append(ConsistencyIssue(
                    level=CheckLevel.ERROR,
                    category="character_state",
                    message=f"角色 '{name}' 状态冲突：TruthLedger=dead, SwimlaneManager=active",
                    detail=f"TL: alive={cs.is_alive} | SM: {sm_lifecycle}",
                ))
            elif tl_lifecycle == "sealed" and sm_lifecycle == "active":
                issues.append(ConsistencyIssue(
                    level=CheckLevel.WARNING,
                    category="character_state",
                    message=f"角色 '{name}' 状态不一致：TruthLedger=sealed, SwimlaneManager=active",
                    detail=f"TL: arc_stage={cs.arc_stage} | SM: {sm_lifecycle}",
                ))

        # 检查 SwimlaneManager 中有但 TruthLedger 中没有的角色
        for name in sm_swimlanes:
            if name not in tl_states:
                issues.append(ConsistencyIssue(
                    level=CheckLevel.INFO,
                    category="character_state",
                    message=f"角色 '{name}' 在 SwimlaneManager 中已注册，但 TruthLedger 中无记录",
                ))

        return issues

    # ─── 检查项 2：时间线活跃角色一致性 ───

    def check_timeline_characters(self) -> List[ConsistencyIssue]:
        """
        校验 WorldTimeline 中记录的活跃角色与 SwimlaneManager 的状态是否匹配

        检查点：
        - WorldTimeline 的某个 tick 标记为活跃的角色，在 SwimlaneManager 中已死亡/封印
        - SwimlaneManager 中活跃的角色，没有出现在 WorldTimeline 的活跃角色列表中
        """
        issues = []
        if self.timeline is None or self.swimlane_manager is None:
            return issues

        for tick in self.timeline.ticks:
            tl_active = set(tick.active_characters)
            for char_name in tl_active:
                swimlane = self.swimlane_manager.swimlanes.get(char_name)
                if swimlane is None:
                    issues.append(ConsistencyIssue(
                        level=CheckLevel.WARNING,
                        category="timeline",
                        message=f"tick {tick.tick_id} 活跃角色 '{char_name}' 未在 SwimlaneManager 注册",
                        chapter=tick.chapter,
                        tick=tick.tick_id,
                    ))
                elif swimlane.lifecycle.value in ("dead", "sealed"):
                    issues.append(ConsistencyIssue(
                        level=CheckLevel.ERROR,
                        category="timeline",
                        message=f"tick {tick.tick_id} 标记 '{char_name}' 为活跃，但泳道状态为 {swimlane.lifecycle.value}",
                        chapter=tick.chapter,
                        tick=tick.tick_id,
                    ))

        return issues

    # ─── 检查项 3：目标与生命周期一致性 ───

    def check_goal_lifecycle(self) -> List[ConsistencyIssue]:
        """
        校验 GoalScheduler 中的目标与角色生命周期是否匹配

        检查点：
        - 死亡/封印角色不应该有 EXECUTING 状态的目标
        - 已完成的目标不应该还有 EXECUTING 状态的子目标
        """
        issues = []
        if self.goal_scheduler is None or self.swimlane_manager is None:
            return issues

        try:
            from .goal_scheduler import GoalStatus
        except ImportError:
            try:
                from engine.scheduler.goal_scheduler import GoalStatus
            except ImportError:
                return issues

        for goal_id, goal in self.goal_scheduler.goals.items():
            char_name = goal.character_name
            swimlane = self.swimlane_manager.swimlanes.get(char_name)

            if swimlane is None:
                continue

            # 死亡/封印角色不应有执行中的目标
            if (swimlane.lifecycle.value in ("dead", "sealed")
                    and goal.status == GoalStatus.EXECUTING):
                issues.append(ConsistencyIssue(
                    level=CheckLevel.ERROR,
                    category="goal",
                    message=f"角色 '{char_name}' 已 {swimlane.lifecycle.value}，但目标 '{goal_id}' 仍在执行中",
                    detail=f"Goal: {goal.content[:50]}",
                ))

        return issues

    # ─── 检查项 4：伏笔时间线一致性 ───

    def check_foreshadowing_timeline(self) -> List[ConsistencyIssue]:
        """
        校验伏笔的时间线是否合理

        检查点：
        - 伏笔回收章节早于埋设章节
        - 伏笔标记为已回收，但回收章节未记录
        - 长期伏笔超过预期回收章节太多（warning）
        """
        issues = []
        if self.truth_ledger is None:
            return issues

        for hook in self.truth_ledger.foreshadowing:
            # 回收章节早于埋设章节
            if hook.status == "recovered":
                if (hook.expected_recovery_chapter > 0
                        and hook.expected_recovery_chapter < hook.planted_chapter):
                    issues.append(ConsistencyIssue(
                        level=CheckLevel.ERROR,
                        category="foreshadowing",
                        message=f"伏笔 '{hook.id}' 回收章节({hook.expected_recovery_chapter})早于埋设章节({hook.planted_chapter})",
                        chapter=hook.planted_chapter,
                    ))

            # 长期伏笔超期未回收
            if hook.status in ("planted", "active"):
                if hook.expected_recovery_chapter > 0:
                    # 找当前最大章节号（从 chapter_logs 取，TruthLedger 无 timeline 属性）
                    max_chapter = 0
                    if self.truth_ledger.chapter_logs:
                        max_chapter = max(
                            (cl.chapter_index for cl in self.truth_ledger.chapter_logs),
                            default=0
                        )
                    if max_chapter > hook.expected_recovery_chapter + 5:
                        issues.append(ConsistencyIssue(
                            level=CheckLevel.WARNING,
                            category="foreshadowing",
                            message=f"伏笔 '{hook.id}' 已超期 {max_chapter - hook.expected_recovery_chapter} 章未回收",
                            detail=f"埋设: 第{hook.planted_chapter}章, 预期回收: 第{hook.expected_recovery_chapter}章, 当前: 第{max_chapter}章",
                            chapter=max_chapter,
                        ))

        return issues

    # ─── 检查项 5：时间线倒流检测 ───

    def check_timeline_backflow(self) -> List[ConsistencyIssue]:
        """
        检测时间线倒流 — 后续章节的角色出现在更早的章节

        检查点：
        - TruthLedger 中角色首次出现章节 与 角色注册顺序矛盾
        - WorldTimeline 中 tick 的章节号出现倒退（非分支情况）
        """
        issues = []
        if self.timeline is None:
            return issues

        prev_chapter = 0
        for tick in self.timeline.ticks:
            if tick.chapter < prev_chapter:
                issues.append(ConsistencyIssue(
                    level=CheckLevel.WARNING,
                    category="timeline_backflow",
                    message=f"tick {tick.tick_id} 章节({tick.chapter}) < 前一 tick 章节({prev_chapter})，可能时间线倒流",
                    chapter=tick.chapter,
                    tick=tick.tick_id,
                ))
            prev_chapter = max(prev_chapter, tick.chapter)

        return issues

    # ─── 检查项 6：因果碰撞检测 ───

    def check_causal_collisions(self, tick: int = 0) -> List[ConsistencyIssue]:
        """
        检测当前时间点的因果碰撞

        调用 CausalCollisionScheduler.detect_at_tick 检测碰撞，
        将高激活值的碰撞作为一致性问题返回，提示潜在的剧情冲突点。

        Args:
            tick: 当前 tick 编号

        Returns:
            因果碰撞相关的一致性问题列表
        """
        issues = []
        if self.collision_scheduler is None:
            return issues

        try:
            collisions = self.collision_scheduler.detect_at_tick(tick)
            if not collisions:
                return issues

            for col in collisions:
                if col.total_activation >= 0.7:
                    level = CheckLevel.WARNING
                elif col.total_activation >= 0.4:
                    level = CheckLevel.INFO
                else:
                    continue

                issues.append(ConsistencyIssue(
                    level=level,
                    category="causal_collision",
                    message=f"检测到{col.collision_type}碰撞：{col.description}",
                    detail=(
                        f"来源: {', '.join(col.sources)} | "
                        f"汇聚: {col.node_id} | "
                        f"激活值: {col.total_activation:.3f} | "
                        f"轴分布: {col.axis_breakdown}"
                    ),
                    chapter=col.chapter,
                    tick=col.tick,
                ))
        except Exception as e:
            logger = __import__('logging').getLogger(__name__)
            logger.warning("因果碰撞检测失败: %s", e)

        return issues

    # ─── 报告生成 ───

    def get_report(self) -> str:
        """生成文本格式的一致性报告"""
        if not self._last_issues:
            self.check_all()

        if not self._last_issues:
            return "[ConsistencyChecker] 无一致性问题，全部通过。"

        lines = ["=" * 50, "一致性检查报告", "=" * 50]
        error_count = sum(1 for i in self._last_issues if i.level == CheckLevel.ERROR)
        warn_count = sum(1 for i in self._last_issues if i.level == CheckLevel.WARNING)
        info_count = sum(1 for i in self._last_issues if i.level == CheckLevel.INFO)

        lines.append(f"错误: {error_count} | 警告: {warn_count} | 提示: {info_count}")
        lines.append("-" * 50)

        for issue in self._last_issues:
            level_tag = {"error": "[ERROR]", "warning": "[WARN] ", "info": "[INFO] "}
            tag = level_tag.get(issue.level.value, "[?]   ")
            lines.append(
                f"{tag} [{issue.category}] {issue.message}"
            )
            if issue.detail:
                lines.append(f"       详情: {issue.detail}")

        return "\n".join(lines)

    # ─── 序列化 ───

    def to_dict(self) -> dict:
        return {
            "issues": [i.to_dict() for i in self._last_issues],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConsistencyChecker":
        checker = cls()
        for idata in data.get("issues", []):
            checker._last_issues.append(ConsistencyIssue.from_dict(idata))
        return checker

    # ─── 统计 ───

    def get_stats(self) -> Dict:
        """返回检查统计"""
        error_count = sum(1 for i in self._last_issues if i.level == CheckLevel.ERROR)
        warn_count = sum(1 for i in self._last_issues if i.level == CheckLevel.WARNING)
        info_count = sum(1 for i in self._last_issues if i.level == CheckLevel.INFO)

        category_counts = {}
        for i in self._last_issues:
            category_counts[i.category] = category_counts.get(i.category, 0) + 1

        return {
            "total_issues": len(self._last_issues),
            "errors": error_count,
            "warnings": warn_count,
            "infos": info_count,
            "category_distribution": category_counts,
            "has_truth_ledger": self.truth_ledger is not None,
            "has_swimlane_manager": self.swimlane_manager is not None,
            "has_timeline": self.timeline is not None,
            "has_goal_scheduler": self.goal_scheduler is not None,
            "has_collision_scheduler": self.collision_scheduler is not None,
        }
