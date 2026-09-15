# -*- coding: utf-8 -*-
"""
白城主 Flow Engine — 节点抽象基类

每个节点 = 一组输入端口 + 一组输出端口 + 一个 execute() 方法。
借鉴 ComfyUI 的端口类型系统，但更轻量。
"""

from __future__ import annotations

import uuid
import logging
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PortType(str, Enum):
    """端口数据类型"""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    JSON = "json"           # 任意 JSON-serializable 结构
    TEXT = "text"           # 长文本（章节内容等）
    IMAGE = "image"         # 图片路径 / base64
    VIDEO = "video"         # 视频路径
    AUDIO = "audio"         # 音频路径
    ANY = "any"             # 不限制类型


class NodeStatus(str, Enum):
    """节点执行状态"""
    IDLE = "idle"
    PENDING = "pending"      # 等待上游
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PortDefinition:
    """端口定义：节点的输入或输出口"""
    name: str
    type: PortType = PortType.ANY
    label: str = ""
    description: str = ""
    required: bool = True
    default: Any = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type.value,
            "label": self.label or self.name,
            "description": self.description,
            "required": self.required,
            "default": self.default,
        }


class NodeInput:
    """
    节点输入容器。
    执行时由引擎注入数据，节点通过 self.inputs["port_name"] 读取。
    """

    def __init__(self, definitions: List[PortDefinition]):
        self._defs: Dict[str, PortDefinition] = {d.name: d for d in definitions}
        self._values: Dict[str, Any] = {}

    def set(self, port_name: str, value: Any) -> None:
        """引擎注入输入值"""
        self._values[port_name] = value

    def get(self, port_name: str, default: Any = None) -> Any:
        """节点读取输入值"""
        if port_name in self._values:
            return self._values[port_name]
        d = self._defs.get(port_name)
        if d and d.default is not None:
            return d.default
        return default

    def __getitem__(self, port_name: str) -> Any:
        return self._values.get(port_name)

    def __contains__(self, port_name: str) -> bool:
        return port_name in self._values

    @property
    def definitions(self) -> List[PortDefinition]:
        return list(self._defs.values())

    def to_dict(self) -> dict:
        return {k: v for k, v in self._values.items()}


class NodeOutput:
    """
    节点输出容器。
    节点通过 self.outputs["port_name"] = value 写入。
    """

    def __init__(self, definitions: List[PortDefinition]):
        self._defs: Dict[str, PortDefinition] = {d.name: d for d in definitions}
        self._values: Dict[str, Any] = {}

    def set(self, port_name: str, value: Any) -> None:
        self._values[port_name] = value

    def get(self, port_name: str) -> Any:
        return self._values.get(port_name)

    def __setitem__(self, port_name: str, value: Any) -> None:
        self._values[port_name] = value

    def __getitem__(self, port_name: str) -> Any:
        return self._values.get(port_name)

    @property
    def definitions(self) -> List[PortDefinition]:
        return list(self._defs.values())

    def to_dict(self) -> dict:
        return {k: v for k, v in self._values.items()}

    def export(self) -> dict:
        """导出可序列化的输出数据"""
        return {k: v for k, v in self._values.items()}


class NodeBase(ABC):
    """
    白城主节点基类。

    最小实现：
        class MyNode(NodeBase):
            node_id = "my_node"
            node_name = "我的节点"

            def setup(self):
                self.add_input("text", PortType.TEXT, "输入文本")
                self.add_output("result", PortType.TEXT, "处理结果")

            async def execute(self) -> None:
                text = self.inputs["text"]
                self.outputs["result"] = text.upper()

    注册到市场：
        registry.register(MyNode)
    """

    # ── 子类覆盖 ──
    node_id: str = ""           # 全局唯一 ID（snake_case）
    node_name: str = ""         # 显示名称
    node_category: str = "通用"  # 分类
    node_description: str = ""  # 描述
    node_version: str = "1.0.0"
    node_icon: str = ""         # emoji 或图标名

    def __init__(self, instance_id: Optional[str] = None):
        self.instance_id = instance_id or self._generate_id()
        self.status = NodeStatus.IDLE
        self.error: Optional[str] = None
        self._input_defs: List[PortDefinition] = []
        self._output_defs: List[PortDefinition] = []
        self.setup()
        self.inputs = NodeInput(self._input_defs)
        self.outputs = NodeOutput(self._output_defs)

    # ── 配置方法 ──

    def add_input(
        self,
        name: str,
        type: PortType = PortType.ANY,
        label: str = "",
        description: str = "",
        required: bool = True,
        default: Any = None,
    ) -> None:
        self._input_defs.append(
            PortDefinition(
                name=name,
                type=type,
                label=label or name,
                description=description,
                required=required,
                default=default,
            )
        )

    def add_output(
        self,
        name: str,
        type: PortType = PortType.ANY,
        label: str = "",
        description: str = "",
    ) -> None:
        self._output_defs.append(
            PortDefinition(
                name=name,
                type=type,
                label=label or name,
                description=description,
                required=False,
            )
        )

    def setup(self) -> None:
        """
        子类在此声明输入/输出端口。
        在 __init__ 中自动调用，此时 self._input_defs / self._output_defs 可用。
        """
        pass

    # ── 核心方法 ──

    @abstractmethod
    async def execute(self) -> None:
        """
        执行节点逻辑。
        从 self.inputs 读取数据，写入 self.outputs。
        抛出异常即视为执行失败。
        """
        ...

    # ── 元信息 ──

    def get_input_defs(self) -> List[PortDefinition]:
        return self._input_defs

    def get_output_defs(self) -> List[PortDefinition]:
        return self._output_defs

    def to_definition(self) -> dict:
        """导出节点类型定义（供前端注册表使用）"""
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "node_category": self.node_category,
            "node_description": self.node_description,
            "node_version": self.node_version,
            "node_icon": self.node_icon,
            "inputs": [d.to_dict() for d in self._input_defs],
            "outputs": [d.to_dict() for d in self._output_defs],
        }

    def _generate_id(self) -> str:
        return f"{self.node_id}_{uuid.uuid4().hex[:8]}"

    def __repr__(self) -> str:
        return f"<{self.node_name}({self.instance_id}) [{self.status.value}]>"
