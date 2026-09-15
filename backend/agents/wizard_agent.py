# -*- coding: utf-8 -*-
"""
书斋 V66 - 创作向导 Agent
处理新手创作向导的多轮对话流程。
阶段：选题材 → 生成世界设定 → 设主角 → 生成人物 → 一句话剧情 → 生成大纲 → 生成蓝图
"""

import json, logging

from backend.agents.base_agent import BaseAgent
from backend.agents.dispatcher import _clean_ai_output
from backend.agents.intent_classifier import call_ai
from backend.prompt_sanitizer import sanitize_light
from backend.services.project_service import state

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 各阶段 Prompt 模板
# ═══════════════════════════════════════════

WIZARD_WORLD_PROMPT = """你是一个中文网络小说创作助手。用户想写一本{genre}题材的小说。

请生成紧凑的世界观设定（控制在300字以内），包含：
1. 世界观名称（一个精炼的名字，如"灵气复苏都市"）
2. 时代背景（1-2句）
3. 力量体系核心概念（2-3条，每条一句话）
4. 世界独特性（1-2个独特设定）

只输出JSON，不要解释：
{{
  "name": "世界观名称",
  "era": "时代背景描述",
  "power_system": ["力量体系1", "力量体系2"],
  "unique_features": ["独特设定1"],
  "raw_text": "完整纯文本描述"
}}"""

WIZARD_CHARACTER_PROMPT = """你是一个中文网络小说创作助手。用户正在创作一本{genre}题材的小说。

当前已有世界观设定：
{world_context}

用户的主角信息：{protagonist_info}

请生成主角详细档案（控制在400字以内），包含：
1. 姓名
2. 年龄
3. 外貌特征
4. 性格特点（3个关键词）
5. 背景故事（2-3句）
6. 目标与动机

只输出JSON，不要解释：
{{
  "name": "主角姓名",
  "age": "年龄",
  "appearance": "外貌描述",
  "personality": ["关键词1", "关键词2", "关键词3"],
  "background": "背景故事",
  "goal": "目标与动机",
  "raw_text": "完整纯文本档案"
}}"""

WIZARD_OUTLINE_PROMPT = """你是一个中文网络小说创作助手。用户想写一本{genre}题材的小说。

世界观设定：{world_context}
主角信息：{character_context}
一句话主线：{oneliner}

请生成全书大纲（控制在300字以内），只描述整体架构：
1. 故事的核心冲突是什么
2. 分为几个大阶段（3-5阶段，仅列阶段名和一句话核心事件）
3. 最终结局方向

只输出JSON，不要解释：
{{
  "core_conflict": "核心冲突描述",
  "stages": [
    {{"name": "阶段名", "core_event": "一句话核心事件"}}
  ],
  "ending_direction": "结局方向",
  "raw_text": "完整纯文本大纲"
}}"""

WIZARD_VOLUMES_PROMPT = """你是一个中文网络小说创作助手。用户正在创作一本{genre}题材的小说。

全书大纲：{outline_context}

请为第一卷生成分卷纲要（控制在250字以内）：
1. 第一卷的标题
2. 第一卷概要（2-3句，描述首卷的核心事件与冲突）
3. 第一卷预计章节数（3-5章）

后续各卷在写作推进时逐步生成。只输出JSON，不要解释：
{{
  "volume": {{
    "title": "第一卷标题",
    "summary": "第一卷概要",
    "chapter_count": 3,
    "key_events": ["核心节点事件1", "核心节点事件2"]
  }},
  "raw_text": "完整纯文本"
}}"""

WIZARD_CHAPTER_OUTLINE_PROMPT = """你是一个中文网络小说创作助手。用户正在创作一本{genre}题材的小说。

全书大纲：{outline_context}
第一卷纲要：{volumes_context}
主角：{character_context}

请为第一卷的第一章生成章节大纲（控制在200字以内）：
1. 第一章标题
2. 核心情节（3-5句，完整描述本章从开头到结尾的主要内容）
3. 建议字数

后续各章在写作推进中逐步生成。只输出JSON，不要解释：
{{
  "chapter": {{
    "title": "第1章 章节标题",
    "summary": "核心情节描述",
    "word_count": 3000
  }},
  "raw_text": "完整纯文本章节大纲"
}}"""

WIZARD_BLUEPRINT_PROMPT = """你是一个中文网络小说创作助手。用户正在创作一本{genre}题材的小说。

全书大纲：{outline_context}
章节大纲：{chapter_outline_context}
主角：{character_context}

请为前三章生成蓝图（控制在400字以内），每章包含：
1. 章节标题
2. 核心情节（2-3句）
3. 字数建议

只输出JSON，不要解释：
{{
  "chapters": [
    {{"title": "第1章标题", "summary": "核心情节", "word_count": 3000}},
    {{"title": "第2章标题", "summary": "核心情节", "word_count": 3000}},
    {{"title": "第3章标题", "summary": "核心情节", "word_count": 3000}}
  ],
  "raw_text": "完整纯文本蓝图"
}}"""

# ═══════════════════════════════════════════
# 追加模式 Prompts 已迁至 wizard_append_save.py（随使用方就近）
# ═══════════════════════════════════════════

# ═══════════════════════════════════════════
# 题材反馈模板
# ═══════════════════════════════════════════

GENRE_FEEDBACK = {
    "仙侠": "仙侠题材，格局可以大一些，修炼体系、飞升、宗门争斗是核心看点。",
    "都市": "都市题材，贴近现实又带超现实元素，建议设定一个清晰的金手指/系统。",
    "玄幻": "玄幻题材，异世界、修炼升级、血脉觉醒，世界观可以放开想象。",
    "科幻": "科幻题材，注意科技设定的自洽性，未来世界或近未来都可以。",
    "悬疑": "悬疑题材，埋线很重要，开头要抓住读者好奇心。",
    "言情": "言情题材，人物关系和情感递进是核心，可以先想好CP人设。",
    "历史": "历史题材，架空或真实历史都可以，注意时代细节的真实感。",
    "军事": "军事题材，建议先有大背景设定，战争/冲突是推动力。",
    "游戏": "游戏题材，系统设定是骨架，升级/打怪/道具要有新意。",
    "末世": "末世题材，生存压力与人性考验是永恒主题。",
    "重生": "重生题材，前世今生的信息差是金手指核心。",
    "穿越": "穿越题材，现代思维与古代/异世界碰撞是看点。",
    "武侠": "武侠题材，江湖恩怨与侠义精神是骨架，武功体系和门派格局要先立住。",
    "灵异": "灵异题材，氛围营造大于惊吓本身，规则设定（什么能做、什么不能碰）要自洽。",
    "同人": "同人题材，尊重原作人设是底线，在原著缝隙里找新的可能性是看点。",
    "轻小说": "轻小说题材，文风轻松、对话驱动，人设萌点和日常互动是核心吸引力。",
    "古言": "古言题材，古代背景下的情感故事，礼仪称谓和时代细节要有古意。",
    "职场": "职场题材，行业生态与人物成长双线并行，专业细节的真实感决定可信度。",
    "电竞": "电竞题材，比赛节奏与战队群像是两大支柱，战术描写要有画面感。",
    "无限流": "无限流题材，副本设计是核心竞争力，规则、奖励与淘汰机制要先定清楚。",
    "系统流": "系统流题材，系统面板与成长曲线是爽点引擎，任务奖励的节奏要勾人。",
    "快穿": "快穿题材，单元剧结构，每个世界一个小目标，主线情感贯穿其中。",
    "甜宠": "甜宠题材，糖点密度是生命线，误会宜短不宜长，双向奔赴最动人。",
    "星际": "星际题材，宇宙尺度下的文明碰撞，科技树与星图版图先搭个大概。",
}


from backend.agents.wizard_append_save import WizardAppendSaveMixin

class WizardAgent(BaseAgent, WizardAppendSaveMixin):
    """创作向导 Agent。
    
    处理多轮创作向导对话，分阶段收集信息并逐步生成世界设定、人物档案、
    全书大纲、分卷纲要、章节大纲和三章蓝图。
    
    阶段流转（初建）：
    ask_genre → generate_world → ask_protagonist → generate_characters 
    → ask_oneliner → generate_outline → generate_volumes → generate_chapter_outlines 
    → generate_blueprint → done

    阶段流转（追加）：
    append_outline → append_volumes → append_chapter_outlines → done
    （每步对话式确认后继续，只往后追加，不修改已写正文的阶段/卷/章）
    """

    agent_id = "wizard"
    agent_name = "创作向导Agent"
    intent_keywords = ["wizard"]

    def execute(self, params: dict, context: dict) -> dict:
        stage = params.get("stage", "ask_genre")
        message = params.get("message", "")
        self.log_event("wizard_stage", {"stage": stage})

        stages = {
            "ask_genre": self._ask_genre,
            "generate_world": self._generate_world,
            "ask_protagonist": self._ask_protagonist,
            "generate_characters": self._generate_characters,
            "ask_oneliner": self._ask_oneliner,
            "generate_outline": self._generate_outline,
            "generate_volumes": self._generate_volumes,
            "generate_chapter_outlines": self._generate_chapter_outlines,
            "generate_blueprint": self._generate_blueprint,
            # ── 追加模式 ──
            "append_outline": self._append_outline,
            "append_volumes": self._append_volumes,
            "append_chapter_outlines": self._append_chapter_outlines,
        }
        
        handler = stages.get(stage)
        if handler:
            return handler(message, context)
        else:
            return {
                "reply": "向导阶段异常，请关闭向导后手动设置。",
                "action": {"type": "wizard_error", "stage": stage},
            }

    # ── Stage 1: 询问题材 ──

    def _ask_genre(self, genre: str, context: dict) -> dict:
        """用户已选择题材，返回确认和下一步引导。"""
        genre = sanitize_light(genre).strip()
        if not genre:
            return {
                "reply": "请选择一个题材：" + " / ".join(GENRE_FEEDBACK.keys()),
                "action": {"type": "wizard_ask_genre"},
            }
        
        feedback = GENRE_FEEDBACK.get(genre, f"好的，{genre}题材，我会据此生成设定。")
        return {
            "reply": f"📌 你选择了 **{genre}** 题材。\n\n{feedback}\n\n下一步我会生成世界观设定，准备好了吗？",
            "data": {"genre": genre},
            "action": {"type": "wizard_stage", "stage": "ask_genre", "genre": genre, "next": "generate_world"},
        }

    # ── Stage 2: 生成世界观 ──

    def _generate_world(self, genre: str, context: dict) -> dict:
        """根据题材生成世界观设定并保存。"""
        genre = sanitize_light(genre).strip()
        
        # 搜索注入：获取该题材的参考信息
        search_context = ""
        try:
            from backend.web_search import search_for_context
            search_context = search_for_context(f"{genre} 小说 世界观设定 力量体系", max_results=2)
        except Exception:
            pass
        
        prompt = WIZARD_WORLD_PROMPT.format(genre=genre)
        if search_context:
            prompt = search_context + "\n\n" + prompt
        
        try:
            raw = call_ai(prompt)
            raw = _clean_ai_output(raw)
            result = json.loads(raw)
            
            world_name = result.get("name", f"{genre}世界")
            world_text = result.get("raw_text", "")
            
            # 保存世界设定
            self._save_world_settings(genre, world_name, result)
            
            reply = f"🌍 **世界观设定已生成**\n\n"
            reply += f"**{world_name}**\n"
            if result.get("era"):
                reply += f"时代：{result['era']}\n"
            if result.get("power_system"):
                reply += "力量体系：\n"
                for ps in result["power_system"]:
                    reply += f"  • {ps}\n"
            if result.get("unique_features"):
                reply += "独特设定：\n"
                for uf in result["unique_features"]:
                    reply += f"  • {uf}\n"
            reply += "\n如果你觉得哪里需要调整，直接告诉我。接下来我们设主角？"
            
            return {
                "reply": reply,
                "data": {"world_name": world_name, "world_settings": result},
                "action": {
                    "type": "wizard_stage", 
                    "stage": "generate_world",
                    "next": "ask_protagonist",
                    "world_name": world_name,
                },
            }
        except Exception as e:
            logger.error("[WizardAgent] 生成世界观失败: %s", e, exc_info=True)
            return {
                "reply": f"世界观生成失败：{e}。请重试，或者告诉我你的世界设定想法。",
                "action": {"type": "wizard_stage", "stage": "generate_world", "retry": True},
            }

    # ── Stage 3: 询问主角 ──

    def _ask_protagonist(self, message: str, context: dict) -> dict:
        """处理主角信息，返回确认。"""
        info = sanitize_light(message).strip()
        if not info or len(info) < 2:
            return {
                "reply": "主角叫什么名字？年龄？性格？简单介绍一下吧。",
                "action": {"type": "wizard_ask_protagonist"},
            }
        
        return {
            "reply": f"了解！主角：{info}\n\n接下来我根据世界观和主角信息生成详细人物档案。",
            "data": {"protagonist_info": info},
            "action": {"type": "wizard_stage", "stage": "ask_protagonist", "protagonist_info": info, "next": "generate_characters"},
        }

    # ── Stage 4: 生成人物档案 ──

    def _generate_characters(self, protagonist_info: str, context: dict) -> dict:
        """根据已有信息生成主角详细档案。"""
        genre = context.get("wizard_genre", "玄幻")
        world_context = context.get("wizard_world_text", "")
        protagonist_info = sanitize_light(protagonist_info).strip()
        
        # 搜索注入：获取该题材主角人设参考
        search_context = ""
        try:
            from backend.web_search import search_for_context
            search_context = search_for_context(f"{genre} 小说 主角 人设 性格", max_results=2)
        except Exception:
            pass
        
        prompt = WIZARD_CHARACTER_PROMPT.format(
            genre=genre,
            world_context=world_context,
            protagonist_info=protagonist_info,
        )
        if search_context:
            prompt = search_context + "\n\n" + prompt
        
        try:
            raw = call_ai(prompt)
            raw = _clean_ai_output(raw)
            result = json.loads(raw)
            
            char_name = result.get("name", "主角")
            
            # 保存角色
            self._save_character(result)
            
            reply = f"👤 **角色档案已生成**\n\n"
            reply += f"**{char_name}**"
            if result.get("age"):
                reply += f"，{result['age']}"
            reply += "\n"
            if result.get("personality"):
                reply += f"性格：{' / '.join(result['personality'])}\n"
            if result.get("background"):
                reply += f"背景：{result['background']}\n"
            if result.get("goal"):
                reply += f"目标：{result['goal']}\n"
            reply += "\n需要修改的话直接说。下一步，一句话概括你的故事主线？"
            
            return {
                "reply": reply,
                "data": {"character_name": char_name, "character_info": result},
                "action": {
                    "type": "wizard_stage",
                    "stage": "generate_characters",
                    "next": "ask_oneliner",
                    "character_name": char_name,
                },
            }
        except Exception as e:
            logger.error("[WizardAgent] 生成角色失败: %s", e, exc_info=True)
            return {
                "reply": f"角色生成失败：{e}。请手动补充主角信息。",
                "action": {"type": "wizard_stage", "stage": "generate_characters", "retry": True},
            }

    # ── Stage 5: 询问一句话剧情 ──

    def _ask_oneliner(self, message: str, context: dict) -> dict:
        """处理一句话主线。"""
        oneliner = sanitize_light(message).strip()
        if not oneliner or len(oneliner) < 5:
            return {
                "reply": "用一句话概括你的故事主线？比如：「废材少年捡到上古神器，一路逆袭踏上修仙巅峰」。",
                "action": {"type": "wizard_ask_oneliner"},
            }
        
        return {
            "reply": f'主线："{oneliner}" —— 收到！接下来生成全书大纲。',
            "data": {"oneliner": oneliner},
            "action": {"type": "wizard_stage", "stage": "ask_oneliner", "oneliner": oneliner, "next": "generate_outline"},
        }

    # ── Stage 6: 生成全书大纲 ──

    def _generate_outline(self, oneliner: str, context: dict) -> dict:
        """根据已有信息生成全书大纲（结构层面，不含卷/章）。"""
        genre = context.get("wizard_genre", "玄幻")
        world_context = context.get("wizard_world_text", "")
        character_context = context.get("wizard_char_text", "")
        oneliner = sanitize_light(oneliner).strip()
        
        # 搜索注入：获取该题材大纲套路参考
        search_context = ""
        try:
            from backend.web_search import search_for_context
            search_context = search_for_context(f"{genre} 网文 故事大纲 情节设计", max_results=2)
        except Exception:
            pass
        
        prompt = WIZARD_OUTLINE_PROMPT.format(
            genre=genre,
            world_context=world_context,
            character_context=character_context,
            oneliner=oneliner,
        )
        if search_context:
            prompt = search_context + "\n\n" + prompt
        
        try:
            raw = call_ai(prompt)
            raw = _clean_ai_output(raw)
            result = json.loads(raw)
            
            stages = result.get("stages", [])
            conflict = result.get("core_conflict", "")
            ending = result.get("ending_direction", "")
            raw_text = result.get("raw_text", "")
            
            # 保存大纲
            self._save_outline(stages, conflict, ending, raw_text)
            
            reply = f"📖 **全书大纲已生成**\n\n"
            if conflict:
                reply += f"核心冲突：{conflict}\n\n"
            reply += "**故事分阶段**：\n"
            for i, s in enumerate(stages):
                reply += f"  {i+1}. {s.get('name', '')} — {s.get('core_event', '')}\n"
            if ending:
                reply += f"\n结局方向：{ending}\n"
            reply += "\n如果结构需要调整，现在就可以说。接下来生成分卷纲要。"
            
            return {
                "reply": reply,
                "data": {"stages": stages, "conflict": conflict, "ending": ending, "outline_text": raw_text},
                "action": {
                    "type": "wizard_stage",
                    "stage": "generate_outline",
                    "next": "generate_volumes",
                },
            }
        except Exception as e:
            logger.error("[WizardAgent] 生成大纲失败: %s", e, exc_info=True)
            return {
                "reply": f"大纲生成失败：{e}。请重试。",
                "action": {"type": "wizard_stage", "stage": "generate_outline", "retry": True},
            }

    # ── Stage 7: 生成分卷纲要（仅第一卷）──

    def _generate_volumes(self, message: str, context: dict) -> dict:
        """根据全书大纲生成第一卷的分卷纲要（后续卷逐步生成）。"""
        genre = context.get("wizard_genre", "玄幻")
        outline_context = context.get("wizard_outline_text", "")
        
        prompt = WIZARD_VOLUMES_PROMPT.format(
            genre=genre,
            outline_context=outline_context,
        )
        
        try:
            raw = call_ai(prompt)
            raw = _clean_ai_output(raw)
            result = json.loads(raw)
            
            volume = result.get("volume", {})
            raw_text = result.get("raw_text", "")
            
            reply = f"📚 **第一卷纲要已生成**\n\n"
            reply += f"**{volume.get('title', '第一卷')}**\n"
            reply += f"  {volume.get('summary', '')}\n"
            if volume.get("key_events"):
                reply += "  关键节点：\n"
                for evt in volume["key_events"]:
                    reply += f"    · {evt}\n"
            reply += f"\n预计 {volume.get('chapter_count', 3)} 章。后续各卷在写作推进时逐步生成。\n"
            reply += "接下来生成第一章大纲。"
            
            # 保存
            self._save_volumes(volume)
            
            return {
                "reply": reply,
                "data": {"volume": volume, "volumes_text": raw_text},
                "action": {
                    "type": "wizard_stage",
                    "stage": "generate_volumes",
                    "next": "generate_chapter_outlines",
                },
            }
        except Exception as e:
            logger.error("[WizardAgent] 生成分卷失败: %s", e, exc_info=True)
            return {
                "reply": f"分卷生成失败：{e}。请重试。",
                "action": {"type": "wizard_stage", "stage": "generate_volumes", "retry": True},
            }

    # ── Stage 8: 生成章节大纲（仅第一章）──

    def _generate_chapter_outlines(self, message: str, context: dict) -> dict:
        """根据全书大纲和第一卷纲要生成第一章的章节大纲（后续章逐步生成）。"""
        genre = context.get("wizard_genre", "玄幻")
        outline_context = context.get("wizard_outline_text", "")
        volumes_context = context.get("wizard_volumes_text", "")
        character_context = context.get("wizard_char_text", "")
        
        prompt = WIZARD_CHAPTER_OUTLINE_PROMPT.format(
            genre=genre,
            outline_context=outline_context,
            volumes_context=volumes_context,
            character_context=character_context,
        )
        
        try:
            raw = call_ai(prompt)
            raw = _clean_ai_output(raw)
            result = json.loads(raw)
            
            chapter = result.get("chapter", {})
            raw_text = result.get("raw_text", "")
            
            reply = f"📝 **第一章大纲已生成**\n\n"
            reply += f"**{chapter.get('title', '第1章')}**（建议{chapter.get('word_count', 3000)}字）\n"
            reply += f"  {chapter.get('summary', '')}\n"
            reply += "\n后续章节在写作推进中逐步生成。接下来生成开篇写作蓝图。"
            
            self._save_chapter_outlines(chapter)
            
            return {
                "reply": reply,
                "data": {"chapter": chapter, "chapter_outline_text": raw_text},
                "action": {
                    "type": "wizard_stage",
                    "stage": "generate_chapter_outlines",
                    "next": "generate_blueprint",
                },
            }
        except Exception as e:
            logger.error("[WizardAgent] 生成章节大纲失败: %s", e, exc_info=True)
            return {
                "reply": f"章节大纲生成失败：{e}。请重试。",
                "action": {"type": "wizard_stage", "stage": "generate_chapter_outlines", "retry": True},
            }

    # ── Stage 9: 生成三章蓝图 ──

    def _generate_blueprint(self, message: str, context: dict) -> dict:
        """生成前三章蓝图，完成向导。"""
        genre = context.get("wizard_genre", "玄幻")
        outline_context = context.get("wizard_outline_text", "")
        chapter_outline_context = context.get("wizard_chapter_outline_text", "")
        character_context = context.get("wizard_char_text", "")
        
        prompt = WIZARD_BLUEPRINT_PROMPT.format(
            genre=genre,
            outline_context=outline_context,
            chapter_outline_context=chapter_outline_context,
            character_context=character_context,
        )
        
        try:
            raw = call_ai(prompt)
            raw = _clean_ai_output(raw)
            result = json.loads(raw)
            
            chapters = result.get("chapters", [])
            
            # 保存蓝图
            self._save_blueprint(chapters)
            
            reply = "📝 **前三章蓝图已生成**\n\n"
            for i, ch in enumerate(chapters):
                reply += f"**{ch.get('title', f'第{i+1}章')}**（建议{ch.get('word_count', 3000)}字）\n"
                reply += f"  {ch.get('summary', '')}\n\n"
            reply += "🎉 **创作准备完成！**\n"
            reply += "现在你已经有：世界观设定、人物档案、全书大纲、前三章蓝图。\n"
            reply += "点击「开始写作」进入编辑器，或者继续在对话框里调整设定。\n"
            reply += "大纲树在左侧常驻，点任意节点可以展开编辑面板。"
            
            return {
                "reply": reply,
                "data": {"chapters": chapters},
                "action": {
                    "type": "wizard_complete",
                    "stage": "generate_blueprint",
                    "chapter_count": len(chapters),
                    "chapters": chapters,
                },
            }
        except Exception as e:
            logger.error("[WizardAgent] 生成蓝图失败: %s", e, exc_info=True)
            return {
                "reply": f"蓝图生成失败：{e}。但向导已完成，你可以手动规划章节后开始写作。",
                "action": {"type": "wizard_complete", "stage": "generate_blueprint", "partial": True},
            }

    # ── Stage A1: 延长故事 - 追加大纲阶段 ──

            logger.warning("[WizardAgent] 保存追加章节大纲失败: %s", e)

    def _get_volume_count(self) -> int:
        """获取当前项目已有的分卷数。"""
        try:
            if state.project and state.project.get("volumes"):
                return len(state.project["volumes"])
        except Exception:
            pass
        return 0

    def _get_chapter_count(self, volume_index: int) -> int:
        """获取指定卷下已有的章节数。"""
        try:
            if state.project and state.project.get("volumes"):
                volumes = state.project["volumes"]
                if volume_index < len(volumes):
                    vol = volumes[volume_index]
                    if vol and vol.get("chapters"):
                        return len(vol["chapters"])
        except Exception:
            pass
        return 0

    # ── 内部保存方法 ──

