# -*- coding: utf-8 -*-
"""Wizard 追加模式与保存方法（从 wizard_agent.py 拆分）"""
import json, logging

from backend.agents.dispatcher import _api_post, _clean_ai_output, _get_base_url
from backend.agents.intent_classifier import call_ai
from backend.services.project_service import state

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 追加模式 Prompts（延长故事，从 wizard_agent.py 迁入）
# ═══════════════════════════════════════════

WIZARD_APPEND_OUTLINE_PROMPT = """你是一个中文网络小说创作助手。用户正在创作一本{genre}题材的小说。

已有全书大纲阶段：
{existing_outline}

用户希望延长故事，需要追加一个新阶段。请输出一个新阶段（控制在200字以内）：
1. 新阶段名称
2. 一句话核心事件（这个阶段的主要推动力是什么）
3. 引入的新冲突或转折

新阶段必须延续已有故事的逻辑，不能推翻前文。只输出JSON，不要解释：
{{
  "stage": {{
    "name": "新阶段名",
    "core_event": "一句话核心事件",
    "new_conflict": "新冲突/转折描述"
  }},
  "raw_text": "完整纯文本"
}}"""

WIZARD_APPEND_VOLUMES_PROMPT = """你是一个中文网络小说创作助手。用户正在创作一本{genre}题材的小说。

全书大纲（含新增阶段）：
{outline_context}

已有分卷列表：
{existing_volumes}

请为新增阶段 "{new_stage_name}" 生成第一卷纲要（控制在250字以内）：
1. 该卷标题
2. 卷概要（2-3句，与新增阶段"{new_stage_name}"关联）
3. 预计章节数（3-5章）
4. 关键节点事件

只输出JSON，不要解释：
{{
  "volume": {{
    "title": "第N卷 卷标题",
    "summary": "卷概要",
    "chapter_count": 3,
    "key_events": ["节点事件1", "节点事件2"]
  }},
  "raw_text": "完整纯文本"
}}"""

WIZARD_APPEND_CHAPTER_OUTLINE_PROMPT = """你是一个中文网络小说创作助手。用户正在创作一本{genre}题材的小说。

全书大纲：{outline_context}
当前卷纲要：{volumes_context}
主角：{character_context}

请为当前卷的第一章生成章节大纲（控制在200字以内）：
1. 第一章标题
2. 核心情节（3-5句）

只输出JSON，不要解释：
{{
  "chapter": {{
    "title": "第X章 章节标题",
    "summary": "核心情节描述",
    "word_count": 3000
  }},
  "raw_text": "完整纯文本章节大纲"
}}"""


class WizardAppendSaveMixin:
    """提供追加模式（延长故事）与数据保存方法"""

    def _append_outline(self, message: str, context: dict) -> dict:
        """在已有大纲末尾追加一个新阶段。"""
        genre = context.get("wizard_genre", "玄幻")
        existing_outline = context.get("wizard_outline_text", "")

        if not existing_outline:
            return {
                "reply": "未找到已有大纲，请先完成初建向导。",
                "action": {"type": "wizard_error", "stage": "append_outline"},
            }

        prompt = WIZARD_APPEND_OUTLINE_PROMPT.format(
            genre=genre,
            existing_outline=existing_outline,
        )

        try:
            raw = call_ai(prompt)
            raw = _clean_ai_output(raw)
            result = json.loads(raw)

            new_stage = result.get("stage", {})
            raw_text = result.get("raw_text", "")

            # 构建包含新阶段的完整大纲文本
            new_full_outline = existing_outline.strip() + "\n\n【" + new_stage.get("name", "新阶段") + "】\n" + raw_text

            # 保存新阶段到全书大纲
            self._save_append_stage(new_stage, raw_text)

            reply = f"📌 **已追加新阶段：{new_stage.get('name', '新阶段')}**\n\n"
            reply += f"核心事件：{new_stage.get('core_event', '（待定）')}\n"
            reply += f"新冲突：{new_stage.get('new_conflict', '（待定）')}\n"
            reply += "\n接下来为这个阶段生成分卷纲要。准备好了吗？"

            return {
                "reply": reply,
                "data": {"new_stage": new_stage, "outline_text": new_full_outline},
                "action": {
                    "type": "wizard_stage",
                    "stage": "append_outline",
                    "next": "append_volumes",
                    "new_stage": new_stage,
                },
            }
        except Exception as e:
            logger.error("[WizardAgent] 追加大纲阶段失败: %s", e, exc_info=True)
            return {
                "reply": f"追加大纲失败：{e}。请重试。",
                "action": {"type": "wizard_stage", "stage": "append_outline", "retry": True},
            }

    # ── Stage A2: 延长故事 - 生成新卷 ──

    def _append_volumes(self, message: str, context: dict) -> dict:
        """为新追加的大纲阶段生成第一卷纲要。"""
        genre = context.get("wizard_genre", "玄幻")
        outline_context = context.get("wizard_outline_text", "")
        existing_volumes = context.get("wizard_volumes_text", "（暂无分卷）")

        # 从message或context获取新阶段名（前端可能在message里传递）
        new_stage_name = (context.get("wizard_append_stage", {}).get("name", "") if isinstance(context.get("wizard_append_stage"), dict) else "") or \
                         message.strip() or \
                         "新阶段"

        prompt = WIZARD_APPEND_VOLUMES_PROMPT.format(
            genre=genre,
            outline_context=outline_context,
            existing_volumes=existing_volumes,
            new_stage_name=new_stage_name,
        )

        try:
            raw = call_ai(prompt)
            raw = _clean_ai_output(raw)
            result = json.loads(raw)

            volume = result.get("volume", {})
            raw_text = result.get("raw_text", "")

            # 获取当前卷数用于设定序号
            vol_index = self._get_volume_count()

            reply = f"📚 **新卷纲要已生成**\n\n"
            reply += f"**{volume.get('title', '第N卷')}**\n"
            reply += f"概要：{volume.get('summary', '')}\n"
            reply += f"预计 {volume.get('chapter_count', 3)} 章。接下来生成第一章大纲。\n"

            self._save_append_volumes(volume, vol_index)

            return {
                "reply": reply,
                "data": {"volume": volume, "volumes_text": raw_text, "volume_index": vol_index},
                "action": {
                    "type": "wizard_stage",
                    "stage": "append_volumes",
                    "next": "append_chapter_outlines",
                },
            }
        except Exception as e:
            logger.error("[WizardAgent] 追加分卷失败: %s", e, exc_info=True)
            return {
                "reply": f"追加分卷失败：{e}。请重试。",
                "action": {"type": "wizard_stage", "stage": "append_volumes", "retry": True},
            }

    # ── Stage A3: 延长故事 - 生成章节大纲 ──

    def _append_chapter_outlines(self, message: str, context: dict) -> dict:
        """为新追加的卷生成第一章大纲。"""
        genre = context.get("wizard_genre", "玄幻")
        outline_context = context.get("wizard_outline_text", "")
        volumes_context = context.get("wizard_volumes_text", "")
        character_context = context.get("wizard_char_text", "")

        prompt = WIZARD_APPEND_CHAPTER_OUTLINE_PROMPT.format(
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

            # 防御式获取卷索引：优先从 context，否则用已有卷数-1（刚追加的卷）
            vol_index = context.get("wizard_append_volume_index")
            if vol_index is None:
                vol_index = max(0, self._get_volume_count() - 1)
            ch_index = self._get_chapter_count(vol_index)

            reply = f"📝 **新章节大纲已生成**\n\n"
            reply += f"**{chapter.get('title', '新章')}**（建议{chapter.get('word_count', 3000)}字）\n"
            reply += f"  {chapter.get('summary', '')}\n"
            reply += "\n后续章节在写作推进中逐步生成。延长故事准备完成。"

            self._save_append_chapter(chapter, vol_index, ch_index)

            return {
                "reply": reply,
                "data": {"chapter": chapter},
                "action": {
                    "type": "wizard_complete",
                    "stage": "append_chapter_outlines",
                    "chapter": chapter,
                },
            }
        except Exception as e:
            logger.error("[WizardAgent] 追加章节大纲失败: %s", e, exc_info=True)
            return {
                "reply": f"追加章节大纲失败：{e}。但追加向导已完成。",
                "action": {
                    "type": "wizard_complete",
                    "stage": "append_chapter_outlines",
                    "partial": True,
                },
            }

    # ── 追加模式保存方法 ──

    def _save_append_stage(self, new_stage: dict, raw_text: str) -> None:
        """将新阶段追加写入全书大纲。"""
        try:
            base_url = _get_base_url()
            stage_name = new_stage.get("name", "新阶段")
            core_event = new_stage.get("core_event", "")

            # 读取当前大纲，拼接新阶段后写回
            if state.project:
                current_outline = state.project.get("outline", "")
                combined = current_outline.rstrip()
                if combined and not combined.endswith("\n"):
                    combined += "\n"
                combined += f"\n\n【{stage_name}】\n{raw_text or core_event or ''}"

                _api_post(
                    base_url + "/api/project/settings",
                    {
                        "genre": state.project.get("genre", ""),
                        "title": state.project.get("title", ""),
                        "outline": combined,
                    },
                    timeout=10,
                )
            logger.info("[WizardAgent] 新阶段「%s」已追加到全书大纲", stage_name)
        except Exception as e:
            logger.warning("[WizardAgent] 保存追加阶段失败: %s", e)

    def _save_append_volumes(self, volume: dict, vol_index: int) -> None:
        """保存追加模式的新卷纲要。"""
        try:
            base_url = _get_base_url()
            _api_post(
                base_url + "/api/project/volumes/add",
                {
                    "title": volume.get("title", f"第{vol_index+1}卷"),
                    "summary": volume.get("summary", ""),
                    "key_events": json.dumps(volume.get("key_events", [])),
                    "chapter_count": volume.get("chapter_count", 3),
                    "index": vol_index,
                },
                timeout=10,
            )
            logger.info("[WizardAgent] 追加分卷「%s」已保存（索引 %s）", volume.get("title"), vol_index)
        except Exception as e:
            logger.warning("[WizardAgent] 保存追加分卷失败: %s", e)

    def _save_append_chapter(self, chapter: dict, vol_index: int, ch_index: int) -> None:
        """保存追加模式的章节大纲。"""
        try:
            base_url = _get_base_url()
            _api_post(
                base_url + "/api/project/chapters/outline",
                {
                    "title": chapter.get("title", f"第{ch_index+1}章"),
                    "summary": chapter.get("summary", ""),
                    "word_count_target": chapter.get("word_count", 3000),
                    "index": ch_index,
                    "volume_index": vol_index,
                },
                timeout=10,
            )
            logger.info("[WizardAgent] 追加章节大纲已保存（卷%s章%s）", vol_index, ch_index)
        except Exception as e:
            logger.warning("[WizardAgent] 保存追加章节大纲失败: %s", e)

    def _save_world_settings(self, genre: str, world_name: str, data: dict) -> None:
        """保存世界观设定到项目。"""
        try:
            base_url = _get_base_url()
            
            # 保存叙事风格/题材
            _api_post(
                base_url + "/api/project/settings",
                {"genre": genre, "title": state.project.get("title", "") if state.project else ""},
                timeout=10,
            )
            
            # 保存世界设定文本
            raw_text = data.get("raw_text", "")
            if raw_text and state.project:
                # 用 world_settings 接口保存
                _api_post(
                    base_url + "/api/world/settings",
                    {
                        "name": world_name,
                        "era": data.get("era", ""),
                        "power_system": json.dumps(data.get("power_system", [])),
                        "unique_features": json.dumps(data.get("unique_features", [])),
                        "raw_text": raw_text,
                    },
                    timeout=10,
                )
            logger.info("[WizardAgent] 世界观设定已保存: %s", world_name)
        except Exception as e:
            logger.warning("[WizardAgent] 保存世界观失败: %s", e)

    def _save_character(self, data: dict) -> None:
        """保存角色档案。"""
        try:
            base_url = _get_base_url()
            char_name = data.get("name", "新角色")
            
            _api_post(
                base_url + "/api/project/characters/add",
                {
                    "name": char_name,
                    "age": data.get("age", ""),
                    "appearance": data.get("appearance", ""),
                    "personality": ", ".join(data.get("personality", [])),
                    "background": data.get("background", ""),
                    "goal": data.get("goal", ""),
                },
                timeout=10,
            )
            logger.info("[WizardAgent] 角色已保存: %s", char_name)
        except Exception as e:
            logger.warning("[WizardAgent] 保存角色失败: %s", e)

    def _save_outline(self, stages: list, conflict: str, ending: str, raw_text: str) -> None:
        """保存全书大纲。"""
        try:
            base_url = _get_base_url()
            _api_post(
                base_url + "/api/project/settings",
                {"outline": raw_text},
                timeout=10,
            )
            logger.info("[WizardAgent] 全书大纲已保存")
        except Exception as e:
            logger.warning("[WizardAgent] 保存大纲失败: %s", e)

    def _save_volumes(self, volume: dict) -> None:
        """保存第一卷纲要（后续卷在写作推进中添加）。"""
        try:
            base_url = _get_base_url()
            _api_post(
                base_url + "/api/project/volumes/add",
                {
                    "title": volume.get("title", "第一卷"),
                    "summary": volume.get("summary", ""),
                    "key_events": json.dumps(volume.get("key_events", [])),
                    "chapter_count": volume.get("chapter_count", 3),
                    "index": 0,
                },
                timeout=10,
            )
            logger.info("[WizardAgent] 第一卷纲要已保存")
        except Exception as e:
            logger.warning("[WizardAgent] 保存分卷失败: %s", e)

    def _save_chapter_outlines(self, chapter: dict) -> None:
        """保存第一章大纲（后续章节在写作推进中添加）。"""
        try:
            base_url = _get_base_url()
            _api_post(
                base_url + "/api/project/chapters/outline",
                {
                    "title": chapter.get("title", "第1章"),
                    "summary": chapter.get("summary", ""),
                    "word_count_target": chapter.get("word_count", 3000),
                    "index": 0,
                    "volume_index": 0,
                },
                timeout=10,
            )
            logger.info("[WizardAgent] 第一章大纲已保存")
        except Exception as e:
            logger.warning("[WizardAgent] 保存章节大纲失败: %s", e)

    def _save_blueprint(self, chapters: list) -> None:
        """保存前三章蓝图（作为章节大纲）。"""
        try:
            base_url = _get_base_url()
            for i, ch in enumerate(chapters):
                _api_post(
                    base_url + "/api/project/chapters/outline",
                    {
                        "title": ch.get("title", f"第{i+1}章"),
                        "summary": ch.get("summary", ""),
                        "word_count_target": ch.get("word_count", 3000),
                        "index": i,
                    },
                    timeout=10,
                )
            logger.info("[WizardAgent] 三章蓝图已保存")
        except Exception as e:
            logger.warning("[WizardAgent] 保存蓝图失败: %s", e)
