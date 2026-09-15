# -*- coding: utf-8 -*-
"""
书斋 V66 — Prompt 分层组装器（自研）

五层组装模型：System基础层 → 技能注入层 → 规则注入层 → 上下文层 → 用户指令层。
每层是独立管理单元，可动态增删，按优先级排序后拼接。

使用示例::

    assembler = PromptAssembler()
    assembler.add_layer("system", "你是书斋AI助手", priority=10)
    assembler.add_layer("skills", "可用技能：生成大纲、续写正文", priority=20)
    assembler.add_layer("rules", "回复需简洁专业", priority=30)
    assembler.add_layer("context", "当前章节：第3章 决战", priority=40)
    assembler.add_layer("user", "帮我续写500字", priority=50)
    prompt = assembler.assemble()  # 自动按priority排序拼接
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 层分隔符 ──
_LAYER_SEPARATOR = "\n\n---\n\n"


class PromptAssembler:
    """Prompt 分层组装器。

    管理五层 Prompt 结构，每层是独立的 ``{name, content, priority}`` 管理单元。
    按 priority 数值由小到大排序后拼接。

    Attributes:
        layers: 当前层定义字典，key 为层名，value 为 ``{"content": str, "priority": int}``
    """

    def __init__(self):
        self.layers: Dict[str, Dict] = {}

    # ── 层操作 ──

    def add_layer(self, name: str, content: str, priority: int) -> None:
        """添加或更新一个 Prompt 层。

        Args:
            name: 层名称（如 system / skills / rules / context / user）
            content: 层内容文本
            priority: 排序优先级，数值越小越靠前
        """
        self.layers[name] = {"content": content, "priority": priority}
        logger.debug("[prompt_assembler] 添加层: name=%s, priority=%d, len=%d", name, priority, len(content))

    def remove_layer(self, name: str) -> bool:
        """删除指定层（完全移除，下次 add 时重新创建）。

        Args:
            name: 层名称

        Returns:
            True 表示删除成功，False 表示层不存在
        """
        if name in self.layers:
            del self.layers[name]
            logger.debug("[prompt_assembler] 删除层: name=%s", name)
            return True
        return False

    def clear_layer(self, name: str) -> bool:
        """清空指定层内容（保留层定义，但 content 置空）。

        与 ``remove_layer`` 的区别：清空后该层仍然存在于排序中，
        只是内容为空，``add_layer`` 再次调用时会覆盖。

        Args:
            name: 层名称

        Returns:
            True 表示清空成功，False 表示层不存在
        """
        if name in self.layers:
            self.layers[name]["content"] = ""
            logger.debug("[prompt_assembler] 清空层: name=%s", name)
            return True
        return False

    # ── 组装 ──

    def assemble(self, context: Optional[Dict[str, str]] = None) -> str:
        """按优先级排序后拼接所有非空层，返回完整 Prompt 字符串。

        Args:
            context: 可选上下文变量映射，用于模板替换。
                     例如 ``{"chapter_title": "第3章 决战"}``，
                     会在各层 content 中执行 ``{chapter_title}`` → 实际值替换。

        Returns:
            组装后的完整 Prompt 字符串，各层以 ``---`` 分隔。
        """
        if not self.layers:
            return ""

        # 按 priority 排序
        sorted_layers = sorted(
            self.layers.items(),
            key=lambda item: item[1]["priority"],
        )

        segments: List[str] = []
        for name, layer in sorted_layers:
            content = layer.get("content", "")
            if not content:
                continue
            # 模板替换
            if context:
                try:
                    content = content.format(**context)
                except KeyError as e:
                    logger.warning(
                        "[prompt_assembler] 层 '%s' 缺少模板变量: %s", name, e,
                    )
                except ValueError as e:
                    logger.warning(
                        "[prompt_assembler] 层 '%s' 模板替换失败: %s", name, e,
                    )
            segments.append(content)

        return _LAYER_SEPARATOR.join(segments)
