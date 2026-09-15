# -*- coding: utf-8 -*-
"""
书斋 V66 — 分镜 Prompt 模块化层 (SB-1 + SB-6)

将 storyboard_service._build_prompt() 中硬编码的 280+ 行 prompt 文本拆分为：
  - 8 个独立 prompt 构建模块（SB-1）
  - StoryboardPromptConfig：配置驱动的 prompt 管理（SB-6）

同时兼容现有 PromptAssembler 五层模型（SB-5 接入时使用）。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .storyboard_ir import (
    CharacterRegistry, WorldRuleSet, AdaptiveTrimmer,
    DENSITY_MAP, STYLE_NOTES, TOOL_GUIDE,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# SB-1: prompt_lib 外部化词库（七个 JSON，缺失回落内置）
# ──────────────────────────────────────────────

_PROMPT_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt_lib")
_PROMPT_LIB_NAMES = (
    "public_block", "camera_lib", "light_lib", "material_lib",
    "audio_lib", "style_preset", "platform_filter",
)
_lib_cache: Dict[str, Dict] = {}
_lib_lock = threading.Lock()


def load_prompt_lib(name: str) -> Dict:
    """读取 prompt_lib/<name>.json（带缓存）；文件缺失/损坏时返回空 dict"""
    with _lib_lock:
        if name in _lib_cache:
            return _lib_cache[name]
    path = os.path.join(_PROMPT_LIB_DIR, f"{name}.json")
    data: Dict = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning("[prompt_lib] 读取 %s 失败: %s", path, e)
            data = {}
    with _lib_lock:
        _lib_cache[name] = data
    return data


def reload_prompt_lib() -> None:
    """清空缓存，下次读取时重新加载（热更新）"""
    with _lib_lock:
        _lib_cache.clear()

# ──────────────────────────────────────────────────
# SB-10: 四大赛道风格预设（与视觉风格 STYLE_NOTES 正交）
GENRE_PRESETS = {
    "古风甜宠": {
        "style_note": "古风甜宠赛道：汉服飘逸质感，暖金柔光，花雨/纱幔/庭院意象，镜头缠绵舒缓",
        "camera_words": ["缓推", "环绕", "纱幔遮挡前景", "特写眉眼传情"],
        "light_words": ["暖金色逆光", "柔焦光晕", "灯笼暖光", "月色清辉"],
        "palette_hint": "#F7E7CE #D4A5A5 #FFF5EE",
        "negative_words": ["血腥", "肢解", "恐怖特写"],
    },
    "高燃打斗": {
        "style_note": "高燃打斗赛道：快节奏剪辑感，强对比硬光，动作张力拉满，能量特效进发",
        "camera_words": ["快速甩镜", "跟拍冲击", "低角度仰拍", "撞击瞬间定格"],
        "light_words": ["逆光剑光", "火花进溅高光", "能量光效青蓝", "烟尘体积光"],
        "palette_hint": "#1A1A2E #E94560 #FFB300",
        "negative_words": ["血腥特写", "残忍细节", "开放性伤口"],
    },
    "现代逆袭": {
        "style_note": "现代逆袭赛道：都市冷调电影感，霓虹与玻璃幕墙反光，身份对比构图，情绪特写",
        "camera_words": ["电梯门开合转场", "镜面反射构图", "从下往上推进", "人群穿透跟拍"],
        "light_words": ["都市霓虹冷暖对比", "办公室冷白顶光", "夜车窗光斑", "逆光前尘"],
        "palette_hint": "#0F2027 #2C5364 #E8C547",
        "negative_words": ["血腥", "自残", "未成年不当内容"],
    },
    "悬疑重生": {
        "style_note": "悬疑重生赛道：低饱和青灰调，阴影切割构图，时钟/镜子/旧照片意象，压迫感运镜",
        "camera_words": ["缓慢推近悬念物", "希区柯克变焦", "门缝窥视视角", "闪回闪白"],
        "light_words": ["单侧硬光阴影", "育色窗光", "烛火摇曳暖点", "雨夜冷青反光"],
        "palette_hint": "#1C2833 #566573 #A93226",
        "negative_words": ["血腥特写", "尸体直视", "恐怖惊吓镜头"],
    },
}


def get_genre_preset(name: str) -> Dict:
    """获取赛道预设；style_preset.json 的 genres 字段可覆盖/扩展内置预设"""
    ext = load_prompt_lib("style_preset").get("genres", {})
    merged = {**GENRE_PRESETS, **ext}
    return merged.get(name, {})


# SB-9: 双平台过滤词库（抖音/快手一键切换）
PLATFORM_FILTERS = {
    "douyin": {
        "description": "抖音：弱化血腥暴力，规避审核风险",
        "replacements": {
            "鲜血": "暗红痕迹", "血流如注": "伤势醒目", "尸体": "倒下的身影",
            "砍头": "重击倒地", "斩首": "一击制胜", "开膛破肚": "重创倒地",
            "内脏": "伤势", "割喉": "锁喉制胜", "血淋淋": "伤痕累累",
        },
        "negative_words": ["血腥", "残忍", "肢解", "虐杀", "酷刑"],
        "enhance_note": "画面需符合平台审核：避免直接血腥/暴力特写，用光影与反应镜头代替直接伤害展示。",
    },
    "kuaishou": {
        "description": "快手：高亮高饱，强化视觉冲击",
        "replacements": {},
        "negative_words": ["灰暗低饱和", "过曝发白"],
        "enhance_note": "画面亮度与饱和度拉高，色彩鲜艳浓烈，主体突出，视觉冲击力强。",
    },
}


def get_platform_filter(platform: str) -> Dict:
    """获取平台过滤配置；platform_filter.json 的 platforms 字段可覆盖/扩展"""
    if not platform:
        return {}
    ext = load_prompt_lib("platform_filter").get("platforms", {})
    merged = {**PLATFORM_FILTERS, **ext}
    return merged.get(platform, {})


def apply_platform_filter(text: str, platform: str) -> str:
    """对已渲染的镜头描述应用平台负面词替换（SB-9）"""
    pf = get_platform_filter(platform)
    if not pf or not text:
        return text
    for src, dst in (pf.get("replacements") or {}).items():
        if src in text:
            text = text.replace(src, dst)
    return text


# SB-6: PromptConfig — 配置驱动的 Prompt 管理
# ──────────────────────────────────────────────────

@dataclass
class StoryboardPromptConfig:
    """分镜 Prompt 配置中心，所有可调参数集中管理"""
    # 语言
    language: str = "zh"

    # 风格注入
    style_note: str = ""
    tool_lang: str = "中文详述"
    tool_tip: str = "使用中文详述，兼容主流AI视频工具。画面描述具体、光影明确、动作清晰。"

    # 密度
    chars_per_shot: int = 150

    # 功能开关
    enable_character_layers: bool = False     # 是否启用角色分层权重（SB-2）
    enable_world_rules: bool = False          # 是否启用世界观冲突过滤（SB-3）
    enable_adaptive_trim: bool = True         # 是否启用 Token 自适应裁剪（SB-4）
    enable_scene_aware: bool = True           # 是否启用场景感知条件注入（SB-10）
    enable_state_inherit: bool = True         # 是否启用跨镜头状态继承提示（SB-7）

    # 平台/赛道（SB-9/SB-10）
    platform: str = ""            # douyin/kuaishou，空为不启用平台过滤（SB-9）
    genre_preset: str = ""        # 四大赛道预设名，空为不启用（SB-10）

    # 自定义角色注册表
    character_registry: Optional[CharacterRegistry] = None

    # 自定义世界观规则集
    world_rule_set: Optional[WorldRuleSet] = None

    @classmethod
    def from_options(cls, options: dict) -> StoryboardPromptConfig:
        """从用户 options 字典构建配置"""
        target_tool = options.get("target_tool", "通用")
        style_preset = options.get("style_preset", "默认")
        density = options.get("shot_density", "medium")

        tg = TOOL_GUIDE.get(target_tool, TOOL_GUIDE["通用"])
        # SB-1: style_preset.json 的 visuals 字段可覆盖内置视觉风格
        ext_visuals = load_prompt_lib("style_preset").get("visuals", {})
        visuals = {**STYLE_NOTES, **ext_visuals}
        return cls(
            language=options.get("language", "zh"),
            style_note=visuals.get(style_preset, visuals["默认"]),
            tool_lang=tg["lang"],
            tool_tip=tg["tip"],
            chars_per_shot=DENSITY_MAP.get(density, 150),
            platform=options.get("platform", "") or "",
            genre_preset=options.get("genre_preset", "") or "",
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "language": self.language,
            "chars_per_shot": self.chars_per_shot,
            "enable_character_layers": self.enable_character_layers,
            "enable_world_rules": self.enable_world_rules,
            "enable_adaptive_trim": self.enable_adaptive_trim,
            "enable_state_inherit": self.enable_state_inherit,
            "platform": self.platform,
            "genre_preset": self.genre_preset,
        }


# ──────────────────────────────────────────────────
# SB-1: 独立 Prompt 模块
# ──────────────────────────────────────────────────

class StoryboardPromptBlocks:
    """分镜 prompt 的 8 个可独立替换的构建模块

    每个模块返回一个 (name, content, priority) 元组，
    可直接注入 PromptAssembler 五层模型。
    """

    # ───────── 模块 1：角色设定（system 层, priority=10） ─────────

    @staticmethod
    def block_role_identity() -> Tuple[str, str, int]:
        """角色设定 + 核心任务"""
        return ("system_role", """你是一位资深影视分镜师和AI视频导演。你的任务是把小说片段转化为可直接用于AI视频生成的分镜脚本。""", 10)

    # ───────── 模块 2：完整覆盖原则（rules 层, priority=20） ─────────

    @staticmethod
    def block_coverage(text_len: int, chars_per_shot: int) -> Tuple[str, str, int]:
        """首要原则：完整覆盖"""
        expected = max(1, text_len // chars_per_shot)
        content = f"""## 首要原则：完整覆盖（最高优先级）
你必须为全文从头到尾的每一个关键场景、转折、事件分配镜头。**绝对禁止中途停止**。
- 按大约每 {chars_per_shot} 字一个镜头的密度，全文 {text_len} 字，预期应产出约 {expected} 个镜头
- 请逐段审视全文：开头 → 发展 → 高潮 → 结尾，确保每个叙事段落都有对应的镜头覆盖
- 如果生成的分镜数量明显少于预期，说明你遗漏了大量内容，必须重新审视全文补充
- 镜头数量由正文长度和密度自然决定，不要人为限制或硬性截断"""
        return ("coverage_rule", content, 20)

    # ───────── 模块 3：专业能力（skills 层, priority=15） ─────────

    @staticmethod
    def block_professional_skills() -> Tuple[str, str, int]:
        """专业能力声明"""
        return ("skills", """## 你的专业能力
- 精通电影镜头语言（景别、运镜、构图、光线）
- 擅长视觉化叙事，能从文字中提取画面感最强的瞬间
- 了解 AI 视频生成工具的特点和局限性
- 精通镜头过渡设计，能根据前后镜头内容合理推断过渡效果""", 15)

    # ───────── 模块 4：输出要求（rules 层, priority=25） ─────────

    @staticmethod
    def block_output_requirements(config: StoryboardPromptConfig) -> Tuple[str, str, int]:
        """输出格式与风格要求"""
        return ("output_req", f"""## 输出要求
- 语言：{config.tool_lang}
- 风格：{config.style_note}
- 工具适配：{config.tool_tip}""", 25)

    # ───────── 模块 5：JSON Schema（rules 层, priority=30） ─────────

    @staticmethod
    def block_json_schema() -> Tuple[str, str, int]:
        """13 字段 JSON schema"""
        return ("json_schema", """## 每个镜头的 JSON 字段说明
{
  "index": 整数,                          // 镜头序号，从1开始
  "source_text": "原文关键句引用",         // 触发这个镜头的原文片段（20-50字）
  "shot_type": "景别",                    // 远景/全景/中景/近景/特写/大特写/POV
  "camera_movement": "运镜",              // 推镜/拉镜/平移/俯仰/静态/跟拍/环绕/摇镜
  "duration_sec": 浮点数,                 // 预估时长，2.0-10.0秒
  "transition": "过渡方式",              // 从当前镜头切换到下一镜头的过渡
  "lighting": "光影描述",                 // 光源方向 + 色温 + 光强，必须具体
  "color_palette": "#RRGGBB #RRGGBB #RRGGBB",  // 3-5个主色调
  "character_positions": [               // 画面中的角色
    {
      "name": "角色名",
      "position": "画面中的位置描述",
      "action": "当前动作描述"
    }
  ],
  "scene_description": "场景整体描述",     // 50-100字的完整场景描述
  "sound_design": "声音设计",             // 环境音 + 音效 + 配乐情绪
  "prompt_full": "完整可复制的AI视频生成提示词",
  "prompt_short": "简短关键词版本"
}""", 30)

    # ───────── 模块 6：过渡规则（rules 层, priority=35） ─────────

    @staticmethod
    def block_transition_rules() -> Tuple[str, str, int]:
        """transition 过渡推断规则"""
        return ("transition_rules", """## transition 过渡推断规则
根据前后镜头的场景、情绪、节奏变化来合理推断 transition：
- 场景/地点不变、时间连续 → "切"（CUT）
- 场景大变、情绪转折、时间跳跃 → "叠化"（DISSOLVE）
- 开场镜头、从黑暗进入画面 → "淡入"（FADE IN）
- 章节结束、段落收尾 → "淡出"（FADE OUT）
- 节奏突变、闪回记忆 → "闪白"（FLASH）
- 空间转换、地理位移 → "划像"（WIPE）
- 最后一个镜头 → "无"（NONE）""", 35)

    # ───────── 模块 7：质量规则（rules 层, priority=40） ─────────

    @staticmethod
    def block_quality_rules() -> Tuple[str, str, int]:
        """9 条重要规则"""
        return ("quality_rules", """## 重要规则
1. 光影描述必须具体：光源方向（上下左右角度）、色温（冷/暖/中性，最好给出K值）、强度（强/中/弱）、阴影形态
2. sound_design 必须包含三个维度：环境音 + 音效 + 配乐情绪，用 + 号连接
3. color_palette 必须是有效的十六进制颜色码，用空格分隔
4. character_positions 数组可以为空（纯风景镜头）
5. shot_type 和 camera_movement 必须从给定选项中选取
6. duration_sec 要根据镜头内容的复杂度合理设置（简单静态镜头2-3秒，复杂运动镜头5-8秒，不超过10秒）
7. prompt_full 是完整的画面描述，包含所有视觉信息；prompt_short 是简洁关键词版本
8. transition 必须从给定选项中选取，并根据过渡推断规则合理选择
9. 返回纯 JSON 数组，不要包含任何其他文字、解释或 markdown 标记""", 40)

    # ───────── 模块 8：用户指令（user 层, priority=50） ─────────

    @staticmethod
    def block_user_instruction(text: str) -> Tuple[str, str, int]:
        """包含小说文本的用户指令"""
        return ("user_text", f"""【小说文本】
{text}

请直接返回 JSON 数组，格式：[{{"index": 1, ...}}, {{"index": 2, ...}}]""", 50)

    # ───────── SB-2 动态层：角色分层（动态注入, priority=22） ─────────

    @staticmethod
    def block_character_layers(registry: CharacterRegistry) -> Optional[Tuple[str, str, int]]:
        """角色分层描述块（SB-2），仅在 registry 非空且有出场角色时生效"""
        if not registry or not registry.get_present_characters():
            return None
        return ("character_layers", registry.build_character_prompt_block(), 22)

    # ───────── SB-3 动态层：世界观约束（动态注入, priority=23） ─────────

    @staticmethod
    def block_world_constraints(reports: List) -> Optional[Tuple[str, str, int]]:
        """世界观约束提示块（SB-3），仅在检测到冲突时注入"""
        if not reports:
            return None
        errors = [r for r in reports if r.severity == "error"]
        if not errors:
            return None
        lines = ["## 世界观硬约束（以下规则必须遵守）"]
        seen = set()
        for r in errors:
            if r.rule_id in seen:
                continue
            seen.add(r.rule_id)
            lines.append(f"- 【{r.domain}】{r.description}")
        return ("world_constraints", "\n".join(lines), 23)

    # ───────── SB-7 跨镜头状态继承（rules 层, priority=36） ─────────

    @staticmethod
    def block_state_continuity() -> Tuple[str, str, int]:
        """跨镜头状态延续规则（SB-7）：伤势/服饰/道具不得镜间突变"""
        # SB-1: public_block.json 可覆盖内置文本
        ext = load_prompt_lib("public_block").get("state_continuity")
        text = ext or """## 跨镜头状态继承规则
相邻镜头之间，同一角色的状态必须延续，不得无故突变：
- 伤势：上一镜出现的伤口/血迹/包扎，后续镜头必须保留或合理演变（如包扎→渗血）
- 服饰：服装/发型/配饰在连续场景中保持一致，除非文本明确提及更换
- 道具：手持武器/物品/坐骑随角色延续，不得凭空消失或替换
- 环境：天气/光线/破坏痕迹在连续场景中保持连贯
若文本未提及变化，一律默认延续上一镜状态。"""
        return ("state_continuity", text, 36)

    # ───────── SB-10 赛道预设（风格层, priority=14） ─────────

    @staticmethod
    def block_genre_preset(genre: str) -> Optional[Tuple[str, str, int]]:
        """四大赛道风格预设块（SB-10），仅在 genre 命中时注入"""
        preset = get_genre_preset(genre)
        if not preset:
            return None
        lines = [f"## 赛道风格预设：{genre}", preset.get("style_note", "")]
        cam = preset.get("camera_words") or []
        light = preset.get("light_words") or []
        if cam:
            lines.append(f"- 优先运镜词汇：{'、'.join(cam)}")
        if light:
            lines.append(f"- 优先光影词汇：{'、'.join(light)}")
        if preset.get("palette_hint"):
            lines.append(f"- 建议色板：{preset['palette_hint']}")
        neg = preset.get("negative_words") or []
        if neg:
            lines.append(f"- 负面规避：{'、'.join(neg)}")
        return ("genre_preset", "\n".join(lines), 14)

    # ───────── SB-9 平台规则（规则层, priority=38） ─────────

    @staticmethod
    def block_platform_rules(platform: str) -> Optional[Tuple[str, str, int]]:
        """平台适配规则块（SB-9 抖音/快手），仅在 platform 命中时注入"""
        pf = get_platform_filter(platform)
        if not pf:
            return None
        lines = [f"## 平台适配规则（{pf.get('description', platform)}）"]
        if pf.get("enhance_note"):
            lines.append(f"- {pf['enhance_note']}")
        neg = pf.get("negative_words") or []
        if neg:
            lines.append(f"- 严禁出现：{'、'.join(neg)}")
        reps = pf.get("replacements") or {}
        if reps:
            sample = "、".join(f"「{k}」→「{v}」" for k, v in list(reps.items())[:4])
            lines.append(f"- 敏感表达替换示例：{sample}")
        return ("platform_rules", "\n".join(lines), 38)


# ──────────────────────────────────────────────────
# SB-5: Prompt 组装入口（接入 PromptAssembler）
# ──────────────────────────────────────────────────

def build_storyboard_prompt(
    text: str,
    config: StoryboardPromptConfig,
    assembler=None,  # Optional[PromptAssembler]
) -> str:
    """
    使用 PromptAssembler 五层模型构建分镜 prompt（SB-5 接入点）

    若 assembler 为 None，则回退到传统 f-string 拼接模式（兼容旧调用）。
    推荐传入 PromptAssembler 实例以享受分层管理能力。

    Args:
        text: 小说文本
        config: PromptConfig 配置
        assembler: PromptAssembler 实例，可选

    Returns:
        完整的 prompt 字符串
    """
    blocks = StoryboardPromptBlocks()

    # SB-9: 外部化版本管理（同名字段覆盖内置文本）
    vman = PromptVersionManager.instance()

    # 收集所有静态模块
    all_blocks = [
        vman.apply_block(
            "system_role", *blocks.block_role_identity()[1:],
        ),
        vman.apply_block(
            "coverage_rule", *blocks.block_coverage(len(text), config.chars_per_shot)[1:],
        ),
        vman.apply_block(
            "skills", *blocks.block_professional_skills()[1:],
        ),
        vman.apply_block(
            "output_req", *blocks.block_output_requirements(config)[1:],
            format_kwargs={
                "tool_lang": config.tool_lang,
                "style_note": config.style_note,
                "tool_tip": config.tool_tip,
            },
        ),
        vman.apply_block(
            "json_schema", *blocks.block_json_schema()[1:],
        ),
        vman.apply_block(
            "transition_rules", *blocks.block_transition_rules()[1:],
        ),
        vman.apply_block(
            "quality_rules", *blocks.block_quality_rules()[1:],
        ),
    ]

    # SB-2：角色分层（动态）
    if config.enable_character_layers and config.character_registry:
        char_block = blocks.block_character_layers(config.character_registry)
        if char_block:
            all_blocks.append(char_block)

    # SB-10：场景感知条件注入（动态）
    if config.enable_scene_aware:
        all_blocks.extend(SceneAwareInjector.inject(text, config))

    # SB-7：跨镜头状态继承规则
    if config.enable_state_inherit:
        all_blocks.append(blocks.block_state_continuity())

    # SB-10：四大赛道风格预设（动态）
    if config.genre_preset:
        genre_block = blocks.block_genre_preset(config.genre_preset)
        if genre_block:
            all_blocks.append(genre_block)

    # SB-9：双平台适配规则（动态）
    if config.platform:
        platform_block = blocks.block_platform_rules(config.platform)
        if platform_block:
            all_blocks.append(platform_block)

    # 用户指令
    all_blocks.append(blocks.block_user_instruction(text))

    if assembler is not None:
        # ── SB-5: 使用 PromptAssembler 五层模型 ──
        assembler.layers.clear()
        for name, content, priority in all_blocks:
            assembler.add_layer(name, content, priority)
        prompt = assembler.assemble()
    else:
        # ── 回退：传统拼接（按 priority 排序） ──
        sorted_blocks = sorted(all_blocks, key=lambda x: x[2])
        prompt = "\n\n---\n\n".join(content for _, content, _ in sorted_blocks)

    # SB-4: Token 自适应裁剪
    if config.enable_adaptive_trim:
        budget = AdaptiveTrimmer.get_budget(len(text))
        prompt = AdaptiveTrimmer.trim_prompt(prompt, budget)

    return prompt


# ──────────────────────────────────────────────────
# 便捷函数：旧版 _build_prompt() 的行为保持
# ──────────────────────────────────────────────────

def build_prompt_legacy(text: str, options: dict) -> str:
    """保持与旧 _build_prompt() 完全一致的输出（过渡用）"""
    config = StoryboardPromptConfig.from_options(options)
    return build_storyboard_prompt(text, config, assembler=None)


# ──────────────────────────────────────────────────
# SB-9: Prompt 外部化版本管理
# ──────────────────────────────────────────────────

class PromptVersionManager:
    """分镜 Prompt 外部化版本管理（SB-9）

    加载 backend/services/storyboard_prompts.json：
      - versions: 版本元信息（name / description / features）
      - blocks:   同名字段覆盖内置模块文本；缺失块使用内置文本
    支持 reload() 热更新；线程安全单例。

    覆盖块支持 {placeholder} 模板占位，format_kwargs 提供渲染参数。
    """

    DEFAULT_JSON_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "storyboard_prompts.json"
    )

    _instance = None
    _lock = threading.Lock()

    def __init__(self, json_path: Optional[str] = None):
        self._json_path = json_path or self.DEFAULT_JSON_PATH
        self._data: Dict[str, Any] = {}
        self._load()

    # ── 加载 / 重载 ────────────────────────────────

    def _load(self) -> None:
        try:
            with open(self._json_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            logger.info(
                "[SB-9] PromptVersionManager 加载成功 version=%s",
                self.current_version,
            )
        except FileNotFoundError:
            logger.warning("[SB-9] storyboard_prompts.json 不存在，使用内置文本")
            self._data = {}
        except json.JSONDecodeError as e:
            logger.error("[SB-9] storyboard_prompts.json 解析失败: %s，使用内置文本", e)
            self._data = {}

    def reload(self) -> bool:
        """重新加载外部配置，返回是否成功"""
        self._load()
        return bool(self._data)

    # ── 属性 ───────────────────────────────────────

    @property
    def current_version(self) -> str:
        meta = self._data.get("_meta", {})
        return meta.get("current_version", "内置")

    @property
    def version_info(self) -> Dict[str, Any]:
        return self._data.get("versions", {})

    @property
    def enabled(self) -> bool:
        return bool(self._data)

    # ── 块覆盖 ─────────────────────────────────────

    def get_block(
        self,
        name: str,
        default: str,
        format_kwargs: Optional[Dict[str, Any]] = None,
    ) -> str:
        """获取指定名称的 prompt 块文本。

        若外部 JSON 中存在同名块则返回外部文本（支持 {placeholder} 渲染），
        否则返回内置 default。
        """
        external = self._data.get("blocks", {}).get(name)
        if external is None:
            return default
        if format_kwargs:
            try:
                return external.format(**format_kwargs)
            except (KeyError, IndexError) as e:
                logger.warning("[SB-9] 块 %s 模板渲染失败: %s，使用内置文本", name, e)
                return default
        return external

    def apply_block(
        self,
        name: str,
        content: str,
        priority: int,
        format_kwargs: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str, int]:
        """应用外部覆盖，返回 (name, content, priority)"""
        return (name, self.get_block(name, content, format_kwargs), priority)

    # ── 单例 ───────────────────────────────────────

    @classmethod
    def instance(cls, json_path: Optional[str] = None) -> "PromptVersionManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(json_path)
            elif json_path and json_path != cls._instance._json_path:
                cls._instance = cls(json_path)
        return cls._instance


# ──────────────────────────────────────────────────
# SB-10: 场景感知条件注入
# ──────────────────────────────────────────────────

class SceneAwareInjector:
    """场景感知条件注入器（SB-10）

    扫描小说文本中的场景特征（场景切换 / 时间变化 / 动作戏 / 对话 /
    情绪爆发 / 环境氛围），命中时动态注入对应的 prompt 规则块，
    让 AI 生成的分镜在节奏、过渡、光影上贴合场景类型。
    """

    # 特征 → 命中关键词
    FEATURE_KEYWORDS: Dict[str, Tuple[str, ...]] = {
        "action": (
            "打斗", "厮杀", "剑光", "刀锋", "拳风", "追击", "狂奔",
            "飞身", "碰撞", "爆炸", "轰鸣", "闪避", "反击", "斩",
        ),
        "dialogue": (
            "说道", "开口道", "沉声道", "低声道", "问道", "答道",
            "笑道", "喊道", "怒道", "喃喃", "对话", "交谈", "质问",
        ),
        "time_shift": (
            "清晨", "黎明", "日出", "正午", "黄昏", "傍晚", "入夜",
            "深夜", "午夜", "翌日", "第二天", "片刻后", "转眼间",
        ),
        "emotion": (
            "痛哭", "落泪", "狂笑", "颤抖", "怒吼", "绝望", "狂喜",
            "震惊", "悲痛", "哽咽", "心如刀绞", "怒火",
        ),
        "environment": (
            "暴雨", "风雪", "大雾", "星空", "月光", "烈日", "林间",
            "山谷", "悬崖", "宫殿", "废墟", "荒漠", "海浪", "烛火",
        ),
    }

    # 每个特征的注入规则（priority 处于各静态块之间，20~39 区间）
    FEATURE_RULES: Dict[str, Tuple[str, str, int]] = {
        "action": (
            "scene_action",
            """## 动作场景规则
- 节奏加快：镜头平均时长缩短（2-4秒），多用快速切换与动态运镜（跟拍/环绕/推镜）
- 保持动作连续性：相邻镜头需承接上一个动作的末态，避免跳跃断裂
- 强调冲击力：突出碰撞瞬间、肢体张力、尘土/碎片等细节
- 景别以中景/近景/特写为主，减少远景""",
            21,
        ),
        "dialogue": (
            "scene_dialogue",
            """## 对话场景规则
- 优先使用正反打（shot/reverse shot）：说话者近景 + 倾听者反应镜头交替
- 对话镜头注意眼神、口型与神态细节；无意义空镜头不超过1个
- 角色语气变化处用特写强化情绪，必要时给出镜头上摇/推近等强调运镜""",
            22,
        ),
        "time_shift": (
            "scene_time",
            """## 时间变化规则
- 时间跳变处必须给出明确的过渡镜头（如钟表/光影/天空变化），再用"叠化"或"划像"衔接
- 新时间段的场景需在 lighting 中体现相应色温与光线方向（晨昏低角度暖光、夜晚冷色调）
- 若时间跳变伴随场景变换，transition 优先选"叠化"或"划像"，避免生硬硬切""",
            23,
        ),
        "emotion": (
            "scene_emotion",
            """## 情绪爆发规则
- 情绪高点使用特写/大特写 + 静态或缓慢推镜，让观众聚焦面部表情
- 声音设计需强化情绪配乐；必要时用"闪白"表达记忆/冲击
- 情绪转折处前后镜头节奏要有明显对比（紧张→爆发→余韵）""",
            24,
        ),
        "environment": (
            "scene_environment",
            """## 环境氛围规则
- 环境特征场景优先铺陈全景/远景交代空间，再切近景进入人物
- lighting 必须呼应环境（暴雨=低照度冷光、月光=冷蓝高对比、烛火=暖黄低照度）
- 环境音是 sound_design 的主体，人声与音效层次分明""",
            25,
        ),
    }

    def __init__(self, text: str, config: Optional[StoryboardPromptConfig] = None):
        self.text = text or ""
        self.config = config or StoryboardPromptConfig()

    # ── 特征检测 ────────────────────────────────────

    def detect(self) -> Dict[str, bool]:
        """返回各场景特征是否命中"""
        hits: Dict[str, bool] = {}
        for feature, keywords in self.FEATURE_KEYWORDS.items():
            hits[feature] = any(k in self.text for k in keywords)
        return hits

    def matched_features(self) -> List[str]:
        """返回命中特征的名称列表（按规则优先级排序）"""
        hits = self.detect()
        order = sorted(self.FEATURE_RULES, key=lambda f: self.FEATURE_RULES[f][2])
        return [f for f in order if hits.get(f)]

    # ── 注入块构建 ──────────────────────────────────

    def build_blocks(self) -> List[Tuple[str, str, int]]:
        """构建命中的场景感知注入块列表（空则返回 []）"""
        blocks = []
        for feature in self.matched_features():
            name, content, priority = self.FEATURE_RULES[feature]
            blocks.append((name, content, priority))
        return blocks

    # ── 便捷入口 ────────────────────────────────────

    @classmethod
    def inject(cls, text: str, config: StoryboardPromptConfig) -> List[Tuple[str, str, int]]:
        """一行式调用：返回需注入的块列表"""
        if not config.enable_scene_aware:
            return []
        return cls(text, config).build_blocks()
