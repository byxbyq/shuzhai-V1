# -*- coding: utf-8 -*-
"""
端到端验证: ① 执行链路  ② 持久化
"""

import sys
import asyncio
import os

sys.path.insert(0, r"H:\素材资源\小说\书斋V66-新重构")

from backend.flow_engine.node import NodeBase, NodeStatus, PortType
from backend.flow_engine.graph import FlowGraph
from backend.flow_engine.executor import FlowExecutor
from backend.flow_engine.registry import registry
from backend.flow_engine.nodes.configurable import register_config_node
from backend.flow_engine.nodes.store import save_config, load_all_configs, delete_config


def test_01_executor_basic():
    """测试1: FlowExecutor 基本执行链路（非 HTTP 节点）"""
    print("=" * 60)
    print("测试1: FlowExecutor 基本执行链路")
    print("=" * 60)

    class AddNode(NodeBase):
        node_id = "test.add"
        node_name = "加法节点"

        def setup(self):
            self.add_input("a", type=PortType.NUMBER, default=0)
            self.add_input("b", type=PortType.NUMBER, default=0)
            self.add_output("sum", type=PortType.NUMBER)

        async def execute(self):
            a = self.inputs.get("a") or 0
            b = self.inputs.get("b") or 0
            self.outputs.set("sum", a + b)
            self.status = NodeStatus.COMPLETED

    class MulNode(NodeBase):
        node_id = "test.mul"
        node_name = "乘法节点"

        def setup(self):
            self.add_input("x", type=PortType.NUMBER, default=1)
            self.add_input("y", type=PortType.NUMBER, default=1)
            self.add_output("product", type=PortType.NUMBER)

        async def execute(self):
            x = self.inputs.get("x") or 0
            y = self.inputs.get("y") or 0
            self.outputs.set("product", x * y)
            self.status = NodeStatus.COMPLETED

    async def run():
        graph = FlowGraph()

        n1 = AddNode(instance_id="add_1")
        n2 = MulNode(instance_id="mul_1")
        n1.inputs.set("a", 5)
        n1.inputs.set("b", 3)

        graph.add_node(n1)
        graph.add_node(n2)
        graph.connect("add_1", "sum", "mul_1", "x")
        n2.inputs.set("y", 10)

        errs = graph.validate()
        assert errs == [], f"校验失败: {errs}"
        print(f"  [OK] 图校验通过（2 节点 1 连线）")

        executor = FlowExecutor(graph)
        result = await executor.run()
        assert result.success, f"执行失败: {result.failed_nodes}"
        print(f"  [OK] 执行成功，耗时 {result.total_duration_ms:.0f}ms")

        for r in result.results:
            print(f"  - {r.node_name}: {r.status} → {r.outputs}")

        # 验证数据传递：5+3=8 → 8*10=80
        mul_output = [r for r in result.results if r.node_name == "乘法节点"][0]
        assert mul_output.outputs["product"] == 80, f"期望 80，实际 {mul_output.outputs}"
        print(f"  [OK] 数据流验证通过: (5+3)*10 = {mul_output.outputs['product']}")
        print()

    asyncio.run(run())


def test_02_executor_with_mini_pipeline():
    """测试2: MiniPipelineNode 在 FlowExecutor 中的执行"""
    print("=" * 60)
    print("测试2: MiniPipelineNode + FlowExecutor（Mock HTTP）")
    print("=" * 60)

    from unittest.mock import patch, AsyncMock
    import json as _json

    HAILUO_CONFIG = {
        "node_id": "hailuo.test",
        "node_name": "海螺视频",
        "node_category": "AI生视频",
        "inputs": [
            {"name": "reference_image", "type": "image", "required": True},
            {"name": "prompt", "type": "text", "default": "默认提示词"},
        ],
        "outputs": [
            {"name": "video_url", "type": "text"},
            {"name": "task_id", "type": "text"},
        ],
        "steps": [
            {
                "name": "submit",
                "api": {
                    "method": "POST",
                    "url": "https://api.hailuo.video/v1/videos",
                    "headers": {"Content-Type": "application/json"},
                    "body": {"prompt": "${input:prompt}", "image_url": "${input:reference_image}"},
                },
                "extract": {"task_id": "data.task_id"},
            },
            {
                "name": "poll",
                "poll": {
                    "url": "https://api.hailuo.video/v1/tasks/${step:submit.task_id}",
                    "interval_ms": 100,
                    "timeout_ms": 5000,
                    "until": "$.data.status == 'completed'",
                },
                "extract": {"video_url": "data.video_url"},
            },
        ],
    }

    # 注册节点
    cls = register_config_node(HAILUO_CONFIG, registry)
    assert cls is not None, "注册失败"
    node_id = HAILUO_CONFIG["node_id"]
    print(f"  [OK] 注册成功: {node_id} → {cls.__name__}")

    # 检查持久化
    saved = load_all_configs()
    assert any(c["node_id"] == node_id for c in saved), "持久化失败"
    print(f"  [OK] 已持久化（{len(saved)} 个节点）")

    # 从注册表创建实例
    node = registry.create(node_id)
    assert node._config == HAILUO_CONFIG, "_config 未回填"
    print(f"  [OK] _config 已回填")

    # 创建完整 mock client
    async def mock_post_impl(*args, **kwargs):
        url = args[1] if len(args) >= 2 else kwargs.get("url", "")
        resp = AsyncMock()
        resp.status_code = 200
        if "submit" in url or "create" in url:
            body = {"code": 200, "data": {"task_id": "task_mock_12345"}}
        else:
            body = {"code": 200, "data": {"status": "completed", "video_url": "https://example.com/video.mp4"}}
        resp.json.return_value = body
        resp.text = _json.dumps(body)
        return resp

    async def run():
        # Mock httpx.AsyncClient
        mock_client = AsyncMock()
        mock_client.post.side_effect = mock_post_impl
        mock_client.get.side_effect = mock_post_impl

        with patch("httpx.AsyncClient", return_value=mock_client):
            n = registry.create(node_id)
            n.inputs.set("reference_image", "https://example.com/img.png")
            n.inputs.set("prompt", "人物从画中走出来")
            await n.execute()

        assert n.status == NodeStatus.COMPLETED, f"状态异常: {n.status} error={n.outputs.get('error')}"
        print(f"  [OK] 执行状态: {n.status}")
        assert n.outputs.get("video_url") == "https://example.com/video.mp4"
        print(f"  [OK] video_url: {n.outputs.get('video_url')}")
        assert n.outputs.get("task_id") == "task_mock_12345"
        print(f"  [OK] task_id: {n.outputs.get('task_id')}")
        print()

    asyncio.run(run())


def test_03_persistence():
    """测试3: 持久化存储"""
    print("=" * 60)
    print("测试3: 持久化存储")
    print("=" * 60)

    store_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "backend", "flow_engine", "nodes", "config_nodes.json"
    )

    assert os.path.exists(store_path), f"存储文件不存在: {store_path}"
    print(f"  [OK] 存储文件存在: .../config_nodes.json")

    configs = load_all_configs()
    print(f"  已保存节点: {[c['node_id'] for c in configs]}")
    assert len(configs) >= 1, "应有至少 1 个已保存节点"
    print(f"  [OK] 共 {len(configs)} 个节点已持久化")

    # 测试删除
    test_id = "hailuo.test"
    ok = delete_config(test_id)
    assert ok, "删除失败"
    configs = load_all_configs()
    assert not any(c["node_id"] == test_id for c in configs), "删除后仍存在"
    print(f"  [OK] 删除节点 {test_id} 成功，剩余 {len(configs)} 个")

    # 重新保存测试节点
    saved_config = {
        "node_id": "test.persist",
        "node_name": "持久化测试节点",
        "node_category": "测试",
        "inputs": [{"name": "in1", "type": "text"}],
        "outputs": [{"name": "out1", "type": "text"}],
        "steps": [
            {
                "name": "step1",
                "api": {"method": "GET", "url": "https://example.com/test"},
                "extract": {"out1": "data.result"},
            }
        ],
    }
    save_config(saved_config)
    configs = load_all_configs()
    assert any(c["node_id"] == "test.persist" for c in configs), "重新保存失败"
    print(f"  [OK] 保存节点 test.persist 成功")

    # 清理
    delete_config("test.persist")
    print(f"  [OK] 清理完成")
    print()


if __name__ == "__main__":
    test_01_executor_basic()
    test_02_executor_with_mini_pipeline()
    test_03_persistence()

    print("=" * 60)
    print("全部测试通过!")
    print("=" * 60)
