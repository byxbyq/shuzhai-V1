# -*- coding: utf-8 -*-
"""
书斋 V66 — 分镜视频工具模型适配器 (SB-8)

将"内容理解"与"工具适配"彻底解耦：
- IR 层只描述画面内容（场景/角色/运镜/光影），不关心目标工具
- 适配器层负责把同一份 IR 渲染成不同视频工具（kling/sora/jimeng/通用）
  各自的 prompt 格式、语言习惯与关键词规范

设计：
- VideoToolAdapter 抽象基类：定义统一的渲染接口
- 内置适配器：KlingAdapter / SoraAdapter / JimengAdapter / GenericAdapter
- AdapterRegistry：按 target_tool 名称查找适配器，未知工具回退到通用适配器
"""

from __future__ import annotations

import logging
from abc import ABC
from typing import Dict, List, Optional

from .storyboard_ir import StoryboardShot, StoryboardIR

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────
# 抽象基类
# ──────────────────────────────────────────────────

class VideoToolAdapter(ABC):
    """视频工具适配器抽象基类。

    子类需实现：
        tool_id      — 唯一标识（与 options.target_tool 对应）
        tool_name    — 可读名称
        lang         — 语言指导（用于 prompt 中说明输出语言）
        tip          — 风格/格式提示（用于 prompt 中说明工具特点）

    子类可覆写：
        render_prompt_full(shot)   — 渲染完整可复制的 AI 视频生成提示词
        render_prompt_short(shot)  — 渲染简短关键词版本
        build_guide_block()        — 构建注入 prompt 的工具指导块
    """

    tool_id: str = ""
    tool_name: str = ""
    lang: str = ""
    tip: str = ""

    # ── 供 prompt 构建使用 ──

    def guide_dict(self) -> Dict[str, str]:
        """返回与旧 TOOL_GUIDE 兼容的字典，供 PromptConfig 使用"""
        return {"lang": self.lang, "tip": self.tip}

    def build_guide_block(self) -> str:
        """构建注入 prompt 的工具指导块"""
        return f"- 语言：{self.lang}\n- 工具适配：{self.tip}"

    # ── 渲染接口（默认实现：基于 shot 字段通用渲染） ──

    def render_prompt_full(self, shot: StoryboardShot) -> str:
        """渲染完整可复制的 AI 视频生成提示词。

        默认实现使用通用电影描述风格；各工具适配器覆写以输出
        符合工具习惯的语言/结构/关键词。
        """
        parts = [shot.scene_description]
        if shot.lighting:
            parts.append(f"光影：{shot.lighting}")
        if shot.color_palette:
            parts.append(f"色调：{shot.color_palette}")
        if shot.character_positions:
            chars = "；".join(
                f"{c.get('name','')}({c.get('position','')}，{c.get('action','')})"
                for c in shot.character_positions
            )
            parts.append(f"角色：{chars}")
        return "，".join(parts)

    def render_prompt_short(self, shot: StoryboardShot) -> str:
        """渲染简短关键词版本"""
        keywords = [shot.shot_type, shot.camera_movement]
        if shot.character_positions:
            keywords.append(shot.character_positions[0].get("name", ""))
        return ", ".join(k for k in keywords if k)

    # ── 校验 ──

    def validate_shot(self, shot: StoryboardShot) -> List[str]:
        """对镜头做工具相关的合理性检查，返回问题列表（空=通过）"""
        return []

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} tool_id={self.tool_id}>"


# ──────────────────────────────────────────────────
# 内置适配器
# ──────────────────────────────────────────────────

class KlingAdapter(VideoToolAdapter):
    """可灵（Kling）适配器 — 中文详述、强调构图/神态/氛围"""

    tool_id = "kling"
    tool_name = "可灵Kling"
    lang = "中文详述"
    tip = "使用中文进行细致描述，突出画面构图、角色神态、氛围意境。关键词部分用中文短语。"

    def render_prompt_full(self, shot: StoryboardShot) -> str:
        parts = [shot.scene_description]
        if shot.character_positions:
            chars = "；".join(
                f"{c.get('name','')}：{c.get('action','')}"
                for c in shot.character_positions
            )
            parts.append(f"角色神态与动作：{chars}")
        if shot.lighting:
            parts.append(f"构图光影：{shot.lighting}")
        if shot.color_palette:
            parts.append(f"色彩氛围：{shot.color_palette}")
        return "，".join(parts)


class SoraAdapter(VideoToolAdapter):
    """Sora 适配器 — 英文物理描述、强调真实物理/材质/光学"""

    tool_id = "sora"
    tool_name = "Sora"
    lang = "英文物理描述"
    tip = ("Use English physical descriptions. Focus on realistic physics, "
           "material properties, camera optics, lighting physics. "
           "Short keywords in English.")

    def render_prompt_full(self, shot: StoryboardShot) -> str:
        parts = [shot.scene_description]
        if shot.lighting:
            parts.append(f"lighting: {shot.lighting}")
        if shot.character_positions:
            chars = "; ".join(
                f"{c.get('name','')} {c.get('action','')}"
                for c in shot.character_positions
            )
            parts.append(f"subjects: {chars}")
        if shot.camera_movement:
            parts.append(f"camera: {shot.camera_movement}")
        return ". ".join(parts)

    def render_prompt_short(self, shot: StoryboardShot) -> str:
        en_map = {
            "远景": "wide shot", "全景": "full shot", "中景": "medium shot",
            "近景": "close shot", "特写": "close-up", "大特写": "extreme close-up",
            "POV": "POV",
            "推镜": "dolly in", "拉镜": "dolly out", "平移": "pan",
            "俯仰": "tilt", "静态": "static", "跟拍": "tracking", "环绕": "orbit", "摇镜": "swing",
        }
        keywords = [
            en_map.get(shot.shot_type, shot.shot_type),
            en_map.get(shot.camera_movement, shot.camera_movement),
        ]
        return ", ".join(k for k in keywords if k)


class JimengAdapter(VideoToolAdapter):
    """即梦（Jimeng）适配器 — 中文核心描述 + 英文风格标签"""

    tool_id = "jimeng"
    tool_name = "即梦Jimeng"
    lang = "中文+风格标签"
    tip = ("中文核心描述 + 英文风格标签。例如：'一位侠客在竹林中持剑，雾气弥漫' "
           "+ cinematic lighting, bamboo forest, mist, dynamic pose")

    def render_prompt_full(self, shot: StoryboardShot) -> str:
        parts = [shot.scene_description]
        if shot.lighting:
            parts.append(f"光影：{shot.lighting}")
        tags = self._style_tags(shot)
        if tags:
            parts.append(" + " + ", ".join(tags))
        return "，".join(parts)

    def _style_tags(self, shot: StoryboardShot) -> List[str]:
        tags = []
        move_map = {"推镜": "dolly in", "拉镜": "dolly out", "环绕": "orbit",
                    "跟拍": "tracking shot", "静态": "static shot", "摇镜": "swing"}
        if shot.camera_movement in move_map:
            tags.append(move_map[shot.camera_movement])
        if shot.character_positions:
            tags.append("character focus")
        return tags


class GenericAdapter(VideoToolAdapter):
    """通用适配器 — 兼容主流 AI 视频工具的中文详述"""

    tool_id = "通用"
    tool_name = "通用适配"
    lang = "中文详述"
    tip = "使用中文详述，兼容主流AI视频工具。画面描述具体、光影明确、动作清晰。"


# ──────────────────────────────────────────────────
# 注册表
# ──────────────────────────────────────────────────

class AdapterRegistry:
    """视频工具适配器注册表（单例）"""

    _instance: Optional["AdapterRegistry"] = None

    def __new__(cls) -> "AdapterRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._adapters: Dict[str, VideoToolAdapter] = {}
            cls._instance._register_builtin()
        return cls._instance

    def _register_builtin(self):
        """注册内置适配器"""
        for adapter in (KlingAdapter(), SoraAdapter(), JimengAdapter(), GenericAdapter()):
            self.register(adapter)

    def register(self, adapter: VideoToolAdapter) -> None:
        """注册一个适配器实例（按 tool_id）"""
        if not adapter.tool_id:
            logger.warning("[adapter_registry] 忽略无 tool_id 的适配器: %s", type(adapter).__name__)
            return
        self._adapters[adapter.tool_id] = adapter
        logger.debug("[adapter_registry] 注册适配器: %s", adapter.tool_id)

    def get(self, tool_id: str) -> VideoToolAdapter:
        """按工具名获取适配器，未知工具回退到通用适配器"""
        return self._adapters.get(tool_id, self._adapters.get("通用", GenericAdapter()))

    def list(self) -> List[Dict[str, str]]:
        """列出所有已注册适配器信息"""
        return [
            {"tool_id": a.tool_id, "tool_name": a.tool_name,
             "lang": a.lang, "tip": a.tip}
            for a in self._adapters.values()
        ]

    def __len__(self) -> int:
        return len(self._adapters)


def get_adapter_registry() -> AdapterRegistry:
    """获取全局适配器注册表单例"""
    return AdapterRegistry()


def get_adapter(tool_id: str) -> VideoToolAdapter:
    """便捷函数：按工具名获取适配器"""
    return AdapterRegistry().get(tool_id)


def adapt_ir(ir: StoryboardIR, force: bool = False) -> StoryboardIR:
    """对 IR 中每个镜头应用目标工具适配器，渲染 prompt_full / prompt_short。

    默认仅填充缺失的 prompt 字段（AI 已返回的保留）；
    force=True 时统一重渲染，保证格式与工具一致。

    Args:
        ir: 分镜 IR
        force: 是否强制重渲染 prompt 字段

    Returns:
        适配后的 IR（原地修改并返回）
    """
    tool_id = ir.global_style.target_tool
    adapter = get_adapter(tool_id)
    for shot in ir.shots:
        if force or not shot.prompt_full or shot.prompt_full == shot.scene_description:
            shot.prompt_full = adapter.render_prompt_full(shot)
        if force or not shot.prompt_short:
            shot.prompt_short = adapter.render_prompt_short(shot)
    logger.info(
        "[adapter] IR 已应用适配器 tool=%s shots=%d force=%s",
        tool_id, len(ir.shots), force,
    )
    return ir
