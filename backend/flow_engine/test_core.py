# -*- coding: utf-8 -*-
"""
白城主 Flow Engine 核心验证测试
运行: python backend/flow_engine/test_core.py
"""

import sys
import os
import asyncio

# 确保项目根在 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.flow_engine.node import NodeBase, PortType, NodeStatus
from backend.flow_engine.graph import FlowGraph, FlowGraphError
from backend.flow_engine.registry import NodeRegistry
from backend.flow_engine.executor import FlowExecutor


# ═══════════════════════════════════════════
# 测试用节点
# ═══════════════════════════════════════════

class TextNode(NodeBase):
    """输出固定文本"""
    node_id = "test_text"
    node_name = "文本节点"
    node_category = "测试"

    def setup(self):
        self.add_input("text", PortType.STRING, "文本", default="默认文本")
        self.add_output("output", PortType.STRING, "输出")

    async def execute(self):
        text = self.inputs.get("text", "默认文本")
        # 模拟微小延迟
        await asyncio.sleep(0.01)
        self.outputs["output"] = text.upper()


class ConcatNode(NodeBase):
    """拼接两个字符串"""
    node_id = "test_concat"
    node_name = "拼接节点"
    node_category = "测试"

    def setup(self):
        self.add_input("a", PortType.STRING, "字符串A")
        self.add_input("b", PortType.STRING, "字符串B", default="世界")
        self.add_output("result", PortType.STRING, "拼接结果")

    async def execute(self):
        a = self.inputs.get("a", "")
        b = self.inputs.get("b", "")
        await asyncio.sleep(0.01)
        self.outputs["result"] = f"{a} + {b}"


class FailNode(NodeBase):
    """故意失败的节点"""
    node_id = "test_fail"
    node_name = "失败节点"
    node_category = "测试"

    def setup(self):
        self.add_input("message", PortType.STRING, "错误信息", default="故意的失败")
        self.add_output("output", PortType.STRING, "输出")

    async def execute(self):
        msg = self.inputs.get("message", "失败")
        raise RuntimeError(msg)


class PassthroughNode(NodeBase):
    """透传节点（无输入也能执行）"""
    node_id = "test_passthrough"
    node_name = "透传节点"
    node_category = "测试"

    def setup(self):
        self.add_input("data", PortType.ANY, "数据", required=False)
        self.add_output("data", PortType.ANY, "输出")

    async def execute(self):
        data = self.inputs.get("data", None)
        await asyncio.sleep(0.01)
        self.outputs["data"] = data


# ═══════════════════════════════════════════
# 测试用例
# ═══════════════════════════════════════════

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name}" + (f" — {detail}" if detail else ""))


async def test_node_registry():
    print("\n=== 测试1: 节点注册 ===")
    registry = NodeRegistry()
    registry.register(TextNode)
    registry.register(ConcatNode)

    check("注册 text 节点", registry.is_registered("test_text"))
    check("注册 concat 节点", registry.is_registered("test_concat"))
    check("不存在的节点", not registry.is_registered("nonexistent"))

    # 创建实例
    node = registry.create("test_text", params={"text": "hello"})
    check("创建实例", node.instance_id.startswith("test_text_"))
    check("参数注入", node.inputs.get("text") == "hello")

    # 前端注册表
    frontend = registry.get_registry_for_frontend()
    check("前端注册表", len(frontend) == 2)
    check("注册表含 inputs", "inputs" in frontend[0] and "outputs" in frontend[0])


async def test_simple_chain():
    print("\n=== 测试2: 简单链式执行 ===")
    g = FlowGraph()
    a = g.add_node(TextNode(instance_id="a"))
    b = g.add_node(ConcatNode(instance_id="b"))

    a.inputs.set("text", "hello")
    g.connect("a", "output", "b", "a")

    check("图合法", g.is_valid())

    executor = FlowExecutor(g)
    result = await executor.run()

    check("执行成功", result.success)
    check("两个节点都完成", len(result.completed_nodes) == 2)
    check("输出正确", result.results[1].outputs.get("result") == "HELLO + 世界")


async def test_parallel_branches():
    print("\n=== 测试3: 并行分支 ===")
    g = FlowGraph()
    root = g.add_node(TextNode(instance_id="root"))
    left = g.add_node(TextNode(instance_id="left"))
    right = g.add_node(TextNode(instance_id="right"))
    merge = g.add_node(ConcatNode(instance_id="merge"))

    root.inputs.set("text", "source")
    g.connect("root", "output", "left", "text")
    g.connect("root", "output", "right", "text")
    g.connect("left", "output", "merge", "a")
    g.connect("right", "output", "merge", "b")

    check("图合法", g.is_valid())

    # 验证拓扑批次
    batches = g.topological_batches()
    check("3个批次", len(batches) == 3, f"实际 {len(batches)} 批")
    check("第1批: root", set(batches[0]) == {"root"})
    check("第2批: left+right", set(batches[1]) == {"left", "right"}, f"实际 {set(batches[1])}")
    check("第3批: merge", set(batches[2]) == {"merge"})

    executor = FlowExecutor(g)
    result = await executor.run()
    check("执行成功", result.success)
    check("4节点全完成", len(result.completed_nodes) == 4)


async def test_cycle_detection():
    print("\n=== 测试4: 环检测 ===")
    g = FlowGraph()
    a = g.add_node(TextNode(instance_id="a"))
    b = g.add_node(TextNode(instance_id="b"))
    c = g.add_node(TextNode(instance_id="c"))

    g.connect("a", "output", "b", "text")
    try:
        g.connect("b", "output", "c", "text")
        g.connect("c", "output", "a", "text")
        check("三节点环检测", False, "应该抛出但未抛出")
    except FlowGraphError as e:
        check("三节点环检测", "环" in str(e), str(e))


async def test_required_input_validation():
    print("\n=== 测试5: 必填输入校验 ===")
    g = FlowGraph()
    a = g.add_node(TextNode(instance_id="a"))
    b = g.add_node(ConcatNode(instance_id="b"))  # 需要 'a' 输入，但未连

    a.inputs.set("text", "hello")
    g.connect("a", "output", "b", "a")  # b.a 已连，b.b 有默认值

    check("图合法", g.is_valid())

    # 清除连线，b.a 没连又无默认值 → 不合法
    g.remove_edge(g.edges[0].id)
    errors = g.validate()
    check("缺少必填输入", len(errors) == 1 and "未连接" in errors[0], errors[0] if errors else "无错误")


async def test_fail_fast():
    print("\n=== 测试6: fail-fast 级联跳过 ===")
    g = FlowGraph()
    a = g.add_node(TextNode(instance_id="a"))
    bad = g.add_node(FailNode(instance_id="bad"))
    c = g.add_node(TextNode(instance_id="c"))

    a.inputs.set("text", "data")
    g.connect("a", "output", "bad", "message")
    g.connect("bad", "output", "c", "text")

    executor = FlowExecutor(g)
    result = await executor.run()

    check("执行失败", not result.success)
    check("失败节点存在", len(result.failed_nodes) >= 1)
    check("下游节点跳过", any(r.status == NodeStatus.SKIPPED for r in result.results))


async def test_registry_duplicate_warning():
    print("\n=== 测试7: 重复注册覆盖 ===")
    reg = NodeRegistry()
    reg.register(TextNode)

    # 用同名 node_id 的冒牌节点覆盖
    class TextNodeV2(TextNode):
        node_id = "test_text"
    reg.register(TextNodeV2)

    check("覆盖后仍是新类", reg.get_class("test_text") is TextNodeV2)


async def main():
    global passed, failed
    passed = 0
    failed = 0

    print("=" * 50)
    print("白城主 Flow Engine 核心验证")
    print("=" * 50)

    await test_node_registry()
    await test_simple_chain()
    await test_parallel_branches()
    await test_cycle_detection()
    await test_required_input_validation()
    await test_fail_fast()
    await test_registry_duplicate_warning()

    print(f"\n{'=' * 50}")
    print(f"结果: {passed}/{passed + failed} 通过", end="")
    if failed:
        print(f", {failed} 失败")
    else:
        print(" ✓")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
