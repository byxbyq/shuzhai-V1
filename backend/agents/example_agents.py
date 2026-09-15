# -*- coding: utf-8 -*-
"""
书斋 V65 - 示例 Agent 实现
从 dispatcher.py 的 if/elif 链中提取意图处理逻辑，
封装为独立的 Agent 子类。每个 Agent 继承 BaseAgent，
实现 execute() 方法。

这是渐进式重构的第一步：先提取 5 个代表性 Agent 作为示例，
后续可逐步将其余意图也迁移为 Agent。
"""

import json, re
import logging

from backend.agents.base_agent import BaseAgent
from backend.agents.dispatcher import (
    _resolve_chapter_index,
    _get_chapter_content,
    _api_get,
    _api_post,
    _get_base_url,
)
from backend.services.project_service import state

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 1. OutlineAgent - 大纲生成相关意图
# ═══════════════════════════════════════════════════════════════

class OutlineAgent(BaseAgent):
    """处理大纲生成相关意图：
    - generate_outline: 生成单章大纲
    - generate_all_outlines: 生成全部章节大纲
    """

    agent_id = "outline"
    agent_name = "大纲Agent"
    intent_keywords = ["generate_outline", "generate_all_outlines"]

    def execute(self, params: dict, context: dict) -> dict:
        intent = params.get("_intent", "")
        if intent == "generate_outline":
            return self._generate_outline(params, context)
        elif intent == "generate_all_outlines":
            return self._generate_all_outlines(params, context)
        else:
            return {"reply": "大纲Agent: 未识别的子意图"}

    def _generate_outline(self, params: dict, context: dict) -> dict:
        """生成全书大纲（已融合进章节大纲）"""
        self.log_event("generate_outline", {"params": params})
        return {
            "reply": "全书大纲功能已融合进章节大纲（步骤3）。请直接到步骤3使用「AI生成」或「一键生成全部」来创建章节蓝图。第一章蓝图会自动产出故事总览。",
        }

    def _generate_all_outlines(self, params: dict, context: dict) -> dict:
        """生成全部章节大纲"""
        self.log_event("generate_all_outlines", {"params": params})
        try:
            odata = _api_post(
                _get_base_url() + "/api/generate/all-chapter-outlines",
                {},
                timeout=600,
            )
            if odata.get("ok"):
                results_list = odata.get("results", [])
                success_count = sum(1 for r in results_list if r.get("ok"))
                return {
                    "reply": f"全部章节大纲已生成（{success_count}/{len(results_list)}章成功）。接下来可以'全部生成'正文。",
                    "action": {"type": "reload_outline"},
                }
            else:
                return {"reply": f"章节大纲生成失败：{odata.get('error', '')}"}
        except Exception as e:
            logger.error("[OutlineAgent] 生成全部章节大纲出错: %s", e, exc_info=True)
            return {"reply": f"章节大纲生成出错：{e}"}


# ═══════════════════════════════════════════════════════════════
# 2. ChapterAgent - 章节生成/续写相关意图
# ═══════════════════════════════════════════════════════════════

class ChapterAgent(BaseAgent):
    """处理章节生成/续写/优化相关意图：
    - continue_writing: 续写章节
    - generate_chapter: 生成章节
    - optimize_text: 优化文字
    - generate_all_chapters: 生成全部章节正文
    """

    agent_id = "chapter"
    agent_name = "章节Agent"
    intent_keywords = [
        "continue_writing", "generate_chapter", "optimize_text",
        "generate_all_chapters",
    ]

    def execute(self, params: dict, context: dict) -> dict:
        intent = params.get("_intent", "")
        if intent == "generate_all_chapters":
            return self._generate_all_chapters(params, context)
        else:
            return self._generate_single(params, context, intent)

    def _generate_single(self, params: dict, context: dict, intent: str) -> dict:
        """续写 / 生成 / 优化 单章"""
        idx = _resolve_chapter_index(params, context)
        action_map = {
            "continue_writing": "continue",
            "generate_chapter": "generate",
            "optimize_text": "optimize",
        }
        action_type = action_map.get(intent, "generate")
        self.log_event("generate_single", {"intent": intent, "chapter_index": idx})
        return {
            "reply": params.get("reply", f"好的，我来{action_type}第{idx+1}章内容。"),
            "action": {
                "type": action_type,
                "chapter_index": idx,
                "extra": params.get("message", ""),
            },
        }

    def _generate_all_chapters(self, params: dict, context: dict) -> dict:
        """生成全部章节正文"""
        self.log_event("generate_all_chapters", {})
        try:
            odata = _api_post(
                _get_base_url() + "/api/generate/all-chapters",
                {},
                timeout=900,
            )
            if odata.get("ok"):
                results_list = odata.get("results", [])
                success_count = sum(1 for r in results_list if r.get("ok"))
                total_words = sum(
                    r.get("word_count", 0) for r in results_list if r.get("ok")
                )
                return {
                    "reply": f"全部正文已生成（{success_count}/{len(results_list)}章成功，共{total_words}字）。可以让我'导出txt'或'检查连贯性'。",
                    "action": {"type": "reload_chapters"},
                }
            else:
                return {"reply": f"正文生成失败：{odata.get('error', '')}"}
        except Exception as e:
            logger.error("[ChapterAgent] 生成全部正文出错: %s", e, exc_info=True)
            return {"reply": f"正文生成出错：{e}"}


# ═══════════════════════════════════════════════════════════════
# 3. ValidateAgent - 校验/检查相关意图
# ═══════════════════════════════════════════════════════════════

class ValidateAgent(BaseAgent):
    """处理校验/检查相关意图：
    - check_continuity: 连贯性检查
    - check_completeness: 完整性检查
    - check_drift / check_style: 偏差/风格检查
    - check_all: 全面检查
    - check_batch: 批量检查
    """

    agent_id = "validate"
    agent_name = "校验Agent"
    intent_keywords = [
        "check_continuity", "check_completeness",
        "check_drift", "check_style",
        "check_all", "check_batch",
    ]

    def execute(self, params: dict, context: dict) -> dict:
        intent = params.get("_intent", "")
        self.log_event("validate", {"intent": intent})

        if intent == "check_continuity":
            return self._check_continuity(params, context)
        elif intent == "check_completeness":
            return self._check_completeness(params, context)
        elif intent in ("check_drift", "check_style"):
            return self._check_drift_style(params, context, intent)
        elif intent == "check_all":
            return self._check_all(params, context)
        elif intent == "check_batch":
            return self._check_batch(params, context)
        else:
            return {"reply": "校验Agent: 未识别的子意图"}

    def _check_continuity(self, params: dict, context: dict) -> dict:
        """检查章节连贯性"""
        idx = _resolve_chapter_index(params, context)
        if idx == 0:
            return {"reply": "第1章是开头，没有前一章可对比。试试检查第2章及以后的章节连贯性。"}
        chapters = []
        if state.project:
            chapters = state.project.chapters
        if idx >= len(chapters):
            return {"reply": f"当前只有{len(chapters)}章，无法检查第{idx+1}章。"}
        title_a, content_a = _get_chapter_content(idx - 1)
        title_b, content_b = _get_chapter_content(idx)
        if len(content_a) < 100 or len(content_b) < 100:
            return {"reply": f"第{idx}章或第{idx+1}章内容太短（不足100字），无法做连贯性检查。请先确保两章都有内容。"}
        try:
            check_result = _api_post(
                _get_base_url() + "/api/check/continuity",
                {"chapter_a": content_a[:3000], "chapter_b": content_b[:3000], "title_a": title_a, "title_b": title_b},
                timeout=300,
            )
            if check_result.get("ok"):
                r = check_result["result"]
                score = r.get("overall_score", "?")
                level = r.get("overall_level", "")
                dims = r.get("dimensions", {})
                dim_text = ""
                for dim_name, dim_data in dims.items():
                    dim_text += f"  {dim_name}: {dim_data.get('score', '?')}/10 - {dim_data.get('comment', '')[:60]}\n"
                reply = f"第{idx}章->第{idx+1}章连贯性评分：{score}/10（{level}）\n\n维度详情：\n{dim_text}"
                if r.get("gap_points"):
                    reply += f"\n断裂点：{'、'.join(r['gap_points'][:3])}"
                if r.get("suggestions"):
                    reply += f"\n建议：{r['suggestions'][0]}"
                return {
                    "reply": reply,
                    "data": check_result["result"],
                    "action": {"type": "check_result", "check_type": "continuity", "chapter_index": idx, "has_issue": score != "?" and float(score) < 8},
                }
            else:
                return {"reply": f"连贯性检查失败：{check_result.get('error', '未知错误')}"}
        except Exception as e:
            return {"reply": f"连贯性检查出错：{e}"}

    def _check_completeness(self, params: dict, context: dict) -> dict:
        """检查章节完整性"""
        idx = _resolve_chapter_index(params, context)
        title, content = _get_chapter_content(idx)
        if len(content) < 100:
            return {"reply": f"第{idx+1}章内容太短（{len(content)}字），无法检查。"}
        try:
            check_result = _api_post(
                _get_base_url() + "/api/check/completeness",
                {"content": content[:5000], "title": title},
                timeout=300,
            )
            if check_result.get("ok"):
                r = check_result["result"]
                score = r.get("overall_score", "?")
                reply = f"第{idx+1}章《{title}》完整性评分：{score}/10（{r.get('overall_level', '')}）\n{r.get('summary', '')}"
                if r.get("suggestions"):
                    reply += f"\n建议：{r['suggestions'][0]}"
                return {
                    "reply": reply,
                    "data": check_result["result"],
                    "action": {"type": "check_result", "check_type": "completeness", "chapter_index": idx, "has_issue": score != "?" and float(score) < 8},
                }
            else:
                return {"reply": f"完整性检查失败：{check_result.get('error', '')}"}
        except Exception as e:
            return {"reply": f"完整性检查出错：{e}"}

    def _check_drift_style(self, params: dict, context: dict, intent: str) -> dict:
        """检查偏差或风格"""
        idx = _resolve_chapter_index(params, context)
        title, content = _get_chapter_content(idx)
        if len(content) < 100:
            return {"reply": f"第{idx+1}章内容太短，无法检查。"}
        check_type = "drift" if intent == "check_drift" else "style"
        try:
            check_result = _api_post(
                _get_base_url() + f"/api/validate/{check_type}",
                {"content": content[:5000], "context": {"stage": "content"}, "index": idx},
                timeout=300,
            )
            if check_result.get("ok"):
                check_text = check_result.get("result", "")
                label = "偏差" if check_type == "drift" else "风格"
                return {
                    "reply": f"第{idx+1}章{label}检查结果：\n{check_text[:800]}",
                    "data": {"check_type": check_type, "result": check_text},
                    "action": {"type": "check_result", "check_type": check_type, "chapter_index": idx, "has_issue": True},
                }
            else:
                return {"reply": f"检查失败：{check_result.get('error', '')}"}
        except Exception as e:
            return {"reply": f"检查出错：{e}"}

    def _check_all(self, params: dict, context: dict) -> dict:
        """全面检查"""
        idx = _resolve_chapter_index(params, context)
        title, content = _get_chapter_content(idx)
        if len(content) < 100:
            return {"reply": f"第{idx+1}章内容太短，无法检查。"}
        try:
            check_result = _api_post(
                _get_base_url() + "/api/validate/all",
                {"content": content[:5000], "context": {"stage": "content"}, "index": idx},
                timeout=300,
            )
            if check_result.get("ok"):
                results = check_result.get("results", {})
                text = ""
                for k, v in results.items():
                    vstr = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
                    text += f"【{k}】{vstr[:200]}\n"
                return {
                    "reply": f"第{idx+1}章全面检查结果：\n{text}",
                    "data": check_result,
                }
            else:
                return {"reply": f"检查失败：{check_result.get('error', '')}"}
        except Exception as e:
            return {"reply": f"全面检查出错：{e}"}

    def _check_batch(self, params: dict, context: dict) -> dict:
        """批量检查"""
        try:
            check_result = _api_post(
                _get_base_url() + "/api/validate/batch",
                {"check_types": ["drift", "style"], "chapter_indices": []},
                timeout=600,
            )
            if check_result.get("ok"):
                summary = check_result.get("summary", {})
                results = check_result.get("results", [])
                text = f"批量检查完成：{summary.get('total', 0)}章，发现{summary.get('issues_found', 0)}个问题。\n"
                for ch in results:
                    checks = ch.get("checks", {})
                    has_issue = any(not c.get("ok") for c in checks.values())
                    text += f"  第{ch['chapter_index']+1}章: {'有问题' if has_issue else '通过'}\n"
                return {"reply": text, "data": check_result}
            else:
                return {"reply": f"批量检查失败：{check_result.get('error', '')}"}
        except Exception as e:
            return {"reply": f"批量检查出错：{e}"}


# ═══════════════════════════════════════════════════════════════
# 4. WorldAgent - 世界观设定相关意图
# ═══════════════════════════════════════════════════════════════

class WorldAgent(BaseAgent):
    """处理世界观设定相关意图：
    - get_world: 查看世界观
    - add_world_force: 添加势力
    - add_world_location: 添加地点
    - add_world_item: 添加物品
    - add_setting: 添加设定
    """

    agent_id = "world"
    agent_name = "世界观Agent"
    intent_keywords = [
        "get_world", "add_world_force", "add_world_location",
        "add_world_item", "add_setting", "delete_world_entity",
    ]

    # 世界观添加端点映射
    _WORLD_ENDPOINT_MAP = {
        "add_world_force": "/api/world/force/add",
        "add_world_location": "/api/world/location/add",
        "add_world_item": "/api/world/item/add",
    }

    # 世界观标签映射
    _WORLD_LABEL_MAP = {
        "add_world_force": "势力",
        "add_world_location": "地点",
        "add_world_item": "物品",
    }

    def execute(self, params: dict, context: dict) -> dict:
        intent = params.get("_intent", "")
        self.log_event("world_action", {"intent": intent})

        if intent == "get_world":
            return self._get_world(params, context)
        elif intent in ("add_world_force", "add_world_location", "add_world_item"):
            return self._add_world_element(params, context, intent)
        elif intent == "add_setting":
            return self._add_setting(params, context)
        elif intent == "delete_world_entity":
            return self._delete_world_entity(params, context)
        else:
            return {"reply": "世界观Agent: 未识别的子意图"}

    def _get_world(self, params: dict, context: dict) -> dict:
        """查看世界观设定"""
        try:
            wdata = _api_get(_get_base_url() + "/api/world/", timeout=10)
            if wdata.get("ok"):
                world = wdata.get("world", {})
                forces = world.get("forces", [])
                locations = world.get("locations", [])
                items = world.get("items", [])
                constraints = world.get("hard_constraints", [])
                text = f"世界观设定：\n  势力{len(forces)}个，地点{len(locations)}个，物品{len(items)}个，硬约束{len(constraints)}条\n"
                for f in forces[:5]:
                    text += f"  {f.get('name', '')}: {f.get('description', '')[:40]}\n"
                for l in locations[:5]:
                    text += f"  {l.get('name', '')}: {l.get('description', '')[:40]}\n"
                return {"reply": text, "data": wdata}
            else:
                return {"reply": "暂无世界观数据。"}
        except Exception as e:
            return {"reply": f"获取世界观出错：{e}"}

    def _add_world_element(self, params: dict, context: dict, intent: str) -> dict:
        """添加势力/地点/物品"""
        message = params.get("message", "")
        name = (
            params.get("force_name")
            or params.get("location_name")
            or params.get("item_name")
            or ""
        )
        desc = params.get("description") or message
        body_dict = {"name": name, "description": desc}
        if intent == "add_world_location":
            body_dict["loc_type"] = "other"
        if intent == "add_world_item":
            body_dict["nature"] = "other"
        if intent == "add_world_force":
            body_dict["territory"] = ""
            body_dict["attitude"] = "neutral"
        try:
            rdata = _api_post(
                _get_base_url() + self._WORLD_ENDPOINT_MAP[intent],
                body_dict,
                timeout=10,
            )
            label = self._WORLD_LABEL_MAP[intent]
            return {
                "reply": f"{label}「{name}」已添加" if rdata.get("ok") else f"添加失败：{rdata.get('error', '')}",
            }
        except Exception as e:
            return {"reply": f"添加世界观元素出错：{e}"}

    def _add_setting(self, params: dict, context: dict) -> dict:
        """添加设定文本到世界观"""
        message = params.get("message", "")
        setting_text = params.get("setting_text") or message or ""
        if not setting_text:
            return {"reply": "设定内容为空，请提供设定文本。"}
        try:
            sdata = _api_get(_get_base_url() + "/api/project/settings", timeout=10)
            if not sdata.get("ok"):
                return {"reply": "读取项目设定失败。"}
            world_settings = sdata.get("world_settings", {})
            if "自由设定" not in world_settings:
                world_settings["自由设定"] = ""
            world_settings["自由设定"] += setting_text + "\n"
            rdata = _api_post(
                _get_base_url() + "/api/project/settings",
                {"world_settings": world_settings},
                timeout=10,
            )
            if rdata.get("ok"):
                return {
                    "reply": f"设定已添加到世界观：\n{setting_text[:100]}...",
                    "action": {"type": "reload_settings"},
                }
            else:
                return {"reply": f"保存失败：{rdata.get('error', '')}"}
        except Exception as e:
            return {"reply": f"添加设定出错：{e}"}

    # 元素类型 → (世界观字段名, 中文名)
    _ENTITY_TYPE_MAP = {
        "force": ("forces", "势力"),
        "location": ("locations", "地点"),
        "item": ("items", "物品"),
    }

    def _delete_world_entity(self, params: dict, context: dict) -> dict:
        """删除世界观元素（按类型+名称匹配）"""
        from backend.agents.dispatcher import _api_delete
        etype = (params.get("entity_type") or "").strip().lower()
        ename = (params.get("entity_name") or "").strip()
        if etype not in self._ENTITY_TYPE_MAP:
            return {"reply": "请说清楚删什么类型：势力、地点还是物品，如'删除势力青云门'。"}
        if not ename:
            return {"reply": "请指定要删除的名称，如'删除势力青云门'。"}
        field, label = self._ENTITY_TYPE_MAP[etype]
        try:
            wdata = _api_get(_get_base_url() + "/api/world/", timeout=10)
            if not wdata.get("ok"):
                return {"reply": "读取世界观失败。"}
            entities = wdata.get("world", {}).get(field, [])
            idx = -1
            for i, e in enumerate(entities):
                if e.get("name") == ename:
                    idx = i
                    break
            if idx < 0:
                names = "、".join(e.get("name", "") for e in entities[:10]) or "（暂无）"
                return {"reply": f"找不到{label}「{ename}」。现有{label}：{names}"}
            rdata = _api_delete(_get_base_url() + f"/api/world/{etype}/{idx}", timeout=10)
            if rdata.get("ok"):
                return {
                    "reply": f"已删除{label}「{ename}」。",
                    "action": {"type": "reload_settings"},
                }
            return {"reply": f"删除失败：{rdata.get('error', '')}"}
        except Exception as e:
            return {"reply": f"删除世界观元素出错：{e}"}


# ═══════════════════════════════════════════════════════════════
# 5. CharacterAgent - 人物设定相关意图
# ═══════════════════════════════════════════════════════════════

class CharacterAgent(BaseAgent):
    """处理人物设定相关意图：
    - list_characters: 列出角色
    - add_character: 添加角色
    - get_character_state: 查看角色状态
    - update_character: 更新角色状态
    - generate_characters: 生成人物档案
    - character_chat: 角色对话
    """

    agent_id = "character"
    agent_name = "人物Agent"
    intent_keywords = [
        "list_characters", "add_character", "get_character_state",
        "update_character", "generate_characters", "character_chat",
        "delete_character", "edit_character",
    ]

    def execute(self, params: dict, context: dict) -> dict:
        intent = params.get("_intent", "")
        self.log_event("character_action", {"intent": intent})

        if intent == "list_characters":
            return self._list_characters(params, context)
        elif intent == "add_character":
            return self._add_character(params, context)
        elif intent == "get_character_state":
            return self._get_character_state(params, context)
        elif intent == "update_character":
            return self._update_character(params, context)
        elif intent == "generate_characters":
            return self._generate_characters(params, context)
        elif intent == "character_chat":
            return self._character_chat(params, context)
        elif intent == "delete_character":
            return self._delete_character(params, context)
        elif intent == "edit_character":
            return self._edit_character(params, context)
        else:
            return {"reply": "人物Agent: 未识别的子意图"}

    def _list_characters(self, params: dict, context: dict) -> dict:
        """列出角色"""
        try:
            char_data = _api_get(_get_base_url() + "/api/chat/characters", timeout=10)
            if char_data.get("ok"):
                chars = char_data.get("characters", [])
                if chars:
                    text = "项目角色：\n"
                    for c in chars:
                        text += f"  - {c['name']}（{c.get('role', '')}）- {c.get('description', '')[:40]}\n"
                    return {"reply": text, "data": char_data}
                else:
                    return {"reply": "当前项目没有角色设定。请在设定面板中添加角色。"}
            else:
                return {"reply": "获取角色失败。"}
        except Exception as e:
            return {"reply": f"获取角色失败：{e}"}

    def _add_character(self, params: dict, context: dict) -> dict:
        """添加角色"""
        message = params.get("message", "")
        char_name = params.get("character", "")
        desc = params.get("description", "") or params.get("message", "")
        if not char_name:
            m = re.search(r'(?:添加角色|加角色|新增角色)[：:]\s*(.+?)[，,]', message)
            if m:
                char_name = m.group(1).strip()
            else:
                return {"reply": "请指定角色名，如'添加角色：林墨，28岁程序员'"}
        try:
            if not state.project:
                return {"reply": "请先打开项目。"}
            # 添加到 characters 列表（SQLite 持久化格式）
            state.project.characters.append({
                "name": char_name,
                "identity": desc,
                "faction": "",
                "goal": "",
                "goals": [],
                "appearance": "",
                "personality": "",
                "backstory": "",
                "abilities": "",
                "relationships": {},
                "arc": "",
                "cognitive_boundary": "",
            })
            state.project.save_all()
            return {
                "reply": f"已添加角色「{char_name}」：{desc[:60]}",
                "action": {"type": "reload_settings"},
            }
        except Exception as e:
            return {"reply": f"添加角色失败：{e}"}

    def _delete_character(self, params: dict, context: dict) -> dict:
        """删除角色（按名匹配）"""
        char_name = (params.get("character") or "").strip()
        if not char_name:
            return {"reply": "请指定要删除的角色名，如'删除人物林墨'。"}
        try:
            if not state.project:
                return {"reply": "请先打开项目。"}
            chars = state.project.characters
            for i, ch in enumerate(chars):
                if ch.get("name") == char_name:
                    chars.pop(i)
                    state.project.save_all()
                    return {
                        "reply": f"已删除角色「{char_name}」，剩余{len(chars)}个角色。",
                        "action": {"type": "reload_settings"},
                    }
            names = "、".join(c.get("name", "") for c in chars[:10]) or "（暂无角色）"
            return {"reply": f"找不到角色「{char_name}」。现有角色：{names}"}
        except Exception as e:
            return {"reply": f"删除角色失败：{e}"}

    # 中文字段名 → 档案字段 key（LLM 可能返回中文）
    _CHAR_FIELD_ALIASES = {
        "identity": "identity", "身份": "identity",
        "faction": "faction", "阵营": "faction", "定位": "faction",
        "personality": "personality", "性格": "personality",
        "background": "background", "身世": "background", "背景": "background", "身世过往": "background",
        "obsession": "obsession", "执念": "obsession",
        "weakness": "weakness", "软肋": "weakness", "弱点": "weakness",
        "goal": "goal", "目标": "goal",
    }

    def _edit_character(self, params: dict, context: dict) -> dict:
        """修改角色档案字段"""
        char_name = (params.get("character") or "").strip()
        field = (params.get("field") or "").strip()
        value = (params.get("value") or "").strip()
        if not char_name or not field or not value:
            return {"reply": "请说清楚要改谁、改什么、改成什么，如'把林墨的性格改成冷淡寡言'。"}
        field_key = self._CHAR_FIELD_ALIASES.get(field)
        if not field_key:
            return {"reply": f"不支持修改「{field}」字段。可改：身份/阵营/性格/身世/执念/软肋/目标。"}
        field_label = {"identity": "身份", "faction": "阵营", "personality": "性格",
                       "background": "身世", "obsession": "执念", "weakness": "软肋", "goal": "目标"}[field_key]
        try:
            if not state.project:
                return {"reply": "请先打开项目。"}
            for ch in state.project.characters:
                if ch.get("name") == char_name:
                    ch[field_key] = value
                    state.project.save_all()
                    return {
                        "reply": f"已将「{char_name}」的{field_label}改为：{value[:60]}",
                        "action": {"type": "reload_settings"},
                    }
            return {"reply": f"找不到角色「{char_name}」。"}
        except Exception as e:
            return {"reply": f"修改角色失败：{e}"}

    def _get_character_state(self, params: dict, context: dict) -> dict:
        """查看角色状态"""
        try:
            cdata = _api_get(_get_base_url() + "/api/ledger/characters", timeout=10)
            if cdata.get("ok"):
                chars = cdata.get("characters", {})
                text = "角色状态：\n"
                for name, info in chars.items():
                    text += f"  {name}: {json.dumps(info, ensure_ascii=False)[:80]}\n"
                return {"reply": text, "data": cdata}
            else:
                return {"reply": "暂无角色状态数据。"}
        except Exception as e:
            return {"reply": f"获取角色状态出错：{e}"}

    def _update_character(self, params: dict, context: dict) -> dict:
        """更新角色状态"""
        char_name = params.get("character")
        if not char_name:
            return {"reply": "请指定要更新的角色名。"}
        desc = params.get("description") or params.get("message", "")
        try:
            rdata = _api_post(
                _get_base_url() + "/api/ledger/character/update",
                {"name": char_name, "fields": {"last_state": desc}},
                timeout=10,
            )
            return {
                "reply": f"角色{char_name}状态已更新" if rdata.get("ok") else f"更新失败：{rdata.get('error', '')}",
            }
        except Exception as e:
            return {"reply": f"更新角色出错：{e}"}

    def _generate_characters(self, params: dict, context: dict) -> dict:
        """生成人物档案"""
        try:
            odata = _api_post(
                _get_base_url() + "/api/ai/generate-characters",
                {},
                timeout=300,
            )
            if odata.get("ok"):
                chars = odata.get("characters", [])
                char_names = [c.get("name", "") for c in chars]
                return {
                    "reply": f"人物档案已生成（{len(chars)}个角色）：{', '.join(char_names)}",
                    "action": {"type": "reload_settings"},
                }
            else:
                return {"reply": f"人物档案生成失败：{odata.get('error', '')}"}
        except Exception as e:
            return {"reply": f"人物档案生成出错：{e}"}

    def _character_chat(self, params: dict, context: dict) -> dict:
        """角色对话"""
        message = params.get("message", "")
        char_name = params.get("character")
        if not char_name:
            return {"reply": "请指定角色名，比如「让XXX说句话」。或者先说「列出角色」查看可用角色。"}
        try:
            chat_result = _api_post(
                _get_base_url() + "/api/chat/talk",
                {"character": char_name, "message": message, "history": []},
                timeout=300,
            )
            if chat_result.get("ok"):
                return {"reply": f"【{char_name}】{chat_result.get('reply', '')}"}
            else:
                return {"reply": f"角色对话失败：{chat_result.get('error', '')}"}
        except Exception as e:
            return {"reply": f"角色对话出错：{e}"}


# ═══════════════════════════════════════════════════════════════
# 辅助：注册所有示例 Agent
# ═══════════════════════════════════════════════════════════════

def register_all_agents(registry=None):
    """将所有 Agent 注册到注册表中。

    优先从 agent_config.json 动态加载，失败时回退到硬编码列表。

    Args:
        registry: AgentRegistry 实例，如果为 None 则使用全局单例
    """
    if registry is None:
        from backend.agents.agent_registry import get_registry
        registry = get_registry()

    # ── 方式1：从配置动态加载（新机制）──
    try:
        import importlib
        from backend.agents.config_loader import AgentConfig
        cfg = AgentConfig()
        agent_configs = cfg.get_agents()
        if agent_configs:
            all_agents = []
            for agent_cfg in agent_configs:
                try:
                    class_path = agent_cfg["class_path"]
                    parts = class_path.rsplit(".", 1)
                    module = importlib.import_module(parts[0])
                    agent_cls = getattr(module, parts[1])
                    agent_instance = agent_cls()
                    registry.register(agent_instance)
                    all_agents.append(agent_instance)
                except Exception as e:
                    logger.warning("[register_all_agents] 跳过 '%s': %s", agent_cfg.get("id"), e)
            if all_agents:
                logger.info("[register_all_agents] 从配置动态加载了 %d 个 Agent", len(all_agents))
                return all_agents
    except Exception as e:
        logger.warning("[register_all_agents] 从配置加载失败，回退到硬编码: %s", e)

    # ── 方式2：硬编码回退（旧机制，保留向后兼容）──
    logger.info("[register_all_agents] 使用硬编码回退注册 Agent")

    # ── 原始5个 Agent（本文件定义）──
    from backend.agents.example_agents import (
        OutlineAgent, ChapterAgent, ValidateAgent, WorldAgent, CharacterAgent,
    )
    # ── 新迁移的 Agent（独立文件）──
    from backend.agents.project_agent import ProjectAgent
    from backend.agents.chapter_manage_agent import ChapterManageAgent
    from backend.agents.memory_agent import MemoryAgent
    from backend.agents.export_agent import ExportAgent
    from backend.agents.storyboard_agent import StoryboardAgent
    from backend.agents.sync_agent import SyncAgent
    from backend.agents.ai_agent import AIAgent
    from backend.agents.edit_agent import EditAgent
    from backend.agents.wizard_agent import WizardAgent
    from backend.agents.search_agent import SearchAgent
    from backend.agents.navigate_agent import NavigateAgent

    all_agents = [
        OutlineAgent(),
        ChapterAgent(),
        ValidateAgent(),
        WorldAgent(),
        CharacterAgent(),
        ProjectAgent(),
        ChapterManageAgent(),
        MemoryAgent(),
        ExportAgent(),
        StoryboardAgent(),
        SyncAgent(),
        AIAgent(),
        EditAgent(),
        WizardAgent(),
        SearchAgent(),
        NavigateAgent(),
    ]

    for agent in all_agents:
        try:
            registry.register(agent)
        except ValueError:
            # 如果已注册则跳过（幂等注册）
            logger.debug("[register_all_agents] Agent '%s' 已存在，跳过", agent.agent_name)

    return all_agents


# 保留旧函数名兼容
register_example_agents = register_all_agents