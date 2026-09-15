# -*- coding: utf-8 -*-
"""书斋 V66 - 章节管理 + 快照 Mixin"""
import os, time, logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class ProjectChaptersMixin:
    """章节管理 Mixin：增删读写 + 快照 + 前文上下文 + 规划可视化字段"""

    # ── Chapters ──

    def _normalize_chapter_fields(self, ch: Dict) -> Dict:
        """补齐规划可视化扩展字段（兼容旧项目数据）"""
        if "status" not in ch:
            ch["status"] = "draft"
        if "pov" not in ch:
            ch["pov"] = ""
        if "scene_labels" not in ch:
            ch["scene_labels"] = []
        return ch

    def normalize_all_chapters(self):
        """批量补齐所有章节的扩展字段（项目打开时调用）"""
        for ch in self.chapters:
            self._normalize_chapter_fields(ch)
        return self.chapters

    def add_chapter(self, title: str, vol_index: int = None) -> int:
        idx = len(self.chapters) + 1
        self.chapters.append({
            "index": idx, "title": title or f"第{idx}章",
            "word_count": 0, "created": time.strftime("%Y-%m-%d %H:%M"),
            "status": "draft", "pov": "", "scene_labels": []
        })
        if self.volumes:
            if vol_index is not None and 1 <= vol_index <= len(self.volumes):
                target_vol = self.volumes[vol_index - 1]
            else:
                target_vol = self.volumes[-1]
            target_vol["chapters"].append(idx)
            target_vol["chapter_count"] = len(target_vol["chapters"])
        self.meta["current_chapter"] = idx - 1
        self._dirty = True
        self.set_content("", idx - 1)
        self._save_meta()
        return idx - 1

    def delete_chapter(self, idx: int):
        if len(self.chapters) <= 1: return
        if 0 <= idx < len(self.chapters):
            ch = self.chapters.pop(idx)
            deleted_idx = ch["index"]
            cf = os.path.join(self.project_dir, "chapters", f"chapter_{deleted_idx:03d}.txt")
            if os.path.exists(cf):
                try:
                    os.remove(cf)
                except Exception as e:
                    logger.warning("删除章节文件失败: %s", e)
            self._chapter_cache.pop(deleted_idx, None)
            # 记录旧 index 用于文件重命名
            for c in self.chapters:
                c["_old_file_idx"] = c.get("index", 0)
            for i, c in enumerate(self.chapters):
                c["index"] = i + 1
            # 重命名磁盘文件以匹配新序号
            self._reorder_chapter_files()
            for c in self.chapters:
                c.pop("_old_file_idx", None)
            if self.volumes:
                for vol in self.volumes:
                    vol["chapters"] = [c for c in vol["chapters"] if c != deleted_idx]
                    vol["chapters"] = [c - 1 if c > deleted_idx else c for c in vol["chapters"]]
                    vol["chapter_count"] = len(vol["chapters"])
            cur = self.meta["current_chapter"]
            if cur >= idx and cur > 0:
                self.meta["current_chapter"] = cur - 1
            self.meta["current_chapter"] = max(0, min(self.meta["current_chapter"], len(self.chapters) - 1))
            self._dirty = True
            self._save_meta()

    def reorder_chapter(self, from_index: int, to_index: int, from_vol: int = None, to_vol: int = None) -> bool:
        """重排章节顺序：将 chapters[from_index] 移动到 to_index 位置。
        from_index / to_index 均为 0-based 的 chapters 数组下标。
        同步更新 volumes 中各卷的 chapters 列表与 chapters 的 index 字段。
        返回是否成功。
        """
        if not self.chapters:
            return False
        if from_index < 0 or from_index >= len(self.chapters):
            return False
        # to_index 允许等于 len(self.chapters)（追加到末尾）
        if to_index < 0 or to_index > len(self.chapters):
            return False
        if from_index == to_index:
            return True
        # 在每个 chapter 上标记旧 index（磁盘文件序号），用于后续文件重命名
        for c in self.chapters:
            c["_old_file_idx"] = c.get("index", 0)
        # 弹出并插入
        ch = self.chapters.pop(from_index)
        if to_index > from_index:
            insert_pos = to_index - 1
        else:
            insert_pos = to_index
        if insert_pos >= len(self.chapters):
            self.chapters.append(ch)
        else:
            self.chapters.insert(insert_pos, ch)
        # 重排文件名（用 _old_file_idx 找到磁盘文件，重命名为新序号）
        self._reorder_chapter_files()
        # 重排 index（在文件重命名完成后，更新 chapters 的 index 字段并清除临时标记）
        for i, c in enumerate(self.chapters):
            c["index"] = i + 1
            c.pop("_old_file_idx", None)
        # 同步 volumes：根据新的 chapters 顺序重建各卷的 chapters 列表
        if self.volumes:
            self._sync_volumes_after_reorder(from_vol, to_vol, from_index, to_index)
        self._dirty = True
        self._save_meta()
        return True

    def _reorder_chapter_files(self):
        """重排章节文件名（chapter_xxx.txt）以匹配新顺序。
        使用每个 chapter 上的 _old_file_idx 临时字段找到磁盘文件。
        为避免文件名冲突，先全部重命名为临时名再重命名为最终名。
        """
        import shutil
        ch_dir = os.path.join(self.project_dir, "chapters")
        if not os.path.exists(ch_dir):
            return
        # 1. 用旧 index 找到磁盘文件，备份到临时名
        temp_map = {}
        for i, c in enumerate(self.chapters):
            old_idx = c.get("_old_file_idx", i + 1)
            if old_idx <= 0:
                old_idx = i + 1
            src = os.path.join(ch_dir, f"chapter_{old_idx:03d}.txt")
            tmp = os.path.join(ch_dir, f".tmp_reorder_{i:04d}.txt")
            if os.path.exists(src):
                try:
                    shutil.move(src, tmp)
                    temp_map[i] = tmp
                except Exception:
                    pass
        # 2. 从临时名重命名为新序号（新序号 = i + 1）
        for i in range(len(self.chapters)):
            new_idx = i + 1
            tmp = temp_map.get(i)
            if tmp and os.path.exists(tmp):
                dst = os.path.join(ch_dir, f"chapter_{new_idx:03d}.txt")
                try:
                    shutil.move(tmp, dst)
                except Exception:
                    pass
        # 3. 清空章节缓存，避免键错位
        self._chapter_cache = {}
        self._snapshot_cache = None

    def _sync_volumes_after_reorder(self, from_vol: int, to_vol: int, from_index: int, to_index: int):
        """重排后重建 volumes 中的 chapters 列表。
        策略：基于 chapters 的新顺序，重新确定每个章节属于哪个卷。
        若 from_vol/to_vol 均提供，则按目标卷归属调整；否则保持原有卷归属关系（按比例分配）。
        """
        # 简化策略：保持原 volumes 的章节归属关系不变（章节编号已重新分配）
        # 这里采用：根据原 volumes 的章节数量比例，重新填充 chapters index
        if not self.volumes:
            return
        # 记录原各卷的章节数
        vol_counts = [len(v.get("chapters", [])) for v in self.volumes]
        total = sum(vol_counts)
        if total == 0 or total != len(self.chapters):
            # 数量不匹配，回退为：所有章节平均分配到第一卷
            self.volumes[0]["chapters"] = [i + 1 for i in range(len(self.chapters))]
            self.volumes[0]["chapter_count"] = len(self.chapters)
            for v in self.volumes[1:]:
                v["chapters"] = []
                v["chapter_count"] = 0
            return
        # 按 vol_counts 重新切片填充
        cursor = 0
        for vi, vol in enumerate(self.volumes):
            cnt = vol_counts[vi]
            vol["chapters"] = [cursor + j + 1 for j in range(cnt)]
            vol["chapter_count"] = cnt
            cursor += cnt
        # 若指定了跨卷移动，额外处理：将移动的章节从 from_vol 移到 to_vol
        # （此处的简化实现保留按比例分配，复杂跨卷场景由前端通过 volumes API 单独调整）

    def update_chapter_status(self, idx: int, status: str) -> bool:
        """更新章节状态：draft / revised / final"""
        if 0 <= idx < len(self.chapters):
            if status not in ("draft", "revised", "final"):
                return False
            self.chapters[idx]["status"] = status
            self._dirty = True
            self._save_meta()
            return True
        return False

    def update_chapter_pov(self, idx: int, pov: str) -> bool:
        """更新章节 POV 角色名"""
        if 0 <= idx < len(self.chapters):
            self.chapters[idx]["pov"] = pov or ""
            self._dirty = True
            self._save_meta()
            return True
        return False

    def update_chapter_scene_labels(self, idx: int, labels: list) -> bool:
        """更新章节场景标签"""
        if 0 <= idx < len(self.chapters):
            self.chapters[idx]["scene_labels"] = labels or []
            self._dirty = True
            self._save_meta()
            return True
        return False

    def get_planning_matrix(self) -> dict:
        """返回矩阵视图数据：卷 × 章节 × 字数 × 状态 × POV"""
        volumes = self.get_volumes() if hasattr(self, "get_volumes") else (self.volumes or [])
        chapters = []
        for i, ch in enumerate(self.chapters):
            self._normalize_chapter_fields(ch)
            chapters.append({
                "index": i,
                "chapter_index": ch.get("index", i + 1),
                "title": ch.get("title", ""),
                "word_count": ch.get("word_count", 0),
                "status": ch.get("status", "draft"),
                "pov": ch.get("pov", ""),
                "scene_labels": ch.get("scene_labels", []),
                "outline": ch.get("outline", ""),
            })
        # 统计
        total_words = sum(c["word_count"] for c in chapters)
        total_chapters = len(chapters)
        avg_words = int(total_words / total_chapters) if total_chapters > 0 else 0
        status_dist = {"draft": 0, "revised": 0, "final": 0}
        for c in chapters:
            s = c["status"] if c["status"] in status_dist else "draft"
            status_dist[s] += 1
        return {
            "volumes": volumes,
            "chapters": chapters,
            "stats": {
                "total_chapters": total_chapters,
                "total_words": total_words,
                "avg_words": avg_words,
                "status_distribution": status_dist,
            }
        }

    def get_planning_timeline(self) -> dict:
        """返回时间线视图数据：角色出场 × 伏笔埋设/回收 × 章节序号"""
        chapters = []
        for i, ch in enumerate(self.chapters):
            self._normalize_chapter_fields(ch)
            chapters.append({
                "index": i,
                "chapter_index": ch.get("index", i + 1),
                "title": ch.get("title", ""),
                "pov": ch.get("pov", ""),
                "scene_labels": ch.get("scene_labels", []),
            })
        # 从 ledger 提取角色出场 + 伏笔
        characters = []
        foreshadowing = []
        if self.ledger:
            # 角色状态：last_seen_chapter 作为出场章节
            for name, cs in self.ledger.character_states.items():
                characters.append({
                    "name": name,
                    "last_seen_chapter": cs.last_seen_chapter,
                    "location": cs.location,
                    "is_alive": cs.is_alive,
                })
            # 伏笔
            for h in self.ledger.foreshadowing:
                foreshadowing.append({
                    "id": h.id,
                    "content": h.content,
                    "planted_chapter": h.planted_chapter,
                    "expected_recovery_chapter": h.expected_recovery_chapter,
                    "status": h.status,
                    "related_characters": h.related_characters,
                })
        return {
            "chapters": chapters,
            "characters": characters,
            "foreshadowing": foreshadowing,
            "timeline_events": [],
        }

    def get_content(self, idx: int = None) -> str:
        if idx is None:
            idx = max(0, self.meta.get("current_chapter", 0))
        if 0 <= idx < len(self.chapters):
            ch_idx = self.chapters[idx]["index"]
            if ch_idx in self._chapter_cache and len(self._chapter_cache[ch_idx]) > 0:
                return self._chapter_cache[ch_idx]
            cf = os.path.join(self.project_dir, "chapters", f"chapter_{ch_idx:03d}.txt")
            txt_content = ""
            if os.path.exists(cf):
                try:
                    with open(cf, "r", encoding="utf-8") as f:
                        txt_content = f.read()
                except Exception as e:
                    logging.warning(f"[get_content] 读txt失败 idx={idx}: {e}")
            db_word_count = int(self.chapters[idx].get("word_count", 0) or 0)
            # ══ 自动修复：txt字数明显少于DB记录word_count，尝试从snapshots恢复 ══
            if (db_word_count > 200 and len(txt_content) < db_word_count * 0.5) or (
                db_word_count == 0 and ch_idx in self._chapter_cache and len(self._chapter_cache[ch_idx]) > 0
            ):
                recovered = None
                # 优先：_cache里有就用（内存是最新的）
                if ch_idx in self._chapter_cache and len(self._chapter_cache[ch_idx]) >= max(db_word_count, 50):
                    recovered = self._chapter_cache[ch_idx]
                else:
                    # 次选：snapshots目录里找最新的备份
                    snap_dir = os.path.join(self.project_dir, "snapshots")
                    if os.path.isdir(snap_dir):
                        snaps = sorted(
                            [fn for fn in os.listdir(snap_dir) if fn.startswith(f"chap{ch_idx:03d}_") and fn.endswith(".txt")],
                            reverse=True
                        )
                        for s in snaps:
                            sp = os.path.join(snap_dir, s)
                            try:
                                with open(sp, "r", encoding="utf-8") as f:
                                    cand = f.read()
                                if len(cand) >= max(db_word_count * 0.8, 100):
                                    recovered = cand
                                    break
                            except:
                                continue
                if recovered:
                    logging.info(f"[get_content] 自动修复：idx={idx} txt_len={len(txt_content)}<db_wc={db_word_count}, 从备份恢复len={len(recovered)}")
                    try:
                        os.makedirs(os.path.dirname(cf), exist_ok=True)
                        with open(cf, "w", encoding="utf-8") as f:
                            f.write(recovered)
                    except Exception as e:
                        logging.warning(f"[get_content] 自动修复写回txt失败: {e}")
                    self._chapter_cache[ch_idx] = recovered
                    return recovered
            self._chapter_cache[ch_idx] = txt_content
            return txt_content
        return ""

    def set_content(self, content: str, idx: int = None):
        if idx is None:
            logging.warning("[set_content] idx 为 None，拒绝保存（防止全局状态推断导致章节串写）")
            return
        if 0 <= idx < len(self.chapters):
            ch_idx = self.chapters[idx]["index"]

            old_content = self.get_content(idx)
            if old_content and old_content != content:
                snap_dir = os.path.join(self.project_dir, "snapshots")
                os.makedirs(snap_dir, exist_ok=True)
                snap_file = os.path.join(snap_dir,
                    f"chap{ch_idx:03d}_{time.strftime('%Y%m%d_%H%M%S')}.txt")
                try:
                    with open(snap_file, "w", encoding="utf-8") as f:
                        f.write(old_content)
                except Exception as e:
                    logging.warning(f"[set_content] 快照写入失败: {e}")
                self._snapshot_cache = None

            self._chapter_cache[ch_idx] = content
            self.chapters[idx]["word_count"] = len(content)
            self.chapters[idx]["modified"] = time.strftime("%Y-%m-%d %H:%M")
            self._dirty = True

            cf = os.path.join(self.project_dir, "chapters", f"chapter_{ch_idx:03d}.txt")
            from backend.storage_transaction import TransactionContext
            tx = TransactionContext(self)
            with tx:
                tx.register_file_write(cf, content)
                tx.mark_sqlite_dirty()

    def get_previous_context(self, chars: int = 0, chapter_index: int = None) -> str:
        if chapter_index is not None:
            cidx = chapter_index
        else:
            cidx = max(0, self.meta.get("current_chapter", 0))
        if cidx <= 0: return ""
        prev = self.get_content(cidx - 1)
        if chars and chars > 0:
            return prev[-chars:] if len(prev) > chars else prev
        return prev

    # ── Snapshots ──

    def get_snapshots(self, idx: int = None) -> List[Dict]:
        if self._snapshot_cache is not None:
            return self._snapshot_cache
        if idx is None:
            idx = max(0, self.meta.get("current_chapter", 0))
        if 0 <= idx < len(self.chapters):
            ch_idx = self.chapters[idx]["index"]
            snap_dir = os.path.join(self.project_dir, "snapshots")
            snaps = []
            if os.path.exists(snap_dir):
                for fname in sorted(os.listdir(snap_dir), reverse=True):
                    if fname.startswith(f"chap{ch_idx:03d}_"):
                        fpath = os.path.join(snap_dir, fname)
                        snaps.append({
                            "file": fname,
                            "time": fname.replace(f"chap{ch_idx:03d}_", "").replace(".txt", ""),
                            "size": os.path.getsize(fpath)
                        })
            self._snapshot_cache = snaps
            return snaps
        return []

    def restore_snapshot(self, idx: int, snapshot_file: str) -> bool:
        snap_dir = os.path.join(self.project_dir, "snapshots")
        src = os.path.join(snap_dir, snapshot_file)
        if not self._is_safe_path(snap_dir, src):
            return False
        if os.path.exists(src) and os.path.isfile(src):
            with open(src, "r", encoding="utf-8") as f:
                content = f.read()
            self.set_content(content, idx)
            self._snapshot_cache = None
            return True
        return False