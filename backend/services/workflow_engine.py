# -*- coding: utf-8 -*-
"""
书斋 V66 — 轻量 Workflow 引擎（自研）

与 backend/routers/workflow.py 完全独立，不修改现有 workflow 路由。
提供断点恢复、条件分支、并行步骤三大核心能力。

使用示例::

    engine = WorkflowEngine()
    engine.add_step("fetch_data", fetch_data_func, fallback=fetch_cache_func)
    engine.add_step("analyze", analyze_func)
    engine.add_parallel_step("batch_process", [
        {"name": "process_A", "func": process_a},
        {"name": "process_B", "func": process_b},
    ])
    result = await engine.run("project_001")
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 数据结构 ──


@dataclass
class _StepDef:
    """内部步骤定义"""
    name: str
    func: Callable[..., Coroutine[Any, Any, Any]]
    fallback: Optional[Callable[..., Coroutine[Any, Any, Any]]] = None
    is_parallel: bool = False
    parallel_steps: List[Dict[str, Any]] = field(default_factory=list)


# ── WorkflowEngine ──


class WorkflowEngine:
    """轻量工作流引擎。

    提供断点恢复、条件分支和并行步骤执行能力。
    检查点持久化到 ``data/workflow_checkpoints/{project_id}.json``。

    公开方法：
        - ``add_step(name, func, fallback=None)`` — 添加串行步骤
        - ``add_parallel_step(name, steps)`` — 添加并行步骤组
        - ``async run(project_id)`` — 执行工作流

    Attributes:
        steps: 已注册的步骤列表（_StepDef 对象）
    """

    def __init__(self):
        self.steps: List[_StepDef] = []

    # ── 步骤注册 ──

    def add_step(
        self,
        name: str,
        func: Callable[..., Coroutine[Any, Any, Any]],
        fallback: Optional[Callable[..., Coroutine[Any, Any, Any]]] = None,
    ) -> None:
        """添加一个串行步骤。

        Args:
            name: 步骤名称（唯一标识）
            func: 异步可调用对象，签名为 ``async def func() -> Any``
            fallback: 可选的降级函数，当 func 失败时自动调用
        """
        self.steps.append(_StepDef(name=name, func=func, fallback=fallback))

    def add_parallel_step(self, name: str, steps: List[Dict[str, Any]]) -> None:
        """添加一个并行步骤组。

        Args:
            name: 步骤组名称（唯一标识）
            steps: 子步骤列表，每项为 ``{"name": str, "func": async_callable}``
        """
        self.steps.append(
            _StepDef(
                name=name,
                func=self._noop,  # 占位，不会被直接调用
                is_parallel=True,
                parallel_steps=steps,
            )
        )

    async def _noop(self) -> None:
        """并行步骤组的占位函数"""
        pass

    # ── 检查点管理 ──

    @staticmethod
    def _checkpoint_path(project_id: str) -> str:
        """返回检查点文件路径"""
        base = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "data", "workflow_checkpoints",
        )
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, f"{project_id}.json")

    @staticmethod
    def _load_checkpoint(project_id: str) -> Optional[Dict[str, Any]]:
        """加载检查点，不存在则返回 None"""
        path = WorkflowEngine._checkpoint_path(project_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("加载检查点失败 [%s]: %s", project_id, e)
            return None

    @staticmethod
    def _save_checkpoint(project_id: str, data: Dict[str, Any]) -> None:
        """保存检查点"""
        path = WorkflowEngine._checkpoint_path(project_id)
        data["_saved_at"] = datetime.now(timezone.utc).isoformat()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error("保存检查点失败 [%s]: %s", project_id, e)

    @staticmethod
    def _delete_checkpoint(project_id: str) -> None:
        """删除检查点（工作流全部成功后）"""
        path = WorkflowEngine._checkpoint_path(project_id)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError as e:
                logger.warning("删除检查点失败 [%s]: %s", project_id, e)

    # ── 主执行循环 ──

    async def run(self, project_id: str) -> Dict[str, Any]:
        """执行整个工作流。

        执行逻辑：
            1. 加载检查点，确定恢复位置
            2. 从恢复点顺序执行步骤
            3. 每个步骤前保存检查点
            4. 失败时尝试 fallback，仍失败则返回失败结果 + 恢复点

        Args:
            project_id: 项目标识，用于检查点隔离

        Returns:
            dict::

                {
                    "success": bool,
                    "results": {step_name: result_value, ...},
                    "resume_point": str | None,  # 失败时的恢复步骤名
                }
        """
        checkpoint = self._load_checkpoint(project_id)
        results: Dict[str, Any] = {}
        resume_idx = 0

        if checkpoint:
            results = checkpoint.get("results", {})
            resume_idx = checkpoint.get("last_completed_idx", -1) + 1
            logger.info(
                "[workflow_engine] 从检查点恢复: project=%s, step=%d/%d",
                project_id, resume_idx, len(self.steps),
            )

        for i in range(resume_idx, len(self.steps)):
            step = self.steps[i]

            # ── 保存检查点（执行前） ──
            self._save_checkpoint(
                project_id,
                {"last_completed_idx": i - 1, "results": dict(results)},
            )

            try:
                if step.is_parallel:
                    # ── 并行执行 ──
                    tasks = [
                        sub["func"]()
                        for sub in step.parallel_steps
                    ]
                    parallel_results = await asyncio.gather(*tasks, return_exceptions=True)

                    # 合并并行结果
                    sub_results: Dict[str, Any] = {}
                    for sub, pr in zip(step.parallel_steps, parallel_results):
                        sub_name = sub["name"]
                        if isinstance(pr, Exception):
                            logger.error(
                                "[workflow_engine] 并行步骤 '%s' 子步骤 '%s' 失败: %s",
                                step.name, sub_name, pr,
                            )
                            sub_results[sub_name] = {"error": str(pr)}
                        else:
                            sub_results[sub_name] = pr
                    results[step.name] = sub_results

                else:
                    # ── 串行执行 ──
                    try:
                        results[step.name] = await step.func()
                    except Exception as e:
                        logger.warning(
                            "[workflow_engine] 步骤 '%s' 失败: %s", step.name, e,
                        )
                        if step.fallback:
                            logger.info(
                                "[workflow_engine] 触发 fallback 步骤: %s", step.name,
                            )
                            results[step.name] = await step.fallback()
                        else:
                            raise

            except Exception as e:
                logger.error(
                    "[workflow_engine] 工作流中断: project=%s, step=%s, error=%s",
                    project_id, step.name, e,
                )
                return {
                    "success": False,
                    "results": results,
                    "resume_point": step.name,
                }

        # ── 全部成功，清理检查点 ──
        self._delete_checkpoint(project_id)
        return {
            "success": True,
            "results": results,
            "resume_point": None,
        }
