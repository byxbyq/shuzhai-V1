# -*- coding: utf-8 -*-
"""时间线服务 - 计划 vs 实际对照系统

存储在每个项目目录下的 timeline.json 中，结构与大纲同构：
  卷 → 章 → { planned, actual, divergences, annotation }
"""

import os
import json
import time
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class TimelineService:
    """管理项目的时间线数据（计划 vs 实际对照）。"""

    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.file_path = os.path.join(project_dir, "timeline.json")
        self.data = self._load()

    # ── 文件读写 ──────────────────────────────────

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {"volumes": {}}
        return {"volumes": {}}

    def _save(self):
        os.makedirs(self.project_dir, exist_ok=True)
        # 写入前备份旧文件
        try:
            if os.path.exists(self.file_path):
                import shutil as _shutil
                _shutil.copy2(self.file_path, self.file_path + '.bak')
        except Exception:
            pass
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # ── 章节节点默认值 ───────────────────────────

    @staticmethod
    def _empty_chapter_node() -> dict:
        return {
            "planned": "",
            "actual": "",
            "divergences": [],
            "annotation": "",
            "last_compared": None,
            # 蒸馏记忆整合字段
            "characters": [],       # 角色状态变化
            "events": [],           # 核心事件
            "foreshadowing": {"planted": [], "resolved": []},  # 伏笔种下/回收
            "new_settings": [],     # 新设定
            "bridge": {"from_prev": "", "to_next": ""},  # 衔接锚
        }

    # ── 读取 ──────────────────────────────────────

    def get_timeline(self) -> Dict[str, Any]:
        """返回完整时间线树。"""
        return self.data

    def get_chapter(self, volume_index: int, chapter_index: int) -> Optional[dict]:
        """获取某一章的对照数据。"""
        vol = self.data.get("volumes", {}).get(str(volume_index))
        if not vol:
            return None
        return vol.get("chapters", {}).get(str(chapter_index))

    # ── 写入 ──────────────────────────────────────

    def ensure_structure(self, volumes: List[dict], chapters: List[dict]):
        """根据实际项目结构创建/补齐时间线骨架，并清理多余的卷和章节。

        volumes:  [{index, title}, ...]
        chapters: [{index, volume_index, title}, ...]
        """
        vols = self.data.setdefault("volumes", {})

        valid_vol_keys = set()
        for v in volumes:
            vk = str(v.get("index", 0))
            valid_vol_keys.add(vk)
            if vk not in vols:
                vols[vk] = {"title": v.get("title", ""), "chapters": {}}
            else:
                vols[vk]["title"] = v.get("title", vols[vk].get("title", ""))

        # 构建有效的章节映射: {vol_index: set(chapter_index_str)}
        valid_ch_map: Dict[str, set] = {}
        for ch in chapters:
            vi = str(ch.get("volume_index", 0))
            ci = str(ch.get("index", 0))
            if vi not in valid_ch_map:
                valid_ch_map[vi] = set()
            valid_ch_map[vi].add(ci)

            if vi not in vols:
                vols[vi] = {"title": "", "chapters": {}}
            chs = vols[vi].setdefault("chapters", {})
            if ci not in chs:
                chs[ci] = self._empty_chapter_node()
            chs[ci]["title"] = ch.get("title", "")

        # 清理不在有效列表中的卷
        for vk in list(vols.keys()):
            if vk not in valid_vol_keys and vk not in valid_ch_map:
                del vols[vk]

        # 清理不在有效列表中的章节
        for vk, v in vols.items():
            chs = v.get("chapters", {})
            valid = valid_ch_map.get(vk, set())
            for ck in list(chs.keys()):
                if ck not in valid:
                    del chs[ck]

        self._save()

    def update_planned(self, volume_index: int, chapter_index: int, planned: str):
        """更新某章的「计划」列（来自章节大纲）。"""
        node = self._get_or_create_node(volume_index, chapter_index)
        node["planned"] = planned
        self._save()

    def _find_volume_for_chapter(self, chapter_index: int) -> int:
        """根据时间线数据结构找到章节所属的卷索引。"""
        for vol_idx, vol_data in enumerate(self.data.get("volumes", [])):
            chapters_in_vol = vol_data.get("chapters", {})
            if chapter_index in chapters_in_vol:
                return vol_idx
        # 如果找不到，返回最后一个卷（或0如果无卷）
        volumes = self.data.get("volumes", [])
        return max(0, len(volumes) - 1) if volumes else 0

    def update_actual(self, volume_index: int, chapter_index: int,
                      actual: str, divergences: list = None):
        """更新某章的「实际」列和分歧列表。"""
        node = self._get_or_create_node(volume_index, chapter_index)
        node["actual"] = actual
        if divergences is not None:
            node["divergences"] = divergences
        node["last_compared"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save()

    def update_annotation(self, volume_index: int, chapter_index: int,
                          annotation: str):
        """更新手工注释。"""
        node = self._get_or_create_node(volume_index, chapter_index)
        node["annotation"] = annotation
        self._save()

    def update_distill(self, volume_index: int, chapter_index: int,
                       characters: list = None, events: list = None,
                       foreshadowing: dict = None, new_settings: list = None,
                       bridge: dict = None):
        """更新某章的蒸馏记忆数据（来自 state_memory）。

        任何参数为 None 时保留原值；空值会覆盖（表示该章无变化）。
        """
        node = self._get_or_create_node(volume_index, chapter_index)
        if characters is not None:
            node["characters"] = characters
        if events is not None:
            node["events"] = events
        if foreshadowing is not None:
            # 确保 planted/resolved 字段存在
            node["foreshadowing"] = {
                "planted": foreshadowing.get("planted", []) or [],
                "resolved": foreshadowing.get("resolved", []) or [],
            }
        if new_settings is not None:
            node["new_settings"] = new_settings
        if bridge is not None:
            node["bridge"] = {
                "from_prev": bridge.get("from_prev", ""),
                "to_next": bridge.get("to_next", ""),
            }
        self._save()

    def update_divergence_status(self, volume_index: int, chapter_index: int,
                                 divergence_index: int, status: str):
        """更新某条分歧的处理状态（待处理/已接受/已修复）。"""
        node = self._get_or_create_node(volume_index, chapter_index)
        divs = node.get("divergences", [])
        if 0 <= divergence_index < len(divs):
            divs[divergence_index]["status"] = status
        self._save()

    def update_divergence(self, volume_index: int, chapter_index: int,
                          divergence_index: int, divergence_data: dict):
        """更新某条分歧的完整内容（类型、内容、说明、状态等）。"""
        node = self._get_or_create_node(volume_index, chapter_index)
        divs = node.get("divergences", [])
        if 0 <= divergence_index < len(divs):
            divs[divergence_index].update(divergence_data)
        self._save()

    def delete_divergence(self, volume_index: int, chapter_index: int,
                          divergence_index: int) -> bool:
        """删除某条分歧。返回是否成功。"""
        node = self._get_or_create_node(volume_index, chapter_index)
        divs = node.get("divergences", [])
        if 0 <= divergence_index < len(divs):
            divs.pop(divergence_index)
            self._save()
            return True
        return False

    def add_divergence(self, volume_index: int, chapter_index: int,
                       divergence_data: dict) -> int:
        """新增一条分歧。返回新分歧的索引。"""
        node = self._get_or_create_node(volume_index, chapter_index)
        divs = node.setdefault("divergences", [])
        new_div = {
            "type": divergence_data.get("type", "修改"),
            "item": divergence_data.get("item", ""),
            "note": divergence_data.get("note", ""),
            "status": divergence_data.get("status", "待处理"),
        }
        divs.append(new_div)
        self._save()
        return len(divs) - 1

    def _get_or_create_node(self, volume_index: int, chapter_index: int) -> dict:
        vols = self.data.setdefault("volumes", {})
        vi = str(volume_index)
        ci = str(chapter_index)
        if vi not in vols:
            vols[vi] = {"title": "", "chapters": {}}
        chs = vols[vi].setdefault("chapters", {})
        if ci not in chs:
            chs[ci] = self._empty_chapter_node()
        return chs[ci]

    # ── 批量导入 ──────────────────────────────────

    def import_from_outlines(self, all_chapter_outlines: Dict[int, str]):
        """从章节大纲批量导入 planned 列。

        all_chapter_outlines: {chapter_index: outline_text}
        """
        for ci, text in all_chapter_outlines.items():
            # 需要根据章节索引找到对应的卷
            volume_index = self._find_volume_for_chapter(ci)
            self.update_planned(volume_index, ci, text)
