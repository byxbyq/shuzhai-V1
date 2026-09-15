# -*- coding: utf-8 -*-
"""
书斋 V66 - 项目管理 Agent
处理项目创建、统计、模板相关意图。
"""

import re, logging

from backend.agents.base_agent import BaseAgent
from backend.agents.dispatcher import (
    _api_get,
    _api_post,
    _get_base_url,
    _GENRE_LIST,
    _TEMPLATE_KEYWORD_MAP,
)

logger = logging.getLogger(__name__)


class ProjectAgent(BaseAgent):
    """处理项目管理相关意图：
    - create_project: 新建项目
    - get_stats: 写作统计
    - get_templates: 获取模板列表
    - apply_template: 应用模板
    """

    agent_id = "project"
    agent_name = "项目Agent"
    intent_keywords = [
        "create_project", "get_stats",
        "get_templates", "apply_template",
    ]

    def execute(self, params: dict, context: dict) -> dict:
        intent = params.get("_intent", "")
        self.log_event("project_action", {"intent": intent})

        if intent == "create_project":
            return self._create_project(params, context)
        elif intent == "get_stats":
            return self._get_stats(params, context)
        elif intent == "get_templates":
            return self._get_templates(params, context)
        elif intent == "apply_template":
            return self._apply_template(params, context)
        else:
            return {"reply": "项目Agent: 未识别的子意图"}

    def _create_project(self, params: dict, context: dict) -> dict:
        """新建项目"""
        message = params.get("message", "")
        title = params.get("title", "")
        genre = params.get("genre", "")
        if not title:
            m = re.search(r'[《【](.+?)[》】]', message)
            if m:
                title = m.group(1)
            else:
                title = "新小说"
        if not genre:
            for g in _GENRE_LIST:
                if g in message:
                    genre = g
                    break
        chapter_count = 5
        m_cnt = re.search(r'(\d+)\s*章', message)
        if m_cnt:
            chapter_count = max(1, min(50, int(m_cnt.group(1))))
        try:
            from backend.services.project_service import create_project as _create_project
            proj = _create_project(title, genre, chapter_count)
            return {
                "reply": f"已新建{genre}小说《{title}》，共{chapter_count}章。\n\n接下来按顺序让我：\n1. '添加设定：故事发生在...主角是...'（设定世界观）\n2. '添加角色：林墨，28岁程序员'（添加角色）\n3. '生成大纲'（基于世界观和角色生成全书大纲）\n4. '生成人物档案'（生成详细人物档案）\n5. '生成全部章节大纲'（生成各章大纲）\n6. '全部生成'（生成正文）",
                "action": {"type": "reload_project"},
            }
        except Exception as e:
            return {"reply": f"新建项目失败：{e}"}

    def _get_stats(self, params: dict, context: dict) -> dict:
        """写作统计"""
        try:
            stats = _api_get(_get_base_url() + "/api/stats/summary", timeout=10)
            if stats.get("ok"):
                s = stats
                reply = (
                    f"写作统计：\n"
                    f"  总字数：{s.get('total_words', 0):,}\n"
                    f"  章节数：{s.get('total_chapters', 0)}\n"
                    f"  平均每章：{s.get('avg_chapter_words', 0):,}字\n"
                    f"  写作天数：{s.get('writing_days', 0)}天\n"
                    f"  连续天数：{s.get('streak_days', 0)}天"
                )
                best = s.get("best_day", {})
                if best:
                    reply += f"\n  最佳一天：{best.get('date', '')}写了{best.get('words', 0):,}字"
                return {"reply": reply, "data": stats, "action": {"type": "open_stats"}}
            else:
                return {"reply": "暂无统计数据。"}
        except Exception as e:
            return {"reply": f"获取统计失败：{e}"}

    def _get_templates(self, params: dict, context: dict) -> dict:
        """获取模板列表"""
        try:
            tpl_data = _api_get(_get_base_url() + "/api/templates/list", timeout=10)
            if tpl_data.get("ok"):
                tpls = tpl_data.get("templates", [])
                text = "可用大纲模板：\n"
                for t in tpls:
                    text += f"  - {t['name']}（{t['genre']}，{t['chapter_count']}章）- {t.get('description', '')[:40]}\n"
                return {"reply": text, "data": tpls}
            else:
                return {"reply": "获取模板失败。"}
        except Exception as e:
            return {"reply": f"获取模板失败：{e}"}

    def _apply_template(self, params: dict, context: dict) -> dict:
        """应用模板"""
        message = params.get("message", "")
        tpl_id = params.get("template_id")
        if not tpl_id:
            for kw, tid in _TEMPLATE_KEYWORD_MAP.items():
                if kw in message:
                    tpl_id = tid
                    break
        if not tpl_id:
            return {"reply": "请指定模板类型，比如「用退婚流模板」「用系统流模板」。可选：玄幻升级流、都市系统流、重生复仇流、女频宫斗流、无限流、种田文流。"}
        try:
            tpl_result = _api_post(
                _get_base_url() + "/api/templates/apply",
                {"template_id": tpl_id},
                timeout=10,
            )
            if tpl_result.get("ok"):
                return {"reply": "模板已应用，大纲已写入项目。", "action": {"type": "reload_outline"}}
            else:
                return {"reply": f"应用模板失败：{tpl_result.get('error', '')}"}
        except Exception as e:
            return {"reply": f"应用模板出错：{e}"}
