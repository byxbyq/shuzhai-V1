# -*- coding: utf-8 -*-
"""小说引擎 API 路由

提供碰撞检测、关系图可视化、图编辑等 REST 接口。
路由前缀: /api/engine

V2 扩展（四期融合）：
  - /api/engine/v2/status     - 完整引擎状态
  - /api/engine/v2/tick       - tick 推进
  - /api/engine/v2/timeline   - 世界时间轴
  - /api/engine/v2/swimlanes  - 角色泳道
  - /api/engine/v2/goals      - 目标调度
  - /api/engine/v2/consistency - 一致性校验
  - /api/engine/v2/rules      - 世界观规则守卫
  - /api/engine/v2/branches   - 时序分支管理
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

from backend.api_models import err, ErrorCode


# ─── 请求/响应模型 ───

class AddEdgeRequest(BaseModel):
    """手动添加边的请求体"""
    src: str
    dst: str
    fb: float = 0.0
    ud: float = 0.0
    lr: float = 0.0
    sd: float = 0.0
    io: float = 0.0
    tm: float = 0.0
    weight: float = 1.0


class AddGoalRequest(BaseModel):
    """添加目标的请求体"""
    content: str
    level: str = "daily"        # daily / stage / ultimate
    character_name: str
    tick: int = 0


class CompleteGoalRequest(BaseModel):
    """完成目标的请求体"""
    goal_id: str
    tick: int


class CheckRulesRequest(BaseModel):
    """规则守卫校验请求体"""
    text: str
    characters: List[str] = []


class CreateBranchRequest(BaseModel):
    """创建分支的请求体"""
    parent_branch_id: str = "main"
    branch_point_tick: int = 0
    description: str = ""


class SwitchBranchRequest(BaseModel):
    """切换分支的请求体"""
    branch_id: str


class AdvanceTickRequest(BaseModel):
    """推进 tick 的请求体"""
    scene: str = ""
    time_marker: str = ""
    active_characters: List[str] = []


# ─── 路由器 ───

router = APIRouter(prefix="/api/engine", tags=["novel-engine"])

# 模块级引擎实例缓存（延迟初始化）
_engine_instance = None


def _get_engine():
    """延迟获取 NovelEngineCore 实例

    首次调用时才导入并初始化引擎，避免书斋启动时的循环依赖。
    """
    global _engine_instance
    if _engine_instance is None:
        from backend.novel_engine.engine_core import NovelEngineCore
        _engine_instance = NovelEngineCore()
    return _engine_instance


# ═══════════════════════════════════════════
#  V1 接口（保持兼容）
# ═══════════════════════════════════════════

@router.get("/status")
async def engine_status():
    """获取引擎状态

    Returns:
        {ok, engine, graph_nodes, graph_edges}
    """
    try:
        engine = _get_engine()
        graph = engine.six_axis_graph
        if graph is None:
            return {"ok": True, "engine": "loaded", "graph_nodes": 0, "graph_edges": 0}
        stats = graph.get_stats()
        return {
            "ok": True,
            "engine": "loaded",
            "graph_nodes": stats["node_count"],
            "graph_edges": stats["edge_count"],
        }
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"引擎错误: {str(e)}")


@router.post("/collide")
async def run_collision():
    """执行碰撞检测并生成灵感

    Returns:
        {ok, collisions, inspirations}
        每条 inspiration 包含 title, desc, impact, tags
    """
    try:
        engine = _get_engine()
        collisions = engine.run_collision_detection()
        inspirations = engine.collisions_to_inspirations(collisions)
        engine.save_state()
        return {
            "ok": True,
            "collisions": collisions,
            "inspirations": inspirations,
        }
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"引擎错误: {str(e)}")


@router.get("/graph")
async def get_graph():
    """获取六轴关系图 JSON（用于前端可视化）

    Returns:
        {nodes: [...], edges: [...]}
    """
    try:
        engine = _get_engine()
        graph = engine.six_axis_graph
        if graph is None:
            return {"nodes": [], "edges": []}

        nodes = [{"id": nid} for nid in graph.adj.keys()]
        edges = []
        for src, edge_list in graph.adj.items():
            for e in edge_list:
                edges.append(e.to_dict())

        return {"nodes": nodes, "edges": edges}
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}


@router.post("/graph/add-edge")
async def add_edge(req: AddEdgeRequest):
    """手动向关系图添加一条边"""
    try:
        engine = _get_engine()
        if engine.six_axis_graph is None:
            from backend.novel_engine.six_axis_graph import SixAxisGraph
            engine.six_axis_graph = SixAxisGraph()

        engine.six_axis_graph.add_edge(
            src=req.src, dst=req.dst,
            fb=req.fb, ud=req.ud, lr=req.lr,
            sd=req.sd, io=req.io, tm=req.tm,
            weight=req.weight,
        )
        engine.save_state()
        return {"ok": True, "message": f"已添加边: {req.src} -> {req.dst}"}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"引擎错误: {str(e)}")


@router.post("/reset")
async def reset_engine():
    """重置引擎状态并重新构建关系图"""
    global _engine_instance
    try:
        from backend.novel_engine.engine_core import NovelEngineCore
        _engine_instance = NovelEngineCore()
        characters = _engine_instance.get_characters_from_ledger()
        if characters:
            _engine_instance.six_axis_graph = _engine_instance.build_six_axis_graph_from_characters(characters)
        return {"ok": True, "message": "引擎已重置并重建"}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"引擎错误: {str(e)}")


# ═══════════════════════════════════════════
#  V2 接口（四期融合新增）
# ═══════════════════════════════════════════

@router.get("/v2/status")
async def v2_status():
    """获取完整引擎状态（V2）

    Returns:
        包含所有模块的统计信息
    """
    try:
        engine = _get_engine()
        tl_stats = engine.world_timeline.get_stats()
        sm_stats = engine.swimlane_manager.get_stats()
        gs_stats = engine.goal_scheduler.get_stats()
        cc_stats = engine.consistency_checker.get_stats()
        rg_stats = engine.rule_guard.get_stats()
        tb_stats = engine.timeline_branch.get_stats()

        graph_nodes = 0
        graph_edges = 0
        if engine.six_axis_graph is not None:
            gstats = engine.six_axis_graph.get_stats()
            graph_nodes = gstats["node_count"]
            graph_edges = gstats["edge_count"]

        return {
            "ok": True,
            "graph": {"nodes": graph_nodes, "edges": graph_edges},
            "timeline": tl_stats,
            "swimlanes": sm_stats,
            "goals": gs_stats,
            "consistency": cc_stats,
            "rules": rg_stats,
            "branches": tb_stats,
        }
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"引擎错误: {str(e)}")


# ─── 时间轴 ───

@router.get("/v2/timeline")
async def v2_timeline():
    """获取世界时间轴"""
    try:
        engine = _get_engine()
        tl = engine.world_timeline
        ticks = [t.to_dict() for t in tl.ticks]
        return {
            "ok": True,
            "ticks": ticks,
            "current_tick": tl.current_tick,
            "stats": tl.get_stats(),
        }
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"引擎错误: {str(e)}")


@router.post("/v2/tick/advance")
async def v2_advance_tick(req: AdvanceTickRequest):
    """推进一个 tick

    继承上一 tick 的角色和场景，可覆盖。
    """
    try:
        engine = _get_engine()
        engine.world_timeline.advance_tick()
        # 手动设置属性（advance_tick 只递增 tick）
        current = engine.world_timeline.get_current_tick()
        if current:
            if req.scene:
                current.scene = req.scene
            if req.time_marker:
                current.time_marker = req.time_marker
            if req.active_characters:
                current.active_characters = list(req.active_characters)
        engine.save_state()
        return {"ok": True, "tick": current.tick_id if current else 0}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"引擎错误: {str(e)}")


# ─── 角色泳道 ───

@router.get("/v2/swimlanes")
async def v2_swimlanes():
    """获取角色泳道列表"""
    try:
        engine = _get_engine()
        sm = engine.swimlane_manager
        swimlanes = []
        for name, sl in sm.swimlanes.items():
            swimlanes.append({
                "character_name": name,
                "lifecycle": sl.lifecycle.value,
                "entry_tick": sl.entry_tick,
                "exit_tick": sl.exit_tick,
                "action_count": len(sl.action_log),
                "daily_goals": sl.daily_goals,
                "state_snapshot": sl.state_snapshot,
            })
        return {
            "ok": True,
            "swimlanes": swimlanes,
            "stats": sm.get_stats(),
        }
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"引擎错误: {str(e)}")


# ─── 目标调度 ───

@router.get("/v2/goals")
async def v2_goals(character: str = None):
    """获取目标列表

    Args:
        character: 可选，按角色过滤
    """
    try:
        engine = _get_engine()
        gs = engine.goal_scheduler
        goals = []
        for gid, g in gs.goals.items():
            if character and g.character_name != character:
                continue
            goals.append({
                "id": g.id,
                "content": g.content,
                "level": g.level.value,
                "status": g.status.value,
                "character_name": g.character_name,
                "parent_goal_id": g.parent_goal_id,
                "child_goal_ids": g.child_goal_ids,
                "created_tick": g.created_tick,
                "completed_tick": g.completed_tick,
            })
        return {
            "ok": True,
            "goals": goals,
            "stats": gs.get_stats(),
        }
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"引擎错误: {str(e)}")


@router.post("/v2/goals/add")
async def v2_add_goal(req: AddGoalRequest):
    """添加一个目标"""
    try:
        from backend.novel_engine.scheduler import GoalLevel
        engine = _get_engine()
        level_map = {
            "daily": GoalLevel.DAILY,
            "stage": GoalLevel.STAGE,
            "ultimate": GoalLevel.ULTIMATE,
        }
        level = level_map.get(req.level, GoalLevel.DAILY)
        goal = engine.goal_scheduler.add_goal(
            content=req.content,
            level=level,
            character_name=req.character_name,
            tick=req.tick,
        )
        engine.save_state()
        return {"ok": True, "goal_id": goal.id, "goal": goal.to_dict() if hasattr(goal, 'to_dict') else str(goal)}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"引擎错误: {str(e)}")


@router.post("/v2/goals/complete")
async def v2_complete_goal(req: CompleteGoalRequest):
    """完成一个目标"""
    try:
        engine = _get_engine()
        new_goals = engine.goal_scheduler.complete_goal(req.goal_id, req.tick)
        engine.save_state()
        return {
            "ok": True,
            "new_goals_count": len(new_goals),
        }
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"引擎错误: {str(e)}")


# ─── 一致性校验 ───

@router.get("/v2/consistency")
async def v2_consistency():
    """执行全局一致性校验"""
    try:
        engine = _get_engine()
        issues = engine.consistency_checker.check_all()
        report = engine.consistency_checker.get_report()
        return {
            "ok": True,
            "issues": [i.to_dict() for i in issues],
            "report": report,
            "stats": engine.consistency_checker.get_stats(),
        }
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"引擎错误: {str(e)}")


# ─── 规则守卫 ───

@router.get("/v2/rules")
async def v2_rules():
    """获取世界观规则列表"""
    try:
        engine = _get_engine()
        rules = [r.to_dict() for r in engine.rule_guard.list_rules()]
        return {
            "ok": True,
            "rules": rules,
            "stats": engine.rule_guard.get_stats(),
        }
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"引擎错误: {str(e)}")


@router.post("/v2/rules/check")
async def v2_check_rules(req: CheckRulesRequest):
    """校验文本是否违反世界观规则"""
    try:
        engine = _get_engine()
        violations = engine.rule_guard.check_narrative(req.text, req.characters)
        should_block = engine.rule_guard.should_block(violations)
        return {
            "ok": True,
            "violations": [v.to_dict() for v in violations],
            "should_block": should_block,
            "report": engine.rule_guard.get_violation_report(violations),
        }
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"引擎错误: {str(e)}")


# ─── 时序分支 ───

@router.get("/v2/branches")
async def v2_branches():
    """获取分支树"""
    try:
        engine = _get_engine()
        tree = engine.timeline_branch.get_branch_tree()
        branches = [b.to_dict() for b in engine.timeline_branch.list_branches()]
        snapshots = [s.to_dict() for s in engine.timeline_branch.list_snapshots()]
        return {
            "ok": True,
            "tree": tree,
            "branches": branches,
            "snapshots": snapshots,
            "active_branch": engine.timeline_branch.active_branch_id,
        }
    except Exception as e:
        return {**err(ErrorCode.INTERNAL_ERROR, f"引擎错误: {str(e)}"), "tree": {}, "branches": []}


@router.post("/v2/branches/create")
async def v2_create_branch(req: CreateBranchRequest):
    """创建一个新分支"""
    try:
        engine = _get_engine()
        branch_id = engine.timeline_branch.create_branch(
            parent_branch_id=req.parent_branch_id,
            branch_point_tick=req.branch_point_tick,
            description=req.description,
        )
        engine.save_state()
        return {"ok": True, "branch_id": branch_id}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"引擎错误: {str(e)}")


@router.post("/v2/branches/switch")
async def v2_switch_branch(req: SwitchBranchRequest):
    """切换到指定分支"""
    try:
        engine = _get_engine()
        success = engine.timeline_branch.switch_branch(req.branch_id)
        engine.save_state()
        return {"ok": success, "active_branch": engine.timeline_branch.active_branch_id}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"引擎错误: {str(e)}")
