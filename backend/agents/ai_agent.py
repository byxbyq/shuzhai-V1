# -*- coding: utf-8 -*-
"""
书斋 V66 - AI 创作 Agent
处理通用对话、头脑风暴、五感描写、分析、总结等 AI 调用意图。
"""

import json, logging

from backend.agents.base_agent import BaseAgent
from backend.agents.dispatcher import (
    _resolve_chapter_index,
    _api_post,
    _get_base_url,
    _clean_ai_output,
    _ANALYZE_TYPE_MAP,
)
from backend.agents.intent_classifier import call_ai
from backend.agents.prompts import (
    GENERAL_CHAT_PROMPT,
    ANALYZE_CHAPTER_PROMPT,
    SUMMARIZE_PLOT_PROMPT,
)
from backend.prompt_sanitizer import sanitize_user_input, sanitize_light
from backend.services.project_service import state

logger = logging.getLogger(__name__)


class AIAgent(BaseAgent):
    """处理 AI 创作相关意图：
    - general_chat: 通用对话
    - brainstorm: 头脑风暴
    - sensory: 五感描写
    - ai_analyze: AI分析设定
    - analyze_chapter: 深度分析章节
    - summarize_plot: 总结故事主线
    """

    agent_id = "ai"
    agent_name = "AI创作Agent"
    intent_keywords = [
        "general_chat", "brainstorm", "sensory",
        "ai_analyze", "analyze_chapter", "summarize_plot",
    ]

    def execute(self, params: dict, context: dict) -> dict:
        intent = params.get("_intent", "")
        self.log_event("ai_action", {"intent": intent})

        if intent == "general_chat":
            return self._general_chat(params, context)
        elif intent == "brainstorm":
            return self._brainstorm(params, context)
        elif intent == "sensory":
            return self._sensory(params, context)
        elif intent == "ai_analyze":
            return self._ai_analyze(params, context)
        elif intent == "analyze_chapter":
            return self._analyze_chapter(params, context)
        elif intent == "summarize_plot":
            return self._summarize_plot(params, context)
        else:
            return {"reply": "AI创作Agent: 未识别的子意图"}

    def _general_chat(self, params: dict, context: dict) -> dict:
        """通用对话"""
        message = params.get("message", "")
        prompt = GENERAL_CHAT_PROMPT.format(message=sanitize_user_input(message))
        reply = call_ai(prompt)
        return {"reply": reply}

    def _brainstorm(self, params: dict, context: dict) -> dict:
        """头脑风暴"""
        message = params.get("message", "")
        try:
            bs_result = _api_post(
                _get_base_url() + "/api/ai/brainstorm",
                {"topic": message, "context": "", "mode": "plot", "count": 5},
                timeout=300,
            )
            if bs_result.get("ok"):
                ideas = bs_result.get("ideas", [])
                text = "头脑风暴结果：\n"
                for i, idea in enumerate(ideas):
                    text += f"  {i+1}. {idea}\n"
                return {"reply": text}
            else:
                return {"reply": f"头脑风暴失败：{bs_result.get('error', '')}"}
        except Exception as e:
            return {"reply": f"头脑风暴出错：{e}"}

    def _sensory(self, params: dict, context: dict) -> dict:
        """五感描写"""
        message = params.get("message", "")
        scene = params.get("scene") or message
        sense_type = params.get("sense_type") or "all"
        try:
            sresult = _api_post(
                _get_base_url() + "/api/ai/sensory",
                {"scene": scene, "sense_type": sense_type, "style": ""},
                timeout=300,
            )
            if sresult.get("ok"):
                sensory_data = sresult.get("sensory", "")
                if isinstance(sensory_data, dict):
                    text = ""
                    for k, v in sensory_data.items():
                        text += f"  【{k}】{v}\n"
                    return {"reply": f"五感描写（{sense_type}）：\n{text}"}
                elif isinstance(sensory_data, list):
                    return {"reply": f"五感描写（{sense_type}）：\n" + "\n".join(str(s) for s in sensory_data[:10])}
                else:
                    return {"reply": f"五感描写（{sense_type}）：\n{str(sensory_data)[:500]}"}
            else:
                return {"reply": f"生成失败：{sresult.get('error', '')}"}
        except Exception as e:
            return {"reply": f"五感描写生成出错：{e}"}

    def _ai_analyze(self, params: dict, context: dict) -> dict:
        """AI分析设定"""
        text_to_analyze = params.get("text") or ""
        if not text_to_analyze:
            return {"reply": "请提供要分析的文本内容。"}
        try:
            adata = _api_post(
                _get_base_url() + "/api/ai/analyze-content",
                {"content": text_to_analyze[:5000]},
                timeout=300,
            )
            if adata.get("ok"):
                settings = adata.get("settings", {})
                text = f"AI分析完成，提取了{adata.get('count', 0)}项设定：\n"
                for k, v in settings.items():
                    vstr = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
                    text += f"  【{k}】{vstr[:80]}\n"
                return {"reply": text, "data": adata}
            else:
                return {"reply": f"分析失败：{adata.get('error', '')}"}
        except Exception as e:
            return {"reply": f"AI分析出错：{e}"}

    def _analyze_chapter(self, params: dict, context: dict) -> dict:
        """深度分析章节"""
        analyze_type = params.get("analyze_type", "quality")
        character = params.get("character", "")
        idx = _resolve_chapter_index(params, context)

        # 收集分析素材
        if character and not idx and idx != 0:
            all_content = ""
            if state.project:
                for i in range(len(state.project.chapters)):
                    all_content += state.project.get_content(i) + "\n\n"
            analyze_target = all_content[:8000]
            type_desc = f"人物弧光（{character}）"
            prompt_extra = f"重点分析角色「{character}」的成长轨迹、性格变化、动机转变。"
        else:
            if idx is None or idx < 0:
                idx = context.get("current_chapter_index", 0)
            if not state.project or idx >= len(state.project.chapters):
                return {"reply": f"第{idx+1}章不存在。"}
            analyze_target = state.project.get_content(idx)[:6000]
            type_desc = _ANALYZE_TYPE_MAP.get(analyze_type, "综合分析")
            prompt_extra = ""
            if idx is not None:
                prompt_extra += f"这是第{idx+1}章的内容。"

        if not analyze_target.strip():
            return {"reply": "章节内容为空，无法分析。"}

        prompt = ANALYZE_CHAPTER_PROMPT.format(
            type_desc=type_desc,
            prompt_extra=prompt_extra,
            content=sanitize_light(analyze_target),
        )

        try:
            analysis = call_ai(prompt)
            analysis = _clean_ai_output(analysis)
            return {"reply": f"{type_desc}结果：\n\n{analysis}"}
        except Exception as e:
            return {"reply": f"分析失败：{e}"}

    def _summarize_plot(self, params: dict, context: dict) -> dict:
        """总结故事主线"""
        if not state.project or not state.project.chapters:
            return {"reply": "请先打开项目并生成章节内容。"}

        all_content = ""
        for i in range(len(state.project.chapters)):
            content = state.project.get_content(i)
            all_content += f"【第{i+1}章 {state.project.chapters[i].get('title','')}】\n{content[:1500]}\n\n"

        if not all_content.strip():
            return {"reply": "章节内容为空，无法总结。"}

        prompt = SUMMARIZE_PLOT_PROMPT.format(content=sanitize_light(all_content[:8000]))

        try:
            summary = call_ai(prompt)
            summary = _clean_ai_output(summary)
            return {"reply": f"故事主线总结：\n\n{summary}"}
        except Exception as e:
            return {"reply": f"总结失败：{e}"}
