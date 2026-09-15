# -*- coding: utf-8 -*-
"""书斋 V66 - 卷管理 Mixin（增删改查 + 自动解析 + 大纲驱动卷结构）"""
import os, re, time, logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class ProjectVolumesMixin:
    """卷管理 Mixin：卷 CRUD + 自动重建 + 大纲解析卷结构"""

    # ── Volumes CRUD ──

    def set_volumes(self, volumes_data: List[Dict]):
        """设置卷数据（覆盖），自动补全index和chapters"""
        for i, vol in enumerate(volumes_data):
            if "index" not in vol or vol["index"] is None:
                vol["index"] = i
            # 如果有 start_chapter/end_chapter 但没有 chapters 数组，自动生成
            if "chapters" not in vol or not vol["chapters"]:
                start = vol.get("start_chapter", 0)
                end = vol.get("end_chapter", 0)
                if start > 0 and end >= start:
                    vol["chapters"] = list(range(start, end + 1))
                else:
                    vol["chapters"] = []
        self.volumes = volumes_data
        self._dirty = True
        self._save_meta()

    def get_volumes(self) -> List[Dict]:
        """获取卷数据，动态计算 chapter_count，补全index"""
        result = []
        for i, vol in enumerate(self.volumes):
            vol_copy = dict(vol)
            vol_copy["index"] = i
            vol_copy["chapter_count"] = len(vol.get("chapters", []))
            result.append(vol_copy)
        return result

    def add_volume(self, title: str, outline: str = "", start_chapter: int = 0, end_chapter: int = 0):
        """添加一卷，支持指定章节范围"""
        idx = len(self.volumes)
        chapters = []
        if start_chapter > 0 and end_chapter >= start_chapter:
            chapters = list(range(start_chapter, end_chapter + 1))
            # 从已有卷中移除重叠的章节
            for vol in self.volumes:
                existing = vol.get("chapters", [])
                if existing:
                    vol["chapters"] = [c for c in existing if c < start_chapter or c > end_chapter]
                    vol["chapter_count"] = len(vol["chapters"])
        self.volumes.append({
            "index": idx,
            "title": title or f"第{idx+1}卷",
            "outline": {
                "summary": outline if isinstance(outline, str) else "",
                "theme": "",
                "key_events": [],
                "character_arcs": []
            },
            "chapters": chapters,
        })
        self._dirty = True
        self._save_meta()
        return idx

    def delete_volume(self, vol_index: int) -> bool:
        """删除一卷（不删除卷内章节，将其移到前一卷；删除最后一卷时仅清空卷结构，保留章节数据）"""
        if vol_index < 0 or vol_index >= len(self.volumes):
            return False
        if len(self.volumes) <= 1:
            # 删除最后一卷：仅清空卷结构，章节数据保留（用户可能还想写）
            self.volumes = []
            self._dirty = True
            self._save_meta()
            return True
        removed = self.volumes.pop(vol_index)
        target_idx = vol_index - 1 if vol_index > 0 else 0
        if target_idx < 0:
            target_idx = 0
        if target_idx < len(self.volumes):
            self.volumes[target_idx]["chapters"].extend(removed.get("chapters", []))
            self.volumes[target_idx]["chapter_count"] = len(self.volumes[target_idx]["chapters"])
        for i, vol in enumerate(self.volumes):
            vol["index"] = i
        self._dirty = True
        self._save_meta()
        return True

    def rename_volume(self, vol_index: int, title: str) -> bool:
        """重命名一卷"""
        if vol_index < 0 or vol_index >= len(self.volumes):
            return False
        self.volumes[vol_index]["title"] = title
        self._dirty = True
        self._save_meta()
        return True

    def add_chapter_to_volume(self, vol_index: int, chapter_idx: int) -> bool:
        """将章节添加到指定卷"""
        if vol_index < 0 or vol_index >= len(self.volumes):
            return False
        vol = self.volumes[vol_index]
        chapters = vol.get("chapters", [])
        if chapter_idx not in chapters:
            chapters.append(chapter_idx)
            chapters.sort()
            vol["chapters"] = chapters
            vol["chapter_count"] = len(chapters)
            self._dirty = True
            self._save_meta()
            return True
        return False

    def remove_chapter_from_volume(self, vol_index: int, chapter_idx: int) -> bool:
        """从指定卷移除章节"""
        if vol_index < 0 or vol_index >= len(self.volumes):
            return False
        vol = self.volumes[vol_index]
        chapters = vol.get("chapters", [])
        if chapter_idx in chapters:
            chapters.remove(chapter_idx)
            vol["chapters"] = chapters
            vol["chapter_count"] = len(chapters)
            self._dirty = True
            self._save_meta()
            return True
        return False

    def set_volume_chapters(self, vol_index: int, chapter_indices: List[int]) -> bool:
        """设置卷的章节列表（覆盖）"""
        if vol_index < 0 or vol_index >= len(self.volumes):
            return False
        vol = self.volumes[vol_index]
        vol["chapters"] = sorted(list(set(chapter_indices)))
        vol["chapter_count"] = len(vol["chapters"])
        self._dirty = True
        self._save_meta()
        return True

    def set_volume_outline(self, vol_index: int, outline_data: dict) -> bool:
        """设置卷纲要（structured object）"""
        if vol_index < 0 or vol_index >= len(self.volumes):
            return False
        self.volumes[vol_index]["outline"] = outline_data
        self._dirty = True
        self._save_meta()
        return True

    def get_volume_outline(self, vol_index: int) -> dict:
        """获取卷纲要（返回 dict，空则返回空结构，确保字段完整）"""
        default = {"summary": "", "theme": "", "key_events": [], "character_arcs": []}
        if vol_index < 0 or vol_index >= len(self.volumes):
            return default
        outline = self.volumes[vol_index].get("outline", {})
        if isinstance(outline, dict):
            # 确保所有必需字段存在
            for k in default:
                if k not in outline or outline[k] is None:
                    outline[k] = default[k]
            # 确保列表字段是列表类型
            if not isinstance(outline.get("key_events"), list):
                outline["key_events"] = []
            if not isinstance(outline.get("character_arcs"), list):
                outline["character_arcs"] = []
            return outline
        # 旧版本是字符串，转换为summary
        if isinstance(outline, str) and outline.strip():
            default["summary"] = outline.strip()
        return default

    # ── 自动重建 ──

    def rebuild_volumes_from_chapters(self):
        """根据 chapters 标题自动重建 volumes（兼容旧项目）。
        策略：按章节标题中的卷号关键词分组，如标题包含"卷X"或"第X卷"。
        如果无法识别卷号，则所有章节归入一个默认卷。
        """
        if not self.chapters:
            self.volumes = []
            return

        volume_map: Dict[int, Dict] = {}
        default_volume = {"index": 1, "title": "正文", "outline": {"summary": "", "theme": "", "key_events": [], "character_arcs": []}, "chapters": []}

        for ch in self.chapters:
            ch_idx = ch.get("index", 0)
            title = ch.get("title", "")
            m = re.search(r'(?:第|卷·?)(\d+)卷', title)
            if m:
                vol_num = int(m.group(1))
            else:
                m2 = re.search(r'卷(\d+)', title)
                if m2:
                    vol_num = int(m2.group(1))
                else:
                    vol_num = 0

            if vol_num == 0:
                default_volume["chapters"].append(ch_idx)
            else:
                if vol_num not in volume_map:
                    volume_map[vol_num] = {
                        "index": vol_num,
                        "title": f"第{vol_num}卷",
                        "outline": {"summary": "", "theme": "", "key_events": [], "character_arcs": []},
                        "chapters": [],
                    }
                volume_map[vol_num]["chapters"].append(ch_idx)

        if not volume_map:
            default_volume["chapters"] = [ch.get("index", 0) for ch in self.chapters]
            self.volumes = [default_volume]
        else:
            result = []
            if default_volume["chapters"]:
                result.append(default_volume)
            result.extend(sorted(volume_map.values(), key=lambda x: x["index"]))
            self.volumes = result

        self._dirty = True
        self._save_meta()

    def auto_build_volumes_from_outline(self):
        """根据 outline.txt 自动解析卷结构并创建卷和章节。
        支持多种大纲格式：
        1. 明确的阶段标记：## 第X阶段 / ## 阶段X / ## 第X卷 / ## 卷X / ## 第X幕 / ## 第X部
        2. 章节标题中含卷号：第X卷·... / 卷X·... / 第X部·...
        3. 阶段标题下包含章节列表
        返回 {"ok": True, "volumes": [...], "chapters": [...]}
        """
        outline_text = self.get_outline_text()
        if not outline_text:
            return {"ok": False, "error": "大纲为空"}

        self.volumes = []
        self.chapters = []

        stage_pattern = re.compile(
            r'^##\s*(?:第)?\s*(\d+)\s*(?:阶段|卷|幕|部)\s*[·：:]?\s*(.*?)(?:\n|$)',
            re.MULTILINE
        )
        alt_stage_pattern = re.compile(
            r'^---\s*(?:第)?\s*(\d+)\s*(?:阶段|卷|幕|部)\s*[·：:]?\s*(.*?)(?:\n|$)',
            re.MULTILINE
        )

        stages = []
        for m in stage_pattern.finditer(outline_text):
            stage_num = int(m.group(1))
            stage_title = m.group(2).strip() or f"第{stage_num}阶段"
            start_pos = m.end()
            stages.append({"num": stage_num, "title": stage_title, "start": start_pos})

        if not stages:
            for m in alt_stage_pattern.finditer(outline_text):
                stage_num = int(m.group(1))
                stage_title = m.group(2).strip() or f"第{stage_num}阶段"
                start_pos = m.end()
                stages.append({"num": stage_num, "title": stage_title, "start": start_pos})

        for i, stage in enumerate(stages):
            if i + 1 < len(stages):
                stage["end"] = stages[i + 1]["start"]
            else:
                stage["end"] = len(outline_text)
            stage["text"] = outline_text[stage["start"]:stage["end"]]

        if stages:
            ch_num = 0
            for stage in stages:
                vol_idx = len(self.volumes) + 1
                vol = {
                    "index": vol_idx,
                    "title": stage["title"],
                    "outline": {
                        "summary": stage["text"].strip()[:300],
                        "theme": "",
                        "key_events": [],
                        "character_arcs": []
                    },
                    "chapters": [],
                }

                ch_pattern = re.compile(
                    r'(?:第(\d+)章)\s*[·：:.]?\s*(.*?)(?:\s*\||\s*$)',
                    re.MULTILINE
                )
                ch_pattern_alt = re.compile(
                    r'^\s*(?:-|—|•|\*)\s*(.*?)(?:\s*\||\s*$)',
                    re.MULTILINE
                )
                ch_pattern_num = re.compile(
                    r'^\s*(\d+)\s*[.)、:：]\s*(.*?)(?:\s*\||\s*$)',
                    re.MULTILINE
                )

                found_chapters = []
                for cm in ch_pattern.finditer(stage["text"]):
                    found_chapters.append({"num": int(cm.group(1)), "title": cm.group(2).strip()})

                if not found_chapters:
                    for cm in ch_pattern_num.finditer(stage["text"]):
                        found_chapters.append({"num": int(cm.group(1)), "title": cm.group(2).strip()})

                if not found_chapters:
                    for cm in ch_pattern_alt.finditer(stage["text"]):
                        found_chapters.append({"num": len(found_chapters) + 1, "title": cm.group(1).strip()})

                if found_chapters:
                    for cm in found_chapters:
                        ch_num += 1
                        ch_title = f"第{ch_num}章·{cm['title']}" if cm['title'] else f"第{ch_num}章"
                        ch_idx = len(self.chapters) + 1
                        self.chapters.append({
                            "index": ch_idx,
                            "title": ch_title,
                            "word_count": 0,
                            "created": time.strftime("%Y-%m-%d %H:%M"),
                            "outline": ch_title,
                            "status": "draft",
                            "pov": "",
                            "scene_labels": [],
                        })
                        vol["chapters"].append(ch_idx)
                else:
                    lines = stage["text"].strip().split('\n')
                    meaningful_lines = [l.strip() for l in lines if l.strip() and len(l.strip()) > 10]
                    if meaningful_lines:
                        chapters_per_stage = max(3, min(len(meaningful_lines), 8))
                        chunk_size = max(1, len(meaningful_lines) // chapters_per_stage)
                        for i in range(chapters_per_stage):
                            ch_num += 1
                            start = i * chunk_size
                            end = (i + 1) * chunk_size if i < chapters_per_stage - 1 else len(meaningful_lines)
                            chunk_text = '\n'.join(meaningful_lines[start:end]).strip()
                            if chunk_text:
                                ch_title = f"第{ch_num}章·{chunk_text[:20]}..." if len(chunk_text) > 20 else f"第{ch_num}章·{chunk_text}"
                                ch_idx = len(self.chapters) + 1
                                self.chapters.append({
                                    "index": ch_idx,
                                    "title": ch_title,
                                    "word_count": 0,
                                    "created": time.strftime("%Y-%m-%d %H:%M"),
                                    "outline": chunk_text,
                                    "status": "draft",
                                    "pov": "",
                                    "scene_labels": [],
                                })
                                vol["chapters"].append(ch_idx)

                self.volumes.append(vol)

            if ch_num == 0:
                ch_num = self._extract_chapters_from_full_text(outline_text)

        if not stages:
            ch_num = self._extract_chapters_from_full_text(outline_text)
            if ch_num > 0:
                self._group_chapters_into_volumes()

        if not self.volumes:
            self.volumes = [{
                "index": 1,
                "title": "正文",
                "outline": {
                    "summary": outline_text[:300],
                    "theme": "",
                    "key_events": [],
                    "character_arcs": []
                },
                "chapters": [],
            }]

        for i, vol in enumerate(self.volumes):
            vol["index"] = i + 1
        for i, ch in enumerate(self.chapters):
            ch["index"] = i + 1

        for ch in self.chapters:
            cf = os.path.join(self.project_dir, "chapters", f"chapter_{ch['index']:03d}.txt")
            if not os.path.exists(cf):
                with open(cf, "w", encoding="utf-8") as f:
                    f.write("")

        self._dirty = True
        self._save_meta()
        return {
            "ok": True,
            "volumes": self.get_volumes(),
            "chapters": len(self.chapters),
            "chapter_titles": [ch["title"] for ch in self.chapters],
        }

    def _extract_chapters_from_full_text(self, outline_text: str) -> int:
        """从全文中提取章节（不依赖阶段标记），支持多种格式"""
        ch_num = 0
        ch_pattern = re.compile(
            r'(?:第(\d+)章)\s*[·：:.]?\s*(.*?)(?:\s*\||\s*$)',
            re.MULTILINE
        )
        ch_pattern_num = re.compile(
            r'^\s*(\d+)\s*[.)、:：]\s*(.*?)(?:\s*\||\s*$)',
            re.MULTILINE
        )
        ch_pattern_alt = re.compile(
            r'^\s*(?:-|—|•|\*)\s*(.*?)(?:\s*\||\s*$)',
            re.MULTILINE
        )

        found_chapters = []
        for cm in ch_pattern.finditer(outline_text):
            found_chapters.append({"num": int(cm.group(1)), "title": cm.group(2).strip()})

        if not found_chapters:
            for cm in ch_pattern_num.finditer(outline_text):
                found_chapters.append({"num": int(cm.group(1)), "title": cm.group(2).strip()})

        if not found_chapters:
            for cm in ch_pattern_alt.finditer(outline_text):
                found_chapters.append({"num": len(found_chapters) + 1, "title": cm.group(1).strip()})

        if found_chapters:
            for cm in found_chapters:
                ch_num += 1
                ch_title = f"第{ch_num}章·{cm['title']}" if cm['title'] else f"第{ch_num}章"
                self.chapters.append({
                    "index": ch_num,
                    "title": ch_title,
                    "word_count": 0,
                    "created": time.strftime("%Y-%m-%d %H:%M"),
                    "outline": ch_title,
                    "status": "draft",
                    "pov": "",
                    "scene_labels": [],
                })
        else:
            lines = outline_text.strip().split('\n')
            meaningful_lines = [l.strip() for l in lines if l.strip() and len(l.strip()) > 10]
            if meaningful_lines:
                total_chapters = max(5, min(len(meaningful_lines), 15))
                chunk_size = max(1, len(meaningful_lines) // total_chapters)
                for i in range(total_chapters):
                    ch_num += 1
                    start = i * chunk_size
                    end = (i + 1) * chunk_size if i < total_chapters - 1 else len(meaningful_lines)
                    chunk_text = '\n'.join(meaningful_lines[start:end]).strip()
                    if chunk_text:
                        ch_title = f"第{ch_num}章·{chunk_text[:20]}..." if len(chunk_text) > 20 else f"第{ch_num}章·{chunk_text}"
                        self.chapters.append({
                            "index": ch_num,
                            "title": ch_title,
                            "word_count": 0,
                            "created": time.strftime("%Y-%m-%d %H:%M"),
                            "outline": chunk_text,
                            "status": "draft",
                            "pov": "",
                            "scene_labels": [],
                        })
        return ch_num

    def _group_chapters_into_volumes(self):
        """将章节按标题中的卷号分组为卷"""
        volume_map: Dict[int, Dict] = {}
        default_chapters = []

        for ch in self.chapters:
            title = ch.get("title", "")
            m = re.search(r'(?:第|卷·?)(\d+)\s*(?:卷|部|幕)', title)
            if m:
                vol_num = int(m.group(1))
            else:
                m2 = re.search(r'卷(\d+)', title)
                if m2:
                    vol_num = int(m2.group(1))
                else:
                    vol_num = 0

            if vol_num == 0:
                default_chapters.append(ch["index"])
            else:
                if vol_num not in volume_map:
                    volume_map[vol_num] = {
                        "index": vol_num,
                        "title": f"第{vol_num}卷",
                        "outline": {"summary": "", "theme": "", "key_events": [], "character_arcs": []},
                        "chapters": [],
                    }
                volume_map[vol_num]["chapters"].append(ch["index"])

        self.volumes = []
        if default_chapters:
            self.volumes.append({
                "index": 1, "title": "正文", "outline": {"summary": "", "theme": "", "key_events": [], "character_arcs": []}, "chapters": default_chapters
            })
        self.volumes.extend(sorted(volume_map.values(), key=lambda x: x["index"]))