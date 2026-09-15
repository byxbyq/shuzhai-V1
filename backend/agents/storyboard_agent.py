# -*- coding: utf-8 -*-
"""
书斋 V66 - 分镜 Agent（SB-11 flow 节点接入）
处理分镜生成意图：真正调用 StoryboardService 生成分镜，
而不是像旧版 ExportAgent 那样仅打开页面。

支持：
- storyboard: 为指定章节生成视频分镜脚本
  可选参数：target_tool（kling/sora/jimeng/通用）、style_preset、shot_density、language
"""

import logging

from backend.agents.base_agent import BaseAgent
from backend.agents.dispatcher import (
    _resolve_chapter_index,
    _get_chapter_content,
)

logger = logging.getLogger(__name__)

# 允许透传的分镜生成选项白名单
_STORYBOARD_OPTION_KEYS = (
    "target_tool", "style_preset", "shot_density", "language", "max_shots",
)


class StoryboardAgent(BaseAgent):
    """处理分镜相关意图：
    - storyboard: 生成分镜
    """

    agent_id = "storyboard"
    agent_name = "分镜Agent"
    intent_keywords = ["storyboard"]

    def execute(self, params: dict, context: dict) -> dict:
        intent = params.get("_intent", "")
        self.log_event("storyboard_action", {"intent": intent})

        if intent == "storyboard":
            return self._storyboard(params, context)
        else:
            return {"reply": "分镜Agent: 未识别的子意图"}

    def _storyboard(self, params: dict, context: dict) -> dict:
        """为指定章节生成分镜脚本"""
        idx = _resolve_chapter_index(params, context)
        title, content = _get_chapter_content(idx)
        if not content:
            return {"reply": f"第{idx+1}章内容为空，无法生成分镜。请先写入章节内容。"}

        if len(content) < 50:
            return {
                "reply": f"第{idx+1}章文本过短（{len(content)}字），至少需要50字才能生成有意义的分镜。"
            }

        # 组装生成选项（仅透传白名单内参数）
        options = {}
        for key in _STORYBOARD_OPTION_KEYS:
            val = params.get(key)
            if val is not None and val != "":
                options[key] = val

        try:
            from backend.services.storyboard_service import StoryboardService
            service = StoryboardService()
            result = service.generate(text=content, options=options)

            shots = result.get("shots", [])
            style = result.get("global_style", {}).get("style_preset", "默认")
            warnings = result.get("warnings") or []

            reply = (
                f"已为第{idx+1}章生成分镜：{len(shots)}个镜头，"
                f"风格「{style}」，分镜ID {result.get('storyboard_id', '')}。"
            )
            if warnings:
                reply += "\n提示：" + "；".join(warnings[:3])

            return {
                "reply": reply,
                "data": result,
                "action": {"type": "open_storyboard", "chapter_index": idx},
            }
        except Exception as e:
            logger.error("[storyboard_agent] 生成分镜失败: %s", e, exc_info=True)
            return {"reply": f"分镜生成失败：{str(e)}"}
