# -*- coding: utf-8 -*-
"""
书斋 V66 — 分镜 IR 中间层 (SB-0)
将分镜生成全流程中的数据结构抽象为强类型 IR（中间表示），
解耦 AI 返回的原始 dict ↔ 业务代码。

同时包含：
  SB-2 角色分层权重 — CharacterLayer, ShotCharacter
  SB-3 世界观冲突过滤 — WorldRule, WorldRuleSet, ConflictReport
  SB-4 Token 自适应裁剪 — token_estimator, AdaptiveTrimmer
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────
# SB-0: IR 数据类型
# ──────────────────────────────────────────────────

# ── 枚举约束（集中管理，替代散落在各处的字面量集合） ──

VALID_SHOT_TYPES = frozenset({"远景", "全景", "中景", "近景", "特写", "大特写", "POV"})
VALID_MOVEMENTS   = frozenset({"推镜", "拉镜", "平移", "俯仰", "静态", "跟拍", "环绕", "摇镜"})
VALID_TRANSITIONS = frozenset({"切", "淡入", "淡出", "叠化", "划像", "闪白", "无"})

DENSITY_MAP = {"sparse": 300, "medium": 150, "dense": 80}
STYLE_NOTES = {
    "写实电影": "写实电影风格，自然光照，胶片质感，电影级构图，真实环境纹理细节",
    "动漫":     "日本动画风格，干净线条，鲜明色块，吉卜力/新海诚式光影，手绘质感",
    "水墨":     "中国传统水墨画风格，墨色浓淡，留白意境，宣纸纹理，写意笔触",
    "赛博朋克": "赛博朋克风格，霓虹灯光，湿滑街道反射，全息投影，机械义体，高对比度冷色调",
    "默认":     "电影级画质，自然光影，真实材质，史诗感构图",
}

TOOL_GUIDE = {
    "kling":  {"lang": "中文详述",       "tip": "使用中文进行细致描述，突出画面构图、角色神态、氛围意境。关键词部分用中文短语。"},
    "sora":   {"lang": "英文物理描述",   "tip": "Use English physical descriptions. Focus on realistic physics, material properties, camera optics, lighting physics. Short keywords in English."},
    "jimeng": {"lang": "中文+风格标签",   "tip": "中文核心描述 + 英文风格标签。例如：'一位侠客在竹林中持剑，雾气弥漫' + cinematic lighting, bamboo forest, mist, dynamic pose"},
    "通用":   {"lang": "中文详述",       "tip": "使用中文详述，兼容主流AI视频工具。画面描述具体、光影明确、动作清晰。"},
}


@dataclass
class StoryboardShot:
    """单个分镜镜头（13 字段强类型）"""
    index: int
    source_text: str = ""
    shot_type: str = "中景"
    camera_movement: str = "静态"
    duration_sec: float = 4.0
    transition: str = "切"
    lighting: str = "正面自然光，色温5500K，中等强度"
    color_palette: str = "#FFFFFF #000000 #808080"
    character_positions: List[Dict[str, str]] = field(default_factory=list)
    scene_description: str = ""
    sound_design: str = "环境音（自然氛围）+ 音效（无）+ 配乐情绪（中性）"
    prompt_full: str = ""
    prompt_short: str = ""
    # SB-7 跨镜头状态继承：从上一镜延续的伤势/服饰/道具等状态
    carried_state: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "source_text": self.source_text,
            "shot_type": self.shot_type,
            "camera_movement": self.camera_movement,
            "duration_sec": self.duration_sec,
            "transition": self.transition,
            "lighting": self.lighting,
            "color_palette": self.color_palette,
            "character_positions": self.character_positions,
            "scene_description": self.scene_description,
            "sound_design": self.sound_design,
            "prompt_full": self.prompt_full,
            "prompt_short": self.prompt_short,
            "carried_state": self.carried_state,
        }


@dataclass
class StoryboardGlobalStyle:
    style_preset: str = "默认"
    target_tool: str   = "通用"
    shot_density: str  = "medium"
    language: str      = "zh"

    @property
    def style_note(self) -> str:
        return STYLE_NOTES.get(self.style_preset, STYLE_NOTES["默认"])

    @property
    def tool_guide(self) -> dict:
        return TOOL_GUIDE.get(self.target_tool, TOOL_GUIDE["通用"])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "style_preset": self.style_preset,
            "target_tool": self.target_tool,
            "shot_density": self.shot_density,
            "language": self.language,
            "style_notes": self.style_note,
            "tool_guide": self.tool_guide,
        }


@dataclass
class StoryboardIR:
    """分镜完整 IR"""
    storyboard_id: str
    shots: List[StoryboardShot] = field(default_factory=list)
    global_style: StoryboardGlobalStyle = field(default_factory=StoryboardGlobalStyle)
    warnings: List[str] = field(default_factory=list)
    # SB-3 世界观冲突报告
    world_conflicts: List[ConflictReport] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "storyboard_id": self.storyboard_id,
            "shots": [s.to_dict() for s in self.shots],
            "global_style": self.global_style.to_dict(),
        }
        if self.warnings:
            d["warnings"] = self.warnings
        if self.world_conflicts:
            d["world_conflicts"] = [c.to_dict() for c in self.world_conflicts]
        return d


# ──────────────────────────────────────────────────
# SB-0: IR 构建器（dict → IR，含校验与默认值）
# ──────────────────────────────────────────────────

class StoryboardIRBuilder:
    """将 AI 返回的原始 dict / JSON 字符串转换为 StoryboardIR"""

    @staticmethod
    def parse_raw(raw: str) -> List[dict]:
        """三层容错解析原始 AI 返回文本 → dict 列表"""
        cleaned = raw.strip()

        # 策略1：去代码块标记
        if "```" in cleaned:
            match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1).strip()
            else:
                cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
                cleaned = re.sub(r'\s*```$', '', cleaned)

        # 策略2：提取方括号段
        start_idx = cleaned.find('[')
        end_idx = cleaned.rfind(']')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            cleaned = cleaned[start_idx:end_idx + 1]

        # 策略3：直接解析
        try:
            shots = json.loads(cleaned)
            if isinstance(shots, list):
                return shots
        except json.JSONDecodeError:
            pass

        # 策略4：逐个对象兜底
        return StoryboardIRBuilder._extract_objects_fallback(cleaned)

    @staticmethod
    def _extract_objects_fallback(text: str) -> list:
        objects = []
        depth = 0
        start = -1
        for i, ch in enumerate(text):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start != -1:
                    try:
                        obj = json.loads(text[start:i + 1])
                        objects.append(obj)
                    except json.JSONDecodeError:
                        pass
                    start = -1
        return objects

    @staticmethod
    def validate_shot(raw: dict, expected_index: int) -> StoryboardShot:
        """校验并补全单镜头字段 → StoryboardShot"""

        def _clamp_duration(seconds) -> float:
            try:
                return max(2.0, min(10.0, float(seconds)))
            except (TypeError, ValueError):
                return 4.0

        shot_type = raw.get("shot_type", "中景")
        camera_movement = raw.get("camera_movement", "静态")
        transition = raw.get("transition", "切")

        cp = raw.get("character_positions", [])
        if not isinstance(cp, list):
            cp = []

        return StoryboardShot(
            index=raw.get("index", expected_index),
            source_text=raw.get("source_text", ""),
            shot_type=shot_type if shot_type in VALID_SHOT_TYPES else "中景",
            camera_movement=camera_movement if camera_movement in VALID_MOVEMENTS else "静态",
            duration_sec=_clamp_duration(raw.get("duration_sec", 4.0)),
            transition=transition if transition in VALID_TRANSITIONS else "切",
            lighting=raw.get("lighting", "正面自然光，色温5500K，中等强度"),
            color_palette=raw.get("color_palette", "#FFFFFF #000000 #808080"),
            character_positions=cp,
            scene_description=raw.get("scene_description", ""),
            sound_design=raw.get("sound_design", "环境音（自然氛围）+ 音效（无）+ 配乐情绪（中性）"),
            prompt_full=raw.get("prompt_full", raw.get("scene_description", "")),
            prompt_short=raw.get("prompt_short", ""),
        )

    @classmethod
    def build(cls, storyboard_id: str, raw_text: str,
              options: dict) -> StoryboardIR:
        """主入口：原始 AI 返回 → StoryboardIR"""
        raw_shots = cls.parse_raw(raw_text)
        shots = [cls.validate_shot(s, i + 1) for i, s in enumerate(raw_shots)
                 if isinstance(s, dict)]

        global_style = StoryboardGlobalStyle(
            style_preset=options.get("style_preset", "默认"),
            target_tool=options.get("target_tool", "通用"),
            shot_density=options.get("shot_density", "medium"),
            language=options.get("language", "zh"),
        )

        ir = StoryboardIR(
            storyboard_id=storyboard_id,
            shots=shots,
            global_style=global_style,
        )
        return ir


# ──────────────────────────────────────────────────
# SB-2: 角色分层权重
# ──────────────────────────────────────────────────

@dataclass
class CharacterLayer:
    """单个角色的分层信息"""
    name: str                          # 角色名
    tier: int = 1                      # 1=主角, 2=主要配角, 3=次要配角, 4=龙套
    weight: float = 1.0                # 该角色在 prompt 中的描述权重（1.0=标准）
    visual_traits: str = ""            # 关键视觉特征（如"银发、红瞳、常穿黑色斗篷"）
    current_emotion: str = ""          # 当前情绪状态
    is_present: bool = True            # 当前场景是否出场

    @property
    def tier_label(self) -> str:
        labels = {1: "主角", 2: "主要配角", 3: "次要配角", 4: "龙套"}
        return labels.get(self.tier, "未知")

    def prompt_fragment(self) -> str:
        """生成该角色在 prompt 中的描述片段，权重越高越详细"""
        if not self.is_present:
            return ""
        parts = [self.name]
        if self.visual_traits:
            parts.append(f"（{self.visual_traits}）")
        if self.current_emotion:
            parts.append(f"情绪：{self.current_emotion}")
        base = " ".join(parts)

        # 权重影响详细度
        if self.weight >= 1.5 and self.tier <= 2:
            return f"【重点】{base}，需在画面中突出表现"
        elif self.weight >= 1.0:
            return f"{base}，正常表现"
        elif self.weight >= 0.5:
            return f"{base}，可简化描绘"
        else:
            return f"{base}，仅作背景存在"


class CharacterRegistry:
    """角色注册表：管理所有已知角色及其分层信息"""

    def __init__(self):
        self._chars: Dict[str, CharacterLayer] = {}

    def register(self, layer: CharacterLayer):
        self._chars[layer.name] = layer

    def get(self, name: str) -> Optional[CharacterLayer]:
        return self._chars.get(name)

    def get_present_characters(self) -> List[CharacterLayer]:
        """返回当前出场的角色，按 tier 升序、weight 降序"""
        present = [c for c in self._chars.values() if c.is_present]
        return sorted(present, key=lambda c: (c.tier, -c.weight))

    def build_character_prompt_block(self) -> str:
        """生成"角色分层描述" prompt 块"""
        present = self.get_present_characters()
        if not present:
            return ""
        lines = ["## 角色分层描述"]
        for c in present:
            frag = c.prompt_fragment()
            if frag:
                lines.append(f"- {frag}")
        lines.append("主角应在画面构图、光影和镜头时长上获得更多侧重。")
        return "\n".join(lines)

    def __len__(self):
        return len(self._chars)


# ──────────────────────────────────────────────────
# SB-3: 世界观冲突过滤
# ──────────────────────────────────────────────────

@dataclass
class WorldRule:
    """单条世界观规则"""
    rule_id: str
    domain: str                      # 规则域：physics / culture / magic / technology / creature
    description: str                 # 规则描述
    severity: str = "error"          # error=硬冲突, warning=软冲突
    check_keywords: List[str] = field(default_factory=list)  # 触发检查的关键词

    def check(self, shot: StoryboardShot) -> Optional[ConflictReport]:
        """检查镜头是否违反本条世界观规则"""
        # 合并所有可检查的文本
        text = " ".join([
            shot.scene_description,
            shot.prompt_full,
            shot.lighting,
            shot.sound_design,
        ])

        # 关键词匹配
        triggered = any(kw in text for kw in self.check_keywords)
        if not triggered:
            return None

        return ConflictReport(
            shot_index=shot.index,
            rule_id=self.rule_id,
            domain=self.domain,
            description=self.description,
            severity=self.severity,
            match_text=self._extract_context(text, self.check_keywords),
        )

    @staticmethod
    def _extract_context(text: str, keywords: List[str]) -> str:
        for kw in keywords:
            idx = text.find(kw)
            if idx >= 0:
                start = max(0, idx - 20)
                end = min(len(text), idx + len(kw) + 20)
                return f"…{text[start:end]}…"
        return ""


@dataclass
class ConflictReport:
    """世界观冲突报告"""
    shot_index: int
    rule_id: str
    domain: str
    description: str
    severity: str  # error | warning
    match_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_index": self.shot_index,
            "rule_id": self.rule_id,
            "domain": self.domain,
            "description": self.description,
            "severity": self.severity,
            "match_text": self.match_text,
        }


class WorldRuleSet:
    """世界观规则集"""

    def __init__(self):
        self.rules: List[WorldRule] = []

    def add_rule(self, rule: WorldRule):
        self.rules.append(rule)

    def add_rules(self, rules: List[WorldRule]):
        self.rules.extend(rules)

    def check_all(self, ir: StoryboardIR) -> List[ConflictReport]:
        """对所有镜头执行全部规则检查"""
        reports: List[ConflictReport] = []
        for shot in ir.shots:
            for rule in self.rules:
                report = rule.check(shot)
                if report:
                    reports.append(report)
        return reports

    def filter_errors(self, reports: List[ConflictReport]) -> List[ConflictReport]:
        return [r for r in reports if r.severity == "error"]

    def filter_warnings(self, reports: List[ConflictReport]) -> List[ConflictReport]:
        return [r for r in reports if r.severity == "warning"]

    def build_conflict_prompt_block(self, reports: List[ConflictReport]) -> str:
        """根据冲突报告生成"世界观约束" prompt 块"""
        if not reports:
            return ""
        lines = ["## 世界观硬约束（以下规则必须遵守，违反将导致镜头不可用）"]
        seen = set()
        for r in reports:
            if r.severity != "error":
                continue
            if r.rule_id in seen:
                continue
            seen.add(r.rule_id)
            lines.append(f"- 【{r.domain}】{r.description}")
        return "\n".join(lines) if len(lines) > 1 else ""

    def __len__(self):
        return len(self.rules)


# ──────────────────────────────────────────────────
# SB-4: Token 自适应裁剪
# ──────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """简易 token 估算（中文按字符数，英文按 4 字符 ≈ 1 token）"""
    if not text:
        return 0
    # 粗略估算：中文每个字算 1.5 token，英文每 4 字符算 1 token
    cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf')
    other_len = len(text) - cn_chars
    return int(cn_chars * 1.5 + other_len / 4)


class AdaptiveTrimmer:
    """根据输入文本长度自适应裁剪 prompt 详细度"""

    # 输入字数 → 最大 prompt 预算（tokens）
    TOKEN_BUDGETS = [
        (200,   8000),    # 短文：丰富描述
        (500,   12000),   # 中等
        (1000,  16000),   # 长文：适度压缩
        (2000,  20000),
        (5000,  24000),
    ]

    @classmethod
    def get_budget(cls, text_len: int) -> int:
        for threshold, budget in cls.TOKEN_BUDGETS:
            if text_len <= threshold:
                return budget
        return cls.TOKEN_BUDGETS[-1][1]

    @classmethod
    def get_density(cls, text_len: int, user_density: str) -> str:
        """超长文本自动降密度"""
        if text_len > 3000 and user_density == "dense":
            logger.info(f"[AdaptiveTrimmer] 文本 {text_len} 字过长，密度 dense→medium")
            return "medium"
        if text_len > 5000 and user_density == "medium":
            logger.info(f"[AdaptiveTrimmer] 文本 {text_len} 字过长，密度 medium→sparse")
            return "sparse"
        return user_density

    @classmethod
    def get_max_tokens(cls, text_len: int, density: str) -> int:
        """动态计算 AI 调用的 max_tokens"""
        density_map = {"sparse": 300, "medium": 150, "dense": 80}
        chars_per_shot = density_map.get(density, 150)
        expected_shots = max(1, text_len // chars_per_shot)
        # 每个镜头约 600 tokens + 800 tokens prompt 开销
        storyboard_max = min(32768, max(8192, expected_shots * 600 + 800))
        return storyboard_max

    @classmethod
    def trim_prompt(cls, prompt: str, max_tokens: int) -> str:
        """超预算时裁剪 prompt（优先保留 system 层，截断 context 层）"""
        estimated = estimate_tokens(prompt)
        if estimated <= max_tokens:
            return prompt
        logger.info(f"[AdaptiveTrimmer] prompt {estimated}t > {max_tokens}t，裁剪中…")

        ratio = max_tokens / max(estimated, 1)
        # 按行裁剪，保留前 ratio 比例
        lines = prompt.split("\n")
        keep = max(10, int(len(lines) * ratio))
        # 保留开头和结尾
        head = lines[:int(keep * 0.85)]
        tail = lines[-int(keep * 0.15):]
        return "\n".join(head + ["[以下内容因 Token 预算已裁剪]"] + tail)
