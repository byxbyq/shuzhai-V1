# -*- coding: utf-8 -*-
"""
白城主 Flow Engine — 异步执行器

按拓扑排序的批次顺序执行节点：
- 同批内节点无依赖 → asyncio.gather 并行
- 上游输出 → 下游输入（按 Edge 定义传递）
- 任意节点失败 → 跳过其下游（fail-fast + 级联跳过）
- 执行完成返回每个节点的状态/输出/耗时
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.flow_engine.node import NodeBase, NodeStatus
from backend.flow_engine.graph import FlowGraph, FlowGraphError

logger = logging.getLogger(__name__)


@dataclass
class NodeResult:
    """单个节点执行结果"""
    instance_id: str
    node_id: str
    node_name: str
    status: NodeStatus
    outputs: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class ExecutionResult:
    """一次完整执行的结果"""
    graph_id: str
    results: List[NodeResult]
    total_duration_ms: float = 0.0
    success: bool = False

    @property
    def failed_nodes(self) -> List[NodeResult]:
        return [r for r in self.results if r.status == NodeStatus.FAILED]

    @property
    def completed_nodes(self) -> List[NodeResult]:
        return [r for r in self.results if r.status == NodeStatus.COMPLETED]


class FlowExecutor:
    """
    流程图执行引擎。

    用法::

        graph = FlowGraph()
        graph.add_node(node_a)
        graph.add_node(node_b)
        graph.connect("node_a_id", "out", "node_b_id", "in")
        executor = FlowExecutor(graph)
        result = await executor.run()
    """

    def __init__(
        self,
        graph: FlowGraph,
        *,
        timeout_per_node: float = 300.0,
        fail_fast: bool = True,
    ):
        """
        Args:
            graph: 要执行的流程图
            timeout_per_node: 单节点超时（秒）
            fail_fast: True → 任意节点失败则跳过未执行的下游；False → 尽量执行所有节点
        """
        self.graph = graph
        self.timeout_per_node = timeout_per_node
        self.fail_fast = fail_fast
        self._failed_nodes: set = set()

    async def run(self) -> ExecutionResult:
        """执行整个流程图"""
        errors = self.graph.validate()
        if errors:
            raise FlowGraphError("流程图校验未通过:\n  " + "\n  ".join(f"- {e}" for e in errors))

        import time
        t_start = time.time()

        batches = self.graph.topological_batches()
        results: List[NodeResult] = []
        self._failed_nodes.clear()

        logger.info(
            "[executor] 开始执行图 %s，共 %d 个节点 %d 批次",
            self.graph.graph_id,
            len(self.graph.nodes),
            len(batches),
        )

        for batch_idx, batch in enumerate(batches):
            logger.debug("[executor] 批次 %d/%d: %s", batch_idx + 1, len(batches), batch)

            # 在每批开始前，将上游已完成节点的输出注入下游的输入
            self._propagate_data(batch)

            # 并行执行同批节点
            tasks = []
            for nid in batch:
                node = self.graph.get_node(nid)
                if node is None:
                    continue
                tasks.append(self._run_node(node))

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, item in enumerate(batch_results):
                if isinstance(item, NodeResult):
                    results.append(item)
                elif isinstance(item, Exception):
                    # gather 中的异常
                    node_id = batch[i]
                    node = self.graph.get_node(node_id)
                    results.append(NodeResult(
                        instance_id=node_id,
                        node_id=getattr(node, "node_id", ""),
                        node_name=getattr(node, "node_name", ""),
                        status=NodeStatus.FAILED,
                        error=str(item),
                    ))
                    self._failed_nodes.add(node_id)
                    if self.fail_fast:
                        # 找到该批次出错的节点，把该批次剩余也不会执行了
                        # 后续批次的节点标记为 skipped
                        pass

            # fail-fast：如果有节点失败，后续批次全部跳过
            if self.fail_fast and self._failed_nodes:
                remaining = []
                for future_batch in batches[batch_idx + 1:]:
                    remaining.extend(future_batch)
                for nid in remaining:
                    node = self.graph.get_node(nid)
                    if node:
                        node.status = NodeStatus.SKIPPED
                        results.append(NodeResult(
                            instance_id=nid,
                            node_id=node.node_id,
                            node_name=node.node_name,
                            status=NodeStatus.SKIPPED,
                            error="上游节点执行失败，已跳过",
                        ))

                logger.warning(
                    "[executor] 图 %s 因节点失败终止，已跳过 %d 个下游节点",
                    self.graph.graph_id, len(remaining),
                )
                break

        t_end = time.time()
        total_duration = (t_end - t_start) * 1000

        all_success = all(r.status == NodeStatus.COMPLETED for r in results)

        logger.info(
            "[executor] 图 %s 执行完成，%d/%d 成功，耗时 %.1fms",
            self.graph.graph_id,
            sum(1 for r in results if r.status == NodeStatus.COMPLETED),
            len(results),
            total_duration,
        )

        return ExecutionResult(
            graph_id=self.graph.graph_id,
            results=results,
            total_duration_ms=total_duration,
            success=all_success,
        )

    async def _run_node(self, node: NodeBase) -> NodeResult:
        """执行单个节点并返回结果"""
        import time
        t0 = time.time()
        node.status = NodeStatus.RUNNING
        log_prefix = f"[{node.node_name}:{node.instance_id[:8]}]"
        logger.debug("%s 开始执行", log_prefix)

        try:
            # 超时保护
            await asyncio.wait_for(node.execute(), timeout=self.timeout_per_node)
            # 节点内部（如 MiniPipelineNode 沙箱阻断）可能已自标记失败，勿覆盖
            if node.status != NodeStatus.FAILED:
                node.status = NodeStatus.COMPLETED
            duration = (time.time() - t0) * 1000
            err_text = node.error or node.outputs.get("error")
            if node.status == NodeStatus.FAILED:
                logger.error("%s 执行失败: %s", log_prefix, err_text)
                self._failed_nodes.add(node.instance_id)
            else:
                logger.info("%s 执行成功 (%.1fms)", log_prefix, duration)
            return NodeResult(
                instance_id=node.instance_id,
                node_id=node.node_id,
                node_name=node.node_name,
                status=node.status,
                outputs=node.outputs.export(),
                error=err_text if node.status == NodeStatus.FAILED else None,
                duration_ms=duration,
            )
        except asyncio.TimeoutError:
            node.status = NodeStatus.FAILED
            node.error = f"执行超时 ({self.timeout_per_node}s)"
            duration = (time.time() - t0) * 1000
            logger.error("%s 执行超时", log_prefix)
            self._failed_nodes.add(node.instance_id)
            return NodeResult(
                instance_id=node.instance_id,
                node_id=node.node_id,
                node_name=node.node_name,
                status=NodeStatus.FAILED,
                error=node.error,
                duration_ms=duration,
            )
        except Exception as e:
            node.status = NodeStatus.FAILED
            node.error = str(e)
            duration = (time.time() - t0) * 1000
            logger.error("%s 执行失败: %s", log_prefix, e, exc_info=True)
            self._failed_nodes.add(node.instance_id)
            return NodeResult(
                instance_id=node.instance_id,
                node_id=node.node_id,
                node_name=node.node_name,
                status=NodeStatus.FAILED,
                error=str(e),
                duration_ms=duration,
            )

    def _propagate_data(self, batch: List[str]) -> None:
        """
        将已完成节点的输出数据，按 Edge 注入到目标节点的输入端口。
        仅在批次开始前调用一次。
        """
        for edge in self.graph.edges:
            if edge.to_node not in batch:
                continue
            src = self.graph.get_node(edge.from_node)
            dst = self.graph.get_node(edge.to_node)
            if src is None or dst is None:
                continue
            if src.status != NodeStatus.COMPLETED:
                continue
            value = src.outputs.get(edge.from_port)
            if value is not None:
                dst.inputs.set(edge.to_port, value)
                logger.debug(
                    "[data] %s.%s → %s.%s",
                    src.instance_id[:8], edge.from_port,
                    dst.instance_id[:8], edge.to_port,
                )
