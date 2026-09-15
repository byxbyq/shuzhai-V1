# -*- coding: utf-8 -*-
"""
书斋 V66 - 章节管理 Agent
处理章节列表、加载、保存、增删、排序、卷管理意图。
"""

import logging

from backend.agents.base_agent import BaseAgent
from backend.agents.dispatcher import (
    _resolve_chapter_index,
    _get_chapter_content,
)
from backend.services.project_service import state

logger = logging.getLogger(__name__)


class ChapterManageAgent(BaseAgent):
    """处理章节管理相关意图：
    - list_chapters: 列出章节
    - load_chapter: 加载章节内容
    - save_chapter: 保存章节
    - add_chapter: 新建章节
    - delete_chapter: 删除章节
    - rename_chapter: 重命名章节
    - reorder_chapter: 调整章节顺序
    - get_volumes: 列出卷
    - add_volume / delete_volume / rename_volume: 卷增删改
    """

    agent_id = "chapter_manage"
    agent_name = "章节管理Agent"
    intent_keywords = [
        "list_chapters", "load_chapter", "save_chapter",
        "add_chapter", "delete_chapter", "rename_chapter", "reorder_chapter",
        "get_volumes", "add_volume", "delete_volume", "rename_volume",
    ]

    def execute(self, params: dict, context: dict) -> dict:
        intent = params.get("_intent", "")
        self.log_event("chapter_manage_action", {"intent": intent})

        if intent == "list_chapters":
            return self._list_chapters(params, context)
        elif intent == "load_chapter":
            return self._load_chapter(params, context)
        elif intent == "save_chapter":
            return self._save_chapter(params, context)
        elif intent == "add_chapter":
            return self._add_chapter(params, context)
        elif intent == "delete_chapter":
            return self._delete_chapter(params, context)
        elif intent == "rename_chapter":
            return self._rename_chapter(params, context)
        elif intent == "reorder_chapter":
            return self._reorder_chapter(params, context)
        elif intent == "get_volumes":
            return self._get_volumes(params, context)
        elif intent == "add_volume":
            return self._add_volume(params, context)
        elif intent == "delete_volume":
            return self._delete_volume(params, context)
        elif intent == "rename_volume":
            return self._rename_volume(params, context)
        else:
            return {"reply": "章节管理Agent: 未识别的子意图"}

    def _list_chapters(self, params: dict, context: dict) -> dict:
        """列出章节"""
        if not state.project:
            return {"reply": "请先打开一个项目，我才能帮你操作。"}
        project = state.project
        chapters = project.chapters
        ch_list = []
        for i, ch in enumerate(chapters):
            wc = ch.get("word_count", 0)
            ch_list.append(f"第{i+1}章 {ch.get('title', '')} ({wc}字)")
        return {
            "reply": f"当前项目《{project.meta.get('title', '未命名')}》共{len(chapters)}章：\n" + "\n".join(ch_list),
            "data": {"chapters": [{"index": i, "title": ch.get("title", ""), "word_count": ch.get("word_count", 0)} for i, ch in enumerate(chapters)]},
        }

    def _load_chapter(self, params: dict, context: dict) -> dict:
        """加载章节内容"""
        idx = _resolve_chapter_index(params, context)
        title, content = _get_chapter_content(idx)
        if content:
            preview = content[:500] + ("..." if len(content) > 500 else "")
            return {
                "reply": f"第{idx+1}章《{title}》共{len(content)}字。\n\n开头预览：\n{preview}",
                "data": {"chapter_index": idx, "title": title, "content": content, "word_count": len(content)},
                "action": {"type": "load_chapter", "chapter_index": idx},
            }
        else:
            return {"reply": f"第{idx+1}章没有内容。"}

    def _save_chapter(self, params: dict, context: dict) -> dict:
        """保存章节"""
        idx = _resolve_chapter_index(params, context)
        return {
            "reply": f"请在编辑器中编辑内容后点击保存按钮，或者我帮你加载第{idx+1}章内容。",
            "action": {"type": "save_chapter", "chapter_index": idx},
        }

    def _add_chapter(self, params: dict, context: dict) -> dict:
        """新建章节"""
        try:
            if not state.project:
                return {"reply": "请先打开一个项目。"}
            new_idx = state.project.add_chapter(f"第{len(state.project.chapters)+1}章")
            return {
                "reply": f"已新建第{new_idx+1}章。可以在步骤3生成大纲，或步骤4开始写作。",
                "action": {"type": "reload_chapters", "chapter_index": new_idx},
            }
        except Exception as e:
            return {"reply": f"新建章节失败：{e}"}

    def _delete_chapter(self, params: dict, context: dict) -> dict:
        """删除章节"""
        idx = _resolve_chapter_index(params, context)
        if idx is None or idx < 0:
            return {"reply": "请指定要删除的章节号，如'删除第3章'。"}
        try:
            if not state.project or idx >= len(state.project.chapters):
                return {"reply": f"第{idx+1}章不存在。"}
            title = state.project.chapters[idx].get("title", "")
            word_count = state.project.chapters[idx].get("word_count", 0)
            state.project.delete_chapter(idx)
            return {
                "reply": f"已删除第{idx+1}章「{title}」（{word_count}字）。剩余{len(state.project.chapters)}章。",
                "action": {"type": "reload_chapters", "chapter_index": max(0, idx-1)},
            }
        except Exception as e:
            return {"reply": f"删除章节失败：{e}"}

    def _reorder_chapter(self, params: dict, context: dict) -> dict:
        """调整章节顺序"""
        idx = _resolve_chapter_index(params, context)
        target = params.get("target_index")
        if idx is None or target is None:
            return {"reply": "请指定要移动的章节和目标位置，如'把第2章移到第4章后面'。"}
        try:
            if not state.project:
                return {"reply": "请先打开项目。"}
            if idx < 0 or idx >= len(state.project.chapters) or target < 0 or target >= len(state.project.chapters):
                return {"reply": f"章节号超出范围（共{len(state.project.chapters)}章）。"}
            ok = state.project.reorder_chapter(idx, target)
            if ok:
                return {
                    "reply": f"已将第{idx+1}章移动到第{target+1}章位置。",
                    "action": {"type": "reload_chapters"},
                }
            else:
                return {"reply": "调整顺序失败。"}
        except Exception as e:
            return {"reply": f"调整顺序失败：{e}"}

    def _get_volumes(self, params: dict, context: dict) -> dict:
        """列出卷"""
        from backend.agents.dispatcher import _api_get, _get_base_url
        try:
            vdata = _api_get(_get_base_url() + "/api/project/volumes", timeout=10)
            if vdata.get("ok"):
                vols = vdata.get("volumes", [])
                text = f"共{len(vols)}卷：\n"
                for i, v in enumerate(vols):
                    # outline 是 dict（含 summary/theme/key_events/character_arcs），提取 summary
                    outline_raw = v.get('outline', '')
                    if isinstance(outline_raw, dict):
                        outline_text = outline_raw.get('summary', '') or outline_raw.get('theme', '')
                    elif isinstance(outline_raw, str):
                        outline_text = outline_raw
                    else:
                        outline_text = str(outline_raw)
                    text += f"  第{i+1}卷 {v.get('title', '')}: {outline_text[:40]}\n"
                return {"reply": text, "data": vdata}
            else:
                return {"reply": "暂无卷数据。"}
        except Exception as e:
            return {"reply": f"获取卷列表出错：{e}"}

    # ── 章节重命名 ──

    def _rename_chapter(self, params: dict, context: dict) -> dict:
        """重命名章节"""
        from backend.agents.dispatcher import _api_post, _get_base_url
        idx = _resolve_chapter_index(params, context)
        title = (params.get("title") or "").strip()
        if not title:
            return {"reply": "请告诉我新标题，如'把第3章改名为风起'。"}
        try:
            if not state.project:
                return {"reply": "请先打开项目。"}
            if idx >= len(state.project.chapters):
                return {"reply": f"第{idx+1}章不存在（共{len(state.project.chapters)}章）。"}
            old_title = state.project.chapters[idx].get("title", "")
            rdata = _api_post(_get_base_url() + "/api/chapter/rename",
                              {"index": idx, "title": title}, timeout=10)
            if rdata.get("ok"):
                return {
                    "reply": f"已将第{idx+1}章「{old_title}」改名为「{title}」。",
                    "action": {"type": "reload_chapters"},
                }
            return {"reply": f"重命名失败：{rdata.get('error', '')}"}
        except Exception as e:
            return {"reply": f"重命名章节失败：{e}"}

    # ── 卷增删改 ──

    def _resolve_vol_index(self, params: dict) -> int:
        """解析卷序号：vol_index 优先，否则按名称匹配"""
        vol_index = params.get("vol_index")
        if vol_index is not None:
            return int(vol_index)
        # 按标题匹配（rename_volume 的 title 是新名，不适用；仅限删除时按名查）
        name = (params.get("title") or "").strip()
        if name and state.project:
            for i, v in enumerate(state.project.get_volumes()):
                if v.get("title") == name:
                    return i
        return -1

    def _add_volume(self, params: dict, context: dict) -> dict:
        """新增卷"""
        from backend.agents.dispatcher import _api_post, _get_base_url
        title = (params.get("title") or "").strip()
        if not title:
            return {"reply": "请告诉我新卷的名字，如'新增一卷叫龙起卷'。"}
        try:
            rdata = _api_post(_get_base_url() + "/api/project/volume/add",
                              {"title": title, "outline": params.get("description", "") or ""},
                              timeout=10)
            if rdata.get("ok"):
                return {
                    "reply": f"已新增第{rdata.get('index', 0)+1}卷「{title}」。",
                    "action": {"type": "reload_volumes"},
                }
            return {"reply": f"新增卷失败：{rdata.get('error', '')}"}
        except Exception as e:
            return {"reply": f"新增卷出错：{e}"}

    def _delete_volume(self, params: dict, context: dict) -> dict:
        """删除卷（章节归入前一卷）"""
        from backend.agents.dispatcher import _api_post, _get_base_url
        vol_index = self._resolve_vol_index(params)
        if vol_index < 0:
            return {"reply": "请指定要删除的卷，如'删除第2卷'。"}
        try:
            if not state.project:
                return {"reply": "请先打开项目。"}
            vols = state.project.get_volumes()
            if vol_index >= len(vols):
                return {"reply": f"第{vol_index+1}卷不存在（共{len(vols)}卷）。"}
            vol_title = vols[vol_index].get("title", "")
            rdata = _api_post(_get_base_url() + "/api/project/volume/delete",
                              {"vol_index": vol_index}, timeout=10)
            if rdata.get("ok"):
                return {
                    "reply": f"已删除第{vol_index+1}卷「{vol_title}」，其中章节已归入前一卷。",
                    "action": {"type": "reload_volumes"},
                }
            return {"reply": f"删除卷失败：{rdata.get('error', '')}"}
        except Exception as e:
            return {"reply": f"删除卷出错：{e}"}

    def _rename_volume(self, params: dict, context: dict) -> dict:
        """重命名卷"""
        from backend.agents.dispatcher import _api_post, _get_base_url
        # 注意：此时 title 是新名，不能用 _resolve_vol_index 按名匹配，必须显式 vol_index
        vol_index = params.get("vol_index")
        new_title = (params.get("title") or "").strip()
        if vol_index is None:
            return {"reply": "请指定要改名的卷序号，如'把第2卷改名为xxx'。"}
        if not new_title:
            return {"reply": "请告诉我新卷名。"}
        try:
            if not state.project:
                return {"reply": "请先打开项目。"}
            vols = state.project.get_volumes()
            vol_index = int(vol_index)
            if vol_index >= len(vols):
                return {"reply": f"第{vol_index+1}卷不存在（共{len(vols)}卷）。"}
            old_title = vols[vol_index].get("title", "")
            rdata = _api_post(_get_base_url() + "/api/project/volume/rename",
                              {"vol_index": vol_index, "title": new_title}, timeout=10)
            if rdata.get("ok"):
                return {
                    "reply": f"已将第{vol_index+1}卷「{old_title}」改名为「{new_title}」。",
                    "action": {"type": "reload_volumes"},
                }
            return {"reply": f"重命名卷失败：{rdata.get('error', '')}"}
        except Exception as e:
            return {"reply": f"重命名卷出错：{e}"}
