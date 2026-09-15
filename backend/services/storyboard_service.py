# -*- coding: utf-8 -*-
"""
书斋 V65 - 视频分镜生成服务
根据小说文本生成 AI 视频分镜脚本
"""
import json
import re
import uuid
import os
import time
import logging

# SB-0~SB-6: 分镜 IR 层 + Prompt 模块化
from backend.services.storyboard_ir import (
    StoryboardIRBuilder,
    CharacterRegistry, CharacterLayer, WorldRuleSet, WorldRule,
    AdaptiveTrimmer, DENSITY_MAP,
)
from backend.services.storyboard_prompts import (
    StoryboardPromptConfig, build_storyboard_prompt, apply_platform_filter,
)
from backend.services.prompt_assembler import PromptAssembler

logger = logging.getLogger(__name__)


class StoryboardService:
    """视频分镜生成器 —— 将小说片段转为分镜脚本"""

    # 分镜密度配置（每 N 字一个镜头）
    DENSITY_MAP = {
        "sparse": 300,   # 稀疏：每300字1镜
        "medium": 150,   # 中等：每150字1镜
        "dense": 80,     # 密集：每80字1镜
    }

    # 风格预设 prompt 补充
    STYLE_NOTES = {
        "写实电影": "写实电影风格，自然光照，胶片质感，电影级构图，真实环境纹理细节",
        "动漫": "日本动画风格，干净线条，鲜明色块，吉卜力/新海诚式光影，手绘质感",
        "水墨": "中国传统水墨画风格，墨色浓淡，留白意境，宣纸纹理，写意笔触",
        "赛博朋克": "赛博朋克风格，霓虹灯光，湿滑街道反射，全息投影，机械义体，高对比度冷色调",
        "默认": "电影级画质，自然光影，真实材质，史诗感构图",
    }

    # 不同视频工具的 prompt 语言和格式指导
    TOOL_GUIDE = {
        "kling": {
            "lang": "中文详述",
            "tip": "使用中文进行细致描述，突出画面构图、角色神态、氛围意境。关键词部分用中文短语。",
        },
        "sora": {
            "lang": "英文物理描述",
            "tip": "Use English physical descriptions. Focus on realistic physics, material properties, camera optics, lighting physics. Short keywords in English.",
        },
        "jimeng": {
            "lang": "中文+风格标签",
            "tip": "中文核心描述 + 英文风格标签。例如：'一位侠客在竹林中持剑，雾气弥漫' + cinematic lighting, bamboo forest, mist, dynamic pose",
        },
        "通用": {
            "lang": "中文详述",
            "tip": "使用中文详述，兼容主流AI视频工具。画面描述具体、光影明确、动作清晰。",
        },
    }

    # 过渡类型
    TRANSITION_TYPES = ["切", "淡入", "淡出", "叠化", "划像", "闪白", "无"]

    # 模板预设
    TEMPLATES = {
        "默认": {"target_tool": "通用", "style_preset": "默认", "shot_density": "medium"},
        "电影感": {"target_tool": "kling", "style_preset": "写实电影", "shot_density": "sparse"},
        "快节奏": {"target_tool": "通用", "style_preset": "默认", "shot_density": "dense"},
        "慢节奏": {"target_tool": "通用", "style_preset": "水墨", "shot_density": "sparse"},
    }

    def __init__(self):
        from backend.ai_client import AIClient
        self.ai = AIClient()
        self._data_dir = self._get_data_dir()
        # SB-5: PromptAssembler 实例（分镜专用）
        self._prompt_assembler = PromptAssembler()
        # SB-2: 角色注册表（默认空）
        self._character_registry = CharacterRegistry()
        # SB-3: 世界观规则集（默认空）
        self._world_rules = WorldRuleSet()

    def _get_data_dir(self):
        """获取历史记录存储目录"""
        base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        data_dir = os.path.join(base, "data", "storyboard_history")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir

    # ── 主入口 ────────────────────────────────────────────

    def generate(self, text: str, options: dict = None) -> dict:
        if options is None:
            options = {}

        storyboard_id = f"sb-{uuid.uuid4().hex[:8]}"

        # SB-4: 自适应密度 + max_tokens
        text_len = len(text)
        density = AdaptiveTrimmer.get_density(
            text_len, options.get("shot_density", "medium")
        )
        options["shot_density"] = density
        storyboard_max_tokens = AdaptiveTrimmer.get_max_tokens(text_len, density)
        logger.info(
            f"[StoryboardService] text_len={text_len}, density={density}, "
            f"expected_shots={max(1, text_len // DENSITY_MAP.get(density, 150))}, "
            f"max_tokens={storyboard_max_tokens}"
        )

        # SB-1+SB-5+SB-6: 使用 PromptAssembler 构建 prompt
        config = StoryboardPromptConfig.from_options(options)
        # 注入角色注册表与世界规则集
        config.character_registry = self._character_registry
        config.world_rule_set = self._world_rules
        config.enable_character_layers = bool(self._character_registry)
        config.enable_world_rules = bool(self._world_rules)

        # SB-2: 若提供项目上下文，从真相账本自动同步角色分层
        if options.get("project_dir"):
            self.sync_from_ledger(options["project_dir"])

        prompt = build_storyboard_prompt(text, config, assembler=self._prompt_assembler)

        # 调用 AI
        logger.info(
            f"[StoryboardService] 开始生成分镜 storyboard_id={storyboard_id}, "
            f"text_len={text_len}, prompt_tokens≈{len(prompt)//2}"
        )
        raw = self.ai.generate(prompt, max_tokens=storyboard_max_tokens)

        # SB-0: 用 IRBuilder 解析
        ir = StoryboardIRBuilder.build(storyboard_id, raw, options)

        # SB-8: 目标工具适配器（渲染工具专属 prompt_full / prompt_short）
        from backend.services.storyboard_adapters import adapt_ir
        adapt_ir(ir)

        # SB-7: 跨镜头状态继承后处理（上一镜状态 → 当前镜 carried_state）
        if config.enable_state_inherit:
            self._inherit_state(ir.shots)

        # SB-9: 双平台渲染替换（对已渲染描述做平台负面词弱化）
        if config.platform:
            for shot in ir.shots:
                shot.prompt_full = apply_platform_filter(shot.prompt_full, config.platform)
                shot.prompt_short = apply_platform_filter(shot.prompt_short, config.platform)
                shot.scene_description = apply_platform_filter(shot.scene_description, config.platform)

        # 截断检测
        expected_shots = max(1, text_len // DENSITY_MAP.get(density, 150))
        actual_shots = len(ir.shots)
        if actual_shots > 0 and actual_shots < expected_shots * 0.6:
            logger.warning(
                f"[StoryboardService] 镜头可能被截断：期望~{expected_shots}个，实际{actual_shots}个"
            )
            ir.warnings.append(
                f"镜头数({actual_shots})少于预期({expected_shots})，可能因AI输出长度限制被截断。"
                f"可尝试降低密度或分段生成。"
            )

        # SB-3: 世界观冲突检测（如果配置了规则）
        if self._world_rules:
            conflicts = self._world_rules.check_all(ir)
            ir.world_conflicts = conflicts
            if conflicts:
                errors = self._world_rules.filter_errors(conflicts)
                warnings = self._world_rules.filter_warnings(conflicts)
                if errors:
                    ir.warnings.append(
                        f"世界观硬冲突 {len(errors)} 条，建议检查镜头 {', '.join(str(c.shot_index) for c in errors[:5])}"
                    )
                logger.info(
                    f"[StoryboardService] 世界观检查: {len(errors)} 硬冲突, {len(warnings)} 软冲突"
                )

        return ir.to_dict()

    # ── 批量生成 ──────────────────────────────────────────

    def batch_generate(self, texts: list, options: dict = None) -> list:
        """
        批量生成：接受多个文本，为每个返回独立的分镜结果

        Args:
            texts: [{"chapter_id": "xxx", "text": "..."}, ...]
            options: 全局选项

        Returns:
            [{"chapter_id": "xxx", "storyboard_id": "sb-xxx", "shots": [...], "global_style": {...}}, ...]
        """
        results = []
        for item in texts:
            chapter_id = item.get("chapter_id", "")
            text = item.get("text", "")
            if not text or len(text.strip()) < 50:
                logger.warning(f"[StoryboardService] 跳过过短文本 chapter_id={chapter_id}")
                continue
            try:
                result = self.generate(text=text, options=options)
                result["chapter_id"] = chapter_id
                self._save_to_history(chapter_id, result)
                results.append(result)
            except Exception as e:
                logger.error(f"[StoryboardService] 批量生成单条失败 chapter_id={chapter_id}: {e}")
                results.append({
                    "chapter_id": chapter_id,
                    "storyboard_id": "",
                    "shots": [],
                    "global_style": {},
                    "error": str(e),
                })
        return results

    # ── Prompt 构建 ────────────────────────────────────────

    def _build_prompt(self, text: str, options: dict) -> str:
        """构建分镜 prompt（SB-5: 接入 PromptAssembler）"""
        config = StoryboardPromptConfig.from_options(options)
        config.character_registry = self._character_registry
        config.world_rule_set = self._world_rules
        config.enable_character_layers = bool(self._character_registry)
        config.enable_world_rules = bool(self._world_rules)
        return build_storyboard_prompt(text, config, assembler=self._prompt_assembler)

    # ── 结果解析 ──────────────────────────────────────────

    def _parse_result(self, raw: str) -> dict:
        """
        解析 AI 返回的 JSON 结果，带容错处理。
        支持：
        - 直接 JSON 数组
        - ```json ... ``` 包裹的 JSON
        - 无标记但前后有空格的 JSON
        - 混在文字中的 JSON 数组（提取方括号段）
        """
        shots = []
        error = None

        # 清理 AI 可能返回的多余文本
        cleaned = raw.strip()

        # 策略1：去除 ```json ... ``` 标记
        if "```" in cleaned:
            # 提取代码块内容
            match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1).strip()
            else:
                # 可能只有开头的 ``` 没有结尾
                cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
                cleaned = re.sub(r'\s*```$', '', cleaned)

        # 策略2：找到第一个 [ 和最后一个 ]，只取数组部分
        start_idx = cleaned.find('[')
        end_idx = cleaned.rfind(']')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            cleaned = cleaned[start_idx:end_idx + 1]

        # 策略3：尝试直接解析
        try:
            shots = json.loads(cleaned)
            if not isinstance(shots, list):
                shots = []
        except json.JSONDecodeError as e:
            logger.warning(f"[StoryboardService] JSON 解析失败: {e}")
            error = f"JSON 解析失败: {str(e)}"
            # 最后尝试：逐个对象提取
            shots = self._extract_objects_fallback(cleaned)

        # 验证和补全每个 shot
        validated_shots = []
        for i, shot in enumerate(shots):
            if not isinstance(shot, dict):
                continue
            validated_shots.append(self._validate_shot(shot, i + 1))

        if error and not validated_shots:
            return {"shots": [], "parse_error": error}

        return {"shots": validated_shots}

    def _extract_objects_fallback(self, text: str) -> list:
        """最后的兜底方案：用正则逐个匹配 JSON 对象"""
        objects = []
        # 匹配 { ... } 对象（非贪婪，平衡括号）
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
                    obj_str = text[start:i + 1]
                    try:
                        obj = json.loads(obj_str)
                        objects.append(obj)
                    except json.JSONDecodeError:
                        pass
                    start = -1
        return objects

    def _validate_shot(self, shot: dict, expected_index: int) -> dict:
        """验证并补全单个镜头的字段"""
        # 允许的景别和运镜值
        valid_shot_types = {"远景", "全景", "中景", "近景", "特写", "大特写", "POV"}
        valid_movements = {"推镜", "拉镜", "平移", "俯仰", "静态", "跟拍", "环绕", "摇镜"}
        valid_transitions = set(self.TRANSITION_TYPES)

        validated = {
            "index": shot.get("index", expected_index),
            "source_text": shot.get("source_text", ""),
            "shot_type": shot.get("shot_type", "中景") if shot.get("shot_type", "中景") in valid_shot_types else "中景",
            "camera_movement": shot.get("camera_movement", "静态") if shot.get("camera_movement", "静态") in valid_movements else "静态",
            "duration_sec": self._clamp_duration(shot.get("duration_sec", 4.0)),
            "transition": shot.get("transition", "切") if shot.get("transition", "切") in valid_transitions else "切",
            "lighting": shot.get("lighting", "正面自然光，色温5500K，中等强度"),
            "color_palette": shot.get("color_palette", "#FFFFFF #000000 #808080"),
            "character_positions": shot.get("character_positions", []),
            "scene_description": shot.get("scene_description", ""),
            "sound_design": shot.get("sound_design", "环境音（自然氛围）+ 音效（无）+ 配乐情绪（中性）"),
            "prompt_full": shot.get("prompt_full", shot.get("scene_description", "")),
            "prompt_short": shot.get("prompt_short", ""),
        }

        # 确保 character_positions 是列表
        if not isinstance(validated["character_positions"], list):
            validated["character_positions"] = []

        return validated

    @staticmethod
    def _clamp_duration(seconds) -> float:
        """将时长限制在 2.0 - 10.0 秒之间"""
        try:
            s = float(seconds)
            return max(2.0, min(10.0, s))
        except (TypeError, ValueError):
            return 4.0

    # ── 历史持久化 ────────────────────────────────────────

    def _save_to_history(self, chapter_id: str, result: dict):
        """保存生成结果到历史目录"""
        try:
            ts = int(time.time())
            fname = f"{ts}_{chapter_id or 'unknown'}.json"
            fpath = os.path.join(self._data_dir, fname)
            record = {
                "timestamp": ts,
                "chapter_id": chapter_id,
                "storyboard_id": result.get("storyboard_id", ""),
                "shots": result.get("shots", []),
                "global_style": result.get("global_style", {}),
            }
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            logger.info(f"[StoryboardService] 历史已保存: {fpath}")
        except Exception as e:
            logger.error(f"[StoryboardService] 保存历史失败: {e}")

    def get_history(self) -> list:
        """获取所有历史记录（按时间倒序）"""
        items = []
        try:
            for fname in sorted(os.listdir(self._data_dir), reverse=True):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(self._data_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    # 提取文件名中的 timestamp_chapter_id 作为 history_id
                    hid = fname.replace(".json", "")
                    items.append({
                        "history_id": hid,
                        "timestamp": data.get("timestamp", 0),
                        "chapter_id": data.get("chapter_id", ""),
                        "shot_count": len(data.get("shots", [])),
                        "style": data.get("global_style", {}).get("style_preset", ""),
                        "storyboard_id": data.get("storyboard_id", ""),
                    })
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"[StoryboardService] 读取历史失败: {e}")
        return items

    def load_history(self, history_id: str) -> dict:
        """加载指定历史记录的完整数据"""
        fname = f"{history_id}.json"
        fpath = os.path.join(self._data_dir, fname)
        if not os.path.exists(fpath):
            return None
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.error(f"[StoryboardService] 加载历史失败 {history_id}: {e}")
            return None

    def delete_history(self, history_id: str) -> bool:
        """删除指定历史记录"""
        fname = f"{history_id}.json"
        fpath = os.path.join(self._data_dir, fname)
        if not os.path.exists(fpath):
            return False
        try:
            os.remove(fpath)
            return True
        except Exception as e:
            logger.error(f"[StoryboardService] 删除历史失败 {history_id}: {e}")
            return False

    # ── 模板管理 ──────────────────────────────────────────

    def get_templates(self) -> list:
        """获取所有模板"""
        return [
            {"name": name, **preset}
            for name, preset in self.TEMPLATES.items()
        ]

    def add_template(self, name: str, target_tool: str, style_preset: str, shot_density: str) -> dict:
        """新增自定义模板"""
        if name in self.TEMPLATES:
            self.TEMPLATES[name] = {
                "target_tool": target_tool,
                "style_preset": style_preset,
                "shot_density": shot_density,
            }
            return {"updated": True, "name": name, **self.TEMPLATES[name]}
        self.TEMPLATES[name] = {
            "target_tool": target_tool,
            "style_preset": style_preset,
            "shot_density": shot_density,
        }
        return {"created": True, "name": name, **self.TEMPLATES[name]}

    def delete_template(self, name: str) -> bool:
        """删除模板（内置模板不可删除）"""
        builtin = {"默认", "电影感", "快节奏", "慢节奏"}
        if name in builtin:
            return False
        if name in self.TEMPLATES:
            del self.TEMPLATES[name]
            return True
        return False

    # ── SB-7: 跨镜头状态继承 ──────────────────────

    # 状态关键词分类（伤势/服饰/道具）
    _STATE_KEYWORDS = {
        "伤势": ("伤", "血", "包扎", "绷带", "骨折", "瘀", "中毒", "昏迷"),
        "服饰": ("衣", "袍", "甲", "裙", "帽", "披风", "斗篷", "面纱", "鞋"),
        "道具": ("剑", "刀", "枪", "弓", "盾", "杖", "符", "丹", "匣", "伞", "鞭", "锤", "令牌", "书信"),
    }

    @staticmethod
    def _extract_state_sentence(source: str, keyword: str, max_len: int = 40) -> str:
        """提取包含关键词的最短语句片段，用于状态继承"""
        segments = re.split(r"[。，；！？、\n\[\]]", source)
        for seg in segments:
            seg = seg.strip()
            if keyword in seg:
                return seg[:max_len]
        return ""

    def _inherit_state(self, shots: list):
        """
        SB-7 跨镜头状态继承：从第 i-1 镜的描述/角色位提取伤势/服饰/道具状态，
        填入第 i 镜 carried_state，并在 prompt_full 末尾附加继承行。
        """
        prev = None
        for shot in shots:
            if prev is not None:
                source = " ".join(filter(None, [prev.scene_description, prev.prompt_full]))
                for cp in prev.character_positions or []:
                    if isinstance(cp, dict):
                        source += " " + " ".join(str(v) for v in cp.values())
                carried = {}
                for cat, kws in self._STATE_KEYWORDS.items():
                    for kw in kws:
                        if kw in source:
                            snippet = self._extract_state_sentence(source, kw)
                            if snippet:
                                carried[cat] = snippet
                            break
                if carried:
                    shot.carried_state.update(carried)
                    line = "；".join(f"{k}:{v}" for k, v in carried.items())
                    if shot.prompt_full:
                        shot.prompt_full = f"{shot.prompt_full}\n[状态继承: {line}]"
                    else:
                        shot.prompt_full = f"[状态继承: {line}]"
            prev = shot

    # ── SB-2: 账本同步角色分层 ─────────────────────

    def sync_from_ledger(self, project_dir: str) -> int:
        """
        SB-2 自动分层：读 TruthLedger.character_states 派生 tier 并注册角色。
        派生规则：archived/死亡 → 3（背景层）；last_seen_chapter 近且有 possessions → 1（焦点层）；其余 → 2。
        返回注册角色数。
        """
        try:
            from backend.ledger import TruthLedger
            ledger = TruthLedger(project_dir)
        except Exception as e:
            logger.warning(f"[StoryboardService] sync_from_ledger 加载账本失败: {e}")
            return 0
        total_chapters = len(ledger.chapter_logs)
        count = 0
        for name, cs in ledger.character_states.items():
            archived = bool(getattr(cs, "archived", False))
            alive = bool(getattr(cs, "is_alive", True))
            if archived or not alive:
                tier = 3
            else:
                last_seen = getattr(cs, "last_seen_chapter", 0) or 0
                recent = (total_chapters - last_seen) <= 3
                if recent and getattr(cs, "possessions", None):
                    tier = 1
                else:
                    tier = 2
            traits = []
            if getattr(cs, "realm", ""):
                traits.append(f"境界:{cs.realm}")
            if getattr(cs, "health", ""):
                traits.append(f"健康:{cs.health}")
            if getattr(cs, "possessions", None):
                traits.append("持有:" + ",".join(list(cs.possessions)[:3]))
            self.register_character(
                name, tier=tier, weight=1.0,
                visual_traits="；".join(traits),
                is_present=(tier != 3),
            )
            count += 1
        logger.info(f"[StoryboardService] sync_from_ledger 完成: {count} 个角色已同步分层")
        return count

    # ── SB-2: 角色分层管理 ──────────────────────────

    def register_character(self, name: str, tier: int = 2,
                           weight: float = 1.0,
                           visual_traits: str = "",
                           is_present: bool = True):
        """注册或更新一个角色（SB-2 角色分层权重）"""
        layer = CharacterLayer(
            name=name, tier=tier, weight=weight,
            visual_traits=visual_traits, is_present=is_present,
        )
        self._character_registry.register(layer)
        logger.info(f"[StoryboardService] 角色已注册: {name} tier={tier} weight={weight}")

    def get_characters(self) -> list:
        """获取当前注册的所有角色信息"""
        return [
            {
                "name": c.name, "tier": c.tier, "tier_label": c.tier_label,
                "weight": c.weight, "visual_traits": c.visual_traits,
                "is_present": c.is_present,
            }
            for c in self._character_registry._chars.values()
        ]

    def remove_character(self, name: str) -> bool:
        """移除一个角色"""
        if name in self._character_registry._chars:
            del self._character_registry._chars[name]
            return True
        return False

    # ── SB-3: 世界观规则管理 ────────────────────────

    def add_world_rule(self, rule_id: str, domain: str, description: str,
                       severity: str = "error",
                       check_keywords: list = None):
        """添加一条世界观规则（SB-3 世界观冲突过滤）"""
        rule = WorldRule(
            rule_id=rule_id, domain=domain, description=description,
            severity=severity, check_keywords=check_keywords or [],
        )
        self._world_rules.add_rule(rule)
        logger.info(f"[StoryboardService] 世界规则已添加: {rule_id} domain={domain}")

    def get_world_rules(self) -> list:
        """获取所有世界观规则"""
        return [
            {
                "rule_id": r.rule_id, "domain": r.domain,
                "description": r.description, "severity": r.severity,
                "check_keywords": r.check_keywords,
            }
            for r in self._world_rules.rules
        ]

    def remove_world_rule(self, rule_id: str) -> bool:
        """移除一条世界观规则"""
        before = len(self._world_rules.rules)
        self._world_rules.rules = [
            r for r in self._world_rules.rules if r.rule_id != rule_id
        ]
        return len(self._world_rules.rules) < before
