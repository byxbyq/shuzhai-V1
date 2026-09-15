# -*- coding: utf-8 -*-
"""书斋 V65 - 结构化世界观设定"""
import json, os
from typing import Dict, List, Optional

class WorldSettings:
    """结构化世界观 — 不是平坦 key-value，是有 schema 的事实源"""

    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.magic_system = {"name": "", "rules": [], "realms": []}
        self.forces: List[Dict] = []           # [{name, territory, attitude, description}]
        self.locations: List[Dict] = []        # [{name, type, description, first_seen_chapter}]
        self.items: List[Dict] = []            # [{name, nature, description, first_seen_chapter, status}]
        self.hard_constraints: List[str] = []  # ["凡境不可伤灵台境", "丹药需药引"]
        self.freeform: Dict[str, str] = {}     # 未结构化的设定捕获
        # 结构化世界观字段（五阶模板第一步）
        self.narrative_style: Dict = {          # 叙事风格
            "pov": "",            # 叙事视角: 第三人称限知/第一人称/全知
            "tense": "",          # 时态: 过去时/现在时
            "tone": "",           # 基调: 冷峻/热血/诙谐/沉重
            "pacing": "",         # 节奏: 快节奏/慢热/张弛有度
            "description_style": ""  # 描写风格: 白描/华丽/意识流
        }
        self.era: Dict = {                       # 时代环境
            "tech_level": "",    # 科技水平: 冷兵器/蒸汽/现代
            "society": "",       # 社会制度: 封建帝制/共和/部落
            "geography": "",     # 地理特征
            "culture": "",       # 文化背景
            "social_attitude": ""  # 社会态度: 普通人对超凡力量的态度（崇拜/恐惧/管控/猎杀，以及由此产生的社会规则）
        }
        self.world_rules: List[str] = []         # 通用世界规则（扩展hard_constraints）
        self.world_settings: Dict = {}            # 自由格式核心设定
        self.pinned: List[Dict] = []              # 故事圣经钉选（第5批：必须遵守项）
        self._load()

    @property
    def _file(self): return os.path.join(self.project_dir, "world_meta.json")

    def _load(self):
        """从 SQLite 加载（优先），回退到 JSON"""
        # 优先：SQLite
        try:
            from backend.db import ProjectDB, has_db
            if has_db(self.project_dir):
                db = ProjectDB.get(self.project_dir)
                d = db.load_world()
                if d is not None:
                    self._load_from_dict(d)
                    return
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[WorldSettings] SQLite 加载失败，回退 JSON: {e}")

        # 回退：JSON
        if os.path.exists(self._file):
            with open(self._file, 'r', encoding='utf-8') as f:
                d = json.load(f)
            self._load_from_dict(d)

    def _load_from_dict(self, d: dict):
        """从 dict 填充内存字段（SQLite 和 JSON 共用）"""
        self.magic_system = d.get("magic_system", self.magic_system)
        self.forces = d.get("forces", [])
        self.locations = d.get("locations", [])
        self.items = d.get("items", [])
        self.hard_constraints = d.get("hard_constraints", [])
        self.freeform = d.get("freeform", {})
        self.narrative_style = d.get("narrative_style", self.narrative_style)
        self.era = d.get("era", self.era)
        self.world_rules = d.get("world_rules", [])
        self.world_settings = d.get("world_settings", {})
        self.pinned = d.get("pinned", [])

    def save(self):
        """保存到 SQLite（优先），回退到 JSON"""
        # 保护 narrative_style 和 era：如果内存中全为空但存储中有值，保留存储中的值
        self._protect_fields()

        data = {
            "magic_system": self.magic_system,
            "forces": self.forces,
            "locations": self.locations,
            "items": self.items,
            "hard_constraints": self.hard_constraints,
            "freeform": self.freeform,
            "narrative_style": self.narrative_style,
            "era": self.era,
            "world_rules": self.world_rules,
            "world_settings": self.world_settings,
            "pinned": self.pinned,
        }

        # 优先写 SQLite
        try:
            from backend.db import ProjectDB, has_db
            if has_db(self.project_dir):
                db = ProjectDB.get(self.project_dir)
                db.save_world(data)
                return
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[WorldSettings] SQLite 保存失败，回退 JSON: {e}")

        # 回退写 JSON
        try:
            if os.path.exists(self._file):
                import shutil as _shutil
                _shutil.copy2(self._file, self._file + '.bak')
        except Exception:
            pass
        with open(self._file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _protect_fields(self):
        """如果内存中 narrative_style/era 全为空但存储中有非空值，从存储恢复"""
        disk = None
        # 优先从 SQLite 读取
        try:
            from backend.db import ProjectDB, has_db
            if has_db(self.project_dir):
                db = ProjectDB.get(self.project_dir)
                disk = db.load_world()
        except Exception:
            pass

        # 回退：从 JSON 读取
        if disk is None and os.path.exists(self._file):
            try:
                with open(self._file, 'r', encoding='utf-8') as f:
                    disk = json.load(f)
            except Exception:
                pass

        if disk is None:
            return

        # 检查 narrative_style
        if self._is_all_empty(self.narrative_style):
            disk_ns = disk.get("narrative_style", {})
            if not self._is_all_empty(disk_ns):
                self.narrative_style = disk_ns
        # 检查 era
        if self._is_all_empty(self.era):
            disk_era = disk.get("era", {})
            if not self._is_all_empty(disk_era):
                self.era = disk_era

    @staticmethod
    def _is_all_empty(d):
        """检查字典是否所有值都为空"""
        if not d or not isinstance(d, dict):
            return True
        return all(not v for v in d.values())

    def add_force(self, name: str, territory: str = "", attitude: str = "", description: str = ""):
        self.forces.append({"name": name, "territory": territory, "attitude": attitude, "description": description})
        self.save()

    def add_location(self, name: str, loc_type: str = "", description: str = "", chapter: int = 0):
        self.locations.append({"name": name, "type": loc_type, "description": description, "first_seen_chapter": chapter})
        self.save()

    def add_item(self, name: str, nature: str = "", description: str = "", chapter: int = 0):
        self.items.append({"name": name, "nature": nature, "description": description, "first_seen_chapter": chapter, "status": "active"})
        self.save()

    def add_constraint(self, rule: str):
        if rule not in self.hard_constraints:
            self.hard_constraints.append(rule)
            self.save()

    def get_force(self, idx: int) -> Optional[Dict]:
        if 0 <= idx < len(self.forces):
            return self.forces[idx]
        return None

    def update_force(self, idx: int, **kwargs) -> bool:
        if 0 <= idx < len(self.forces):
            for k, v in kwargs.items():
                if k in self.forces[idx]:
                    self.forces[idx][k] = v
            self.save()
            return True
        return False

    def delete_force(self, idx: int) -> bool:
        if 0 <= idx < len(self.forces):
            del self.forces[idx]
            self.save()
            return True
        return False

    def get_item(self, idx: int) -> Optional[Dict]:
        if 0 <= idx < len(self.items):
            return self.items[idx]
        return None

    def update_item(self, idx: int, **kwargs) -> bool:
        if 0 <= idx < len(self.items):
            for k, v in kwargs.items():
                if k in self.items[idx]:
                    self.items[idx][k] = v
            self.save()
            return True
        return False

    def delete_item(self, idx: int) -> bool:
        if 0 <= idx < len(self.items):
            del self.items[idx]
            self.save()
            return True
        return False

    def get_location(self, idx: int) -> Optional[Dict]:
        if 0 <= idx < len(self.locations):
            return self.locations[idx]
        return None

    def update_location(self, idx: int, **kwargs) -> bool:
        if 0 <= idx < len(self.locations):
            for k, v in kwargs.items():
                if k in self.locations[idx]:
                    self.locations[idx][k] = v
            self.save()
            return True
        return False

    def delete_location(self, idx: int) -> bool:
        if 0 <= idx < len(self.locations):
            del self.locations[idx]
            self.save()
            return True
        return False

    def to_prompt(self) -> str:
        """生成注入 AI prompt 的结构化文本"""
        parts = []
        # 故事圣经钉选（第5批）：置顶输出，强调必须遵守
        if self.pinned:
            pinned_lines = []
            for p in self.pinned:
                if isinstance(p, dict):
                    text = p.get("text", "") or p.get("content", "")
                    tag = p.get("source", "")
                    if text:
                        pinned_lines.append(f"- [钉选·{tag}] {text}" if tag else f"- [钉选] {text}")
                elif isinstance(p, str):
                    pinned_lines.append(f"- [钉选] {p}")
            if pinned_lines:
                parts.append("## 故事圣经（钉选·必须遵守）\n" + "\n".join(pinned_lines))

        # 叙事风格（结构化优先）
        ns = self.narrative_style
        ns_items = []
        if ns.get("pov"): ns_items.append(f"视角: {ns['pov']}")
        if ns.get("tense"): ns_items.append(f"时态: {ns['tense']}")
        if ns.get("tone"): ns_items.append(f"基调: {ns['tone']}")
        if ns.get("pacing"): ns_items.append(f"节奏: {ns['pacing']}")
        if ns.get("description_style"): ns_items.append(f"描写: {ns['description_style']}")
        if ns_items:
            parts.append("## 叙事风格\n" + " | ".join(ns_items))

        # 时代环境
        era = self.era
        era_items = []
        if era.get("tech_level"): era_items.append(f"科技: {era['tech_level']}")
        if era.get("society"): era_items.append(f"社会: {era['society']}")
        if era.get("geography"): era_items.append(f"地理: {era['geography']}")
        if era.get("culture"): era_items.append(f"文化: {era['culture']}")
        if era.get("social_attitude"): era_items.append(f"社会态度: {era['social_attitude']}")
        if era_items:
            parts.append("## 时代环境\n" + " | ".join(era_items))

        # 灵力体系
        if self.magic_system.get("name"):
            parts.append(f"## 灵力体系\n名称: {self.magic_system['name']}")
            if self.magic_system.get("rules"):
                parts.append("规则: " + "; ".join(self.magic_system["rules"]))
            if self.magic_system.get("realms"):
                parts.append("境界: " + " → ".join(self.magic_system["realms"]))

        # 世界规则（通用）+ 硬约束（体系专属）
        all_rules = list(self.world_rules) + list(self.hard_constraints)
        if all_rules:
            rule_lines = []
            for r in all_rules:
                if isinstance(r, dict):
                    k = r.get('key', '')
                    v = r.get('val', '')
                    rule_lines.append(f"- {k}：{v}" if k else f"- {v}")
                elif isinstance(r, str):
                    rule_lines.append(f"- {r}")
            parts.append("## 世界规则\n" + "\n".join(rule_lines))

        # world_settings（自由格式设定）
        if self.world_settings and isinstance(self.world_settings, dict):
            ws_lines = []
            for k, v in self.world_settings.items():
                ws_lines.append(f"- {k}：{v}")
            parts.append("## 核心设定\n" + "\n".join(ws_lines))

        if self.forces:
            parts.append("## 势力\n" + "\n".join(
                f"- {f['name']}: 领地[{f.get('territory','')}] 态度[{f.get('attitude','')}]"
                for f in self.forces
            ))

        if self.items:
            parts.append("## 关键物品\n" + "\n".join(
                f"- {i['name']}({i.get('nature','')}): {i.get('description','')} [首现第{i.get('first_seen_chapter',0)}章]"
                for i in self.items
            ))

        # freeform 兜底：跳过已被结构化字段覆盖的 key
        _covered_keys = {"整体风格", "时代背景", "核心设定", "氛围基调", "叙事风格", "时代环境", "世界规则"}
        extra = {k: v for k, v in self.freeform.items() if k not in _covered_keys}
        if extra:
            parts.append("## 其他设定\n" + "\n".join(f"- {k}: {v}" for k, v in extra.items()))

        return "\n\n".join(parts) if parts else ""

    def get_stats(self) -> dict:
        ns = self.narrative_style
        era = self.era
        return {
            "magic_system": bool(self.magic_system.get("name")),
            "forces": len(self.forces),
            "locations": len(self.locations),
            "items": len(self.items),
            "constraints": len(self.hard_constraints),
            "freeform_entries": len(self.freeform),
            "narrative_style": sum(1 for v in ns.values() if v),
            "era": sum(1 for v in era.values() if v),
            "world_rules": len(self.world_rules),
            "pinned": len(self.pinned),
        }

    # ── 故事圣经钉选（第5批） ──

    def pin(self, text: str, source: str = "") -> Dict:
        """钉选一条设定：必须遵守项置顶注入 prompt"""
        entry = {
            "id": f"pin_{len(self.pinned) + 1}_{int(__import__('time').time())}",
            "text": text,
            "source": source,
            "created": __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        # 去重：同文本不重复钉
        for p in self.pinned:
            if isinstance(p, dict) and p.get("text") == text:
                return p
        self.pinned.append(entry)
        self.save()
        return entry

    def unpin(self, pin_id: str) -> bool:
        """取消钉选"""
        for i, p in enumerate(self.pinned):
            if isinstance(p, dict) and p.get("id") == pin_id:
                del self.pinned[i]
                self.save()
                return True
        return False

    def list_pinned(self) -> List[Dict]:
        """列出全部钉选项"""
        return list(self.pinned)
