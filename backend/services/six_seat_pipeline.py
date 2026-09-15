# -*- coding: utf-8 -*-
"""
P3-1 Agent 六席位流水线

固定 DAG：planner → writer → reviewer → reviser → factcheck → librarian

席位说明：
- planner   : 大纲席（复用 OutlineAgent）
- writer    : 正文席（复用 ChapterAgent）
- reviewer  : 校验席（复用 ValidateAgent）
- reviser   : 修订席（复用 RewriteLoop 有界改写循环）
- factcheck : 防幻觉席（复用 P3-2 HallucinationGuard）
- librarian : 台账席（复用 CommitmentTracker 承诺落账）

基于 FlowGraph/FlowExecutor 构建并同步执行，
对外提供 run_six_seats(chapter_index, project_dir)。
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from backend.flow_engine.node import NodeBase, PortType
from backend.flow_engine.graph import FlowGraph
from backend.flow_engine.executor import FlowExecutor

logger = logging.getLogger(__name__)

# 六席位顺序（与规格一致）
SIX_SEAT_ORDER = ["planner", "writer", "reviewer", "reviser", "factcheck", "librarian"]

SIX_SEAT_LABELS = {
    "planner": "大纲席",
    "writer": "正文席",
    "reviewer": "校验席",
    "reviser": "修订席",
    "factcheck": "防幻觉席",
    "librarian": "台账席",
}


# ═══════════════════════════════════════════
# 自定义席位节点（reviser / factcheck / librarian）
# ═══════════════════════════════════════════

class ReviserNode(NodeBase):
    """修订席：复用 RewriteLoop 对上游正文做有界改写"""

    node_id = "sixseat.reviser"
    node_name = "修订席"
    node_category = "六席位"
    node_description = "有界改写循环：生成→验证→修复"

    def setup(self):
        self.add_input("message", PortType.TEXT, "待修订正文", required=False, default="")
        self.add_input("chapter_index", PortType.NUMBER, "章节索引", required=False, default=0)
        self.add_output("reply", PortType.TEXT, "修订后正文")
        self.add_output("data", PortType.JSON, "修订详情")

    async def execute(self) -> None:
        content = self.inputs.get("message", "") or ""
        if not content.strip():
            self.outputs["reply"] = ""
            self.outputs["data"] = {"skipped": True, "reason": "上游正文为空"}
            return

        from backend.ai_client import AIClient
        from backend.services.rewrite_loop import RewriteLoop, ContextLayer

        ai = AIClient()
        loop = RewriteLoop()
        loop.inject_layer(ContextLayer.STATIC, "你是一位网络小说作者，请输出修订后的章节正文，只输出正文。")
        loop.inject_layer(ContextLayer.DRAFT, content)

        def generate_fn(prompt: str, temperature: float) -> str:
            return ai.generate(prompt, temperature=temperature, task_type="rewrite")

        def validate_fn(text: str) -> list:
            issues = []
            if len(text.strip()) < 200:
                issues.append({"type": "too_short", "description": "正文过短", "severity": "warn"})
            return issues

        result = loop.run(generate_fn, validate_fn)
        final_text = getattr(result, "content", "") or content
        self.outputs["reply"] = final_text
        self.outputs["data"] = {
            "rounds": getattr(result, "round_count", 0),
            "tokens": getattr(result, "total_tokens", 0),
            "fallback_to_draft": final_text == content,
        }


class FactcheckNode(NodeBase):
    """防幻觉席：复用 P3-2 HallucinationGuard"""

    node_id = "sixseat.factcheck"
    node_name = "防幻觉席"
    node_category = "六席位"
    node_description = "实体名近似 / 规范字段失配检查"

    def setup(self):
        self.add_input("message", PortType.TEXT, "待检查正文", required=False, default="")
        self.add_input("chapter_index", PortType.NUMBER, "章节索引", required=False, default=0)
        self.add_output("reply", PortType.TEXT, "检查报告文本")
        self.add_output("data", PortType.JSON, "检查详情")

    def __init__(self, project_dir: str = "", instance_id: Optional[str] = None):
        self._project_dir = project_dir
        super().__init__(instance_id=instance_id)

    async def execute(self) -> None:
        content = self.inputs.get("message", "") or ""
        chapter_index = self.inputs.get("chapter_index", 0) or 0

        ledger = None
        world = None
        if self._project_dir:
            try:
                from backend.ledger import TruthLedger
                from backend.world_settings import WorldSettings
                ledger = TruthLedger(self._project_dir)
                world = WorldSettings(self._project_dir)
            except Exception as e:
                logger.warning("[sixseat.factcheck] 加载账本/世界观失败: %s", e)

        from backend.services.hallucination_guard import get_default_guard
        report = get_default_guard().check(
            content, ledger=ledger, world=world, chapter_index=chapter_index
        )
        issues = report.get("new_issues", []) if isinstance(report, dict) else []
        self.outputs["reply"] = f"防幻觉检查: 发现 {len(issues)} 处疑似问题"
        self.outputs["data"] = {"issues": issues, "passed": len(issues) == 0}


class LibrarianNode(NodeBase):
    """台账席：复用 CommitmentTracker 对正文中的叙事承诺落账"""

    node_id = "sixseat.librarian"
    node_name = "台账席"
    node_category = "六席位"
    node_description = "提取叙事承诺并登记到承诺台账"

    def setup(self):
        self.add_input("message", PortType.TEXT, "正文", required=False, default="")
        self.add_input("chapter_index", PortType.NUMBER, "章节索引", required=False, default=0)
        self.add_output("reply", PortType.TEXT, "落账摘要")
        self.add_output("data", PortType.JSON, "承诺列表")

    async def execute(self) -> None:
        content = self.inputs.get("message", "") or ""
        chapter_index = self.inputs.get("chapter_index", 0) or 0

        from backend.services.commitment_tracker import CommitmentTracker, scan_commitments

        tracker = CommitmentTracker()
        commitments = scan_commitments(content, chapter_index) if content else []
        registered = tracker.register_batch(commitments, chapter_index) if commitments else 0

        self.outputs["reply"] = f"承诺台账: 本章登记 {registered} 条叙事承诺"
        self.outputs["data"] = {"registered": registered, "commitments": tracker.to_list()}


# ═══════════════════════════════════════════
# 流水线构建与执行
# ═══════════════════════════════════════════

def build_six_seat_graph(chapter_index: int = 0, project_dir: str = "") -> Dict[str, Any]:
    """
    构建六席位固定 DAG。

    Returns:
        {"graph": FlowGraph, "instances": {seat: instance_id}}
    """
    from backend.flow_engine.nodes.adapter import wrap_agent
    from backend.agents.example_agents import OutlineAgent, ChapterAgent, ValidateAgent

    g = FlowGraph(graph_id="six_seats")

    planner = wrap_agent(OutlineAgent(), instance_id="seat_planner")
    planner.inputs.set("message", f"生成第{chapter_index + 1}章大纲")
    planner.inputs.set("chapter_index", chapter_index)

    writer = wrap_agent(ChapterAgent(), instance_id="seat_writer")
    writer.inputs.set("chapter_index", chapter_index)

    reviewer = wrap_agent(ValidateAgent(), instance_id="seat_reviewer")
    reviewer.inputs.set("chapter_index", chapter_index)

    reviser = ReviserNode(instance_id="seat_reviser")
    reviser.inputs.set("chapter_index", chapter_index)

    factcheck = FactcheckNode(project_dir=project_dir, instance_id="seat_factcheck")
    factcheck.inputs.set("chapter_index", chapter_index)

    librarian = LibrarianNode(instance_id="seat_librarian")
    librarian.inputs.set("chapter_index", chapter_index)

    for node in (planner, writer, reviewer, reviser, factcheck, librarian):
        g.add_node(node)

    # 链式传递：上一席 reply → 下一席 message
    chain = ["seat_planner", "seat_writer", "seat_reviewer", "seat_reviser", "seat_factcheck", "seat_librarian"]
    for up, down in zip(chain, chain[1:]):
        g.connect(up, "reply", down, "message")

    instances = dict(zip(SIX_SEAT_ORDER, chain))
    return {"graph": g, "instances": instances}


def run_six_seats(chapter_index: int = 0, project_dir: str = "") -> Dict[str, Any]:
    """
    同步执行六席位流水线并汇总结果。

    Args:
        chapter_index: 章节索引（0 基）
        project_dir: 项目目录（factcheck 席需要，可选）

    Returns:
        {"success": bool, "seats": [{seat, label, status, reply, data, duration_ms, error}],
         "total_duration_ms": float}
    """
    built = build_six_seat_graph(chapter_index, project_dir)
    graph, instances = built["graph"], built["instances"]

    executor = FlowExecutor(graph, timeout_per_node=600.0)
    result = asyncio.run(executor.run())

    by_instance = {r.instance_id: r for r in result.results}
    seats = []
    for seat in SIX_SEAT_ORDER:
        iid = instances[seat]
        r = by_instance.get(iid)
        if r is None:
            seats.append({"seat": seat, "label": SIX_SEAT_LABELS[seat],
                          "status": "skipped", "reply": "", "data": {}, "error": "未执行"})
            continue
        seats.append({
            "seat": seat,
            "label": SIX_SEAT_LABELS[seat],
            "status": r.status.value,
            "reply": r.outputs.get("reply", ""),
            "data": r.outputs.get("data", {}),
            "duration_ms": round(r.duration_ms, 1),
            "error": r.error,
        })

    return {
        "success": result.success,
        "seats": seats,
        "total_duration_ms": round(result.total_duration_ms, 1),
    }
