# -*- coding: utf-8 -*-
"""TruthLedger 快照管理方法（从 ledger.py 拆分）"""
import json, os, logging
from dataclasses import asdict
from backend.models.ledger_models import CharacterState, Foreshadowing, ChapterLog, Artifact, Faction, Location

logger = logging.getLogger(__name__)


class LedgerSnapshotMixin:
    """提供快照创建、恢复、列表管理"""

    def take_snapshot(self, chapter_idx: int) -> dict:
        """7.1 创建叙事状态快照，保存到项目/snapshots/目录"""
        import time
        import uuid
        snapshots_dir = os.path.join(self.project_dir, "snapshots")
        os.makedirs(snapshots_dir, exist_ok=True)
        index_file = os.path.join(snapshots_dir, "_index.json")

        # 读取已有快照版本号
        existing = [f for f in os.listdir(snapshots_dir) if f.endswith('.json') and f != '_index.json']
        version = len(existing) + 1
        snapshot_id = uuid.uuid4().hex[:12]
        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")

        snapshot_data = {
            "snapshot_id": snapshot_id,
            "version": version,
            "timestamp": timestamp,
            "chapter": chapter_idx,
            "data": {
                "character_states": {k: asdict(cs) for k, cs in self.character_states.items()},
                "foreshadowing": [asdict(f) for f in self.foreshadowing],
                "chapter_logs": [asdict(cl) for cl in self.chapter_logs],
                "artifacts": {k: asdict(a) for k, a in self.artifacts.items()},
                "factions": {k: asdict(f) for k, f in self.factions.items()},
                "locations": {k: asdict(l) for k, l in self.locations.items()},
            },
        }

        filename = f"v{version}_{timestamp}.json"
        filepath = os.path.join(snapshots_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(snapshot_data, f, ensure_ascii=False, indent=2)

        # 更新索引文件
        self._update_snapshot_index(snapshots_dir, {
            "snapshot_id": snapshot_id,
            "version": version,
            "timestamp": timestamp,
            "chapter": chapter_idx,
            "file": filename,
        })

        return snapshot_data

    def _update_snapshot_index(self, snapshots_dir: str, entry: dict):
        """更新快照索引文件 _index.json"""
        index_file = os.path.join(snapshots_dir, "_index.json")
        index = []
        if os.path.exists(index_file):
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    index = json.load(f)
                if not isinstance(index, list):
                    index = []
            except Exception:
                index = []
        index.append(entry)
        # 按 version 降序排列
        index.sort(key=lambda x: x.get("version", 0), reverse=True)
        try:
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _rebuild_snapshot_index(self, snapshots_dir: str):
        """重建快照索引文件（从所有快照文件中扫描）"""
        index = []
        if not os.path.isdir(snapshots_dir):
            return index
        for f in sorted(os.listdir(snapshots_dir), reverse=True):
            if f.endswith('.json') and f != '_index.json':
                fpath = os.path.join(snapshots_dir, f)
                try:
                    with open(fpath, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    index.append({
                        "snapshot_id": data.get("snapshot_id", ""),
                        "version": data.get("version", 0),
                        "timestamp": data.get("timestamp", ""),
                        "chapter": data.get("chapter", 0),
                        "file": f,
                    })
                except Exception:
                    pass
        index_file = os.path.join(snapshots_dir, "_index.json")
        try:
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return index

    def list_snapshots(self) -> list:
        """列出所有快照元信息（优先读索引文件，不存在则重建）"""
        snapshots_dir = os.path.join(self.project_dir, "snapshots")
        if not os.path.isdir(snapshots_dir):
            return []
        index_file = os.path.join(snapshots_dir, "_index.json")
        # 优先读取索引文件
        if os.path.exists(index_file):
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    index = json.load(f)
                if isinstance(index, list):
                    return index
            except Exception:
                pass
        # 索引文件不存在或损坏，重建
        return self._rebuild_snapshot_index(snapshots_dir)

    def restore_snapshot(self, snapshot_id_or_file: str, backup_current: bool = True) -> bool:
        """从快照恢复 ledger 数据

        Args:
            snapshot_id_or_file: 快照 ID 或文件名
            backup_current: 恢复前是否自动备份当前状态（默认 True，防止误操作不可逆）
        """
        snapshots_dir = os.path.join(self.project_dir, "snapshots")
        filepath = os.path.join(snapshots_dir, snapshot_id_or_file)
        if not os.path.exists(filepath):
            # 按 snapshot_id 查找
            for f in os.listdir(snapshots_dir):
                if f.endswith('.json'):
                    fpath = os.path.join(snapshots_dir, f)
                    try:
                        with open(fpath, "r", encoding="utf-8") as fh:
                            data = json.load(fh)
                        if data.get("snapshot_id") == snapshot_id_or_file:
                            filepath = fpath
                            break
                    except Exception:
                        pass
        if not os.path.exists(filepath):
            return False
        with open(filepath, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        data = snapshot.get("data", {})

        # 恢复前先自动快照当前状态，防止误操作不可逆
        if backup_current:
            try:
                self.take_snapshot(chapter_idx=data.get("chapter", 0))
            except Exception:
                pass

        # 恢复各字段
        from dataclasses import fields as dc_fields
        if "character_states" in data:
            self.character_states.clear()
            for name, cs_dict in data["character_states"].items():
                self.character_states[name] = CharacterState(**{
                    k: v for k, v in cs_dict.items()
                    if k in {f.name for f in dc_fields(CharacterState)}
                })
        if "foreshadowing" in data:
            self.foreshadowing = [
                Foreshadowing(**{
                    k: v for k, v in f.items()
                    if k in {f2.name for f2 in dc_fields(Foreshadowing)}
                }) for f in data["foreshadowing"]
            ]
        if "chapter_logs" in data:
            self.chapter_logs = [
                ChapterLog(**{
                    k: v for k, v in cl.items()
                    if k in {f2.name for f2 in dc_fields(ChapterLog)}
                }) for cl in data["chapter_logs"]
            ]
        if "artifacts" in data:
            self.artifacts.clear()
            artifacts_data = data["artifacts"]
            if isinstance(artifacts_data, list):
                for a in artifacts_data:
                    obj = Artifact(**{
                        k: v for k, v in a.items()
                        if k in {f2.name for f2 in dc_fields(Artifact)}
                    })
                    self.artifacts[obj.id] = obj
            else:
                for aid, a in artifacts_data.items():
                    self.artifacts[aid] = Artifact(**{
                        k: v for k, v in a.items()
                        if k in {f2.name for f2 in dc_fields(Artifact)}
                    })
        if "factions" in data:
            self.factions.clear()
            factions_data = data["factions"]
            if isinstance(factions_data, list):
                for f in factions_data:
                    obj = Faction(**{
                        k: v for k, v in f.items()
                        if k in {f2.name for f2 in dc_fields(Faction)}
                    })
                    self.factions[obj.id] = obj
            else:
                for fid, f in factions_data.items():
                    self.factions[fid] = Faction(**{
                        k: v for k, v in f.items()
                        if k in {f2.name for f2 in dc_fields(Faction)}
                    })
        if "locations" in data:
            self.locations.clear()
            locations_data = data["locations"]
            if isinstance(locations_data, list):
                for loc in locations_data:
                    obj = Location(**{
                        k: v for k, v in loc.items()
                        if k in {f2.name for f2 in dc_fields(Location)}
                    })
                    self.locations[obj.id] = obj
            else:
                for lid, loc in locations_data.items():
                    self.locations[lid] = Location(**{
                        k: v for k, v in loc.items()
                        if k in {f2.name for f2 in dc_fields(Location)}
                    })

        self.save()
        return True
