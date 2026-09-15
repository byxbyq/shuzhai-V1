"""
scene_d 8 条写作纪律（HW-1）

参考行业场景纪律规范，在现有 5 条"祛除AI结构化痕迹"基础上
扩展为 8 条完整纪律体系，同时提供运行时检测能力。

8 条纪律：
1. 无用闲笔 — 碎片细节，不回收，每章 2-3 处
2. 情绪多层错位 — 表面行为 vs 内心真实，至少两层
3. 对话不规整 — 30% 非完整句，打断/抢话/沉默
4. 世界观展示禁旁白 — 通过身体感受/他人反应/冲突展示
5. 节奏变速 — 每章 3 次明显变速
6. 感官先行 — 先写身体反应，不写情绪标签
7. 场景是活的 — 写烟尘/血腥/震感/气味/温度
8. 信息喂不灌 — 新设定需 3 次渐进式提及才可完整展开

用法：
    from backend.services.scene_d_discipline import SceneDChecker
    checker = SceneDChecker()
    report = checker.check(content)  # 运行时检测
    prompt_text = checker.get_prompt_instructions()  # prompt 注入文本
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List


# ============================================================
# 纪律定义
# ============================================================

@dataclass
class DisciplineRule:
    """单条写作纪律"""
    id: str
    name: str
    category: str          # structure / emotion / sensory / delivery
    description: str        # 简短说明
    prompt_text: str        # 注入 prompt 的指导文本
    check_description: str  # 运行时检测说明
    severity: str = "medium"  # high / medium / low


SCENE_D_RULES: List[DisciplineRule] = [
    DisciplineRule(
        id="sd-1",
        name="无用闲笔",
        category="structure",
        description="碎片细节，不承担叙事功能，不回收，每章 2-3 处",
        prompt_text="允许无用闲笔：碎片细节（路边的野花、墙角的蛛网、路人甲的闲谈），"
                    "不承担叙事推进功能，不回收，不暗示伏笔。每章至少 2-3 处纯粹的\"装饰性\"细节。",
        check_description="检测是否存在至少 2 处不承担叙事功能的装饰性细节",
        severity="low",
    ),
    DisciplineRule(
        id="sd-2",
        name="情绪多层错位",
        category="emotion",
        description="表面行为 vs 内心真实，至少两层情绪并置",
        prompt_text="情绪多层错位：角色表面行为与内心真实感受必须存在错位。"
                    "如\"笑着说狠话\"\"平静地崩溃\"\"愤怒时反而安静\"。"
                    "每场关键对话/冲突场景至少展示两层情绪。",
        check_description="检测是否存在表面行为和内心感受的矛盾描写",
        severity="medium",
    ),
    DisciplineRule(
        id="sd-3",
        name="对话不规整",
        category="structure",
        description="30% 非完整句，打断/抢话/沉默/含糊/跑题",
        prompt_text="对话不规整：对话中 30% 应为非完整句——打断、抢话、沉默（用省略号表示）、"
                    "话题被岔开、答非所问、含糊其辞。避免一问一答的僵硬模式。",
        check_description="统计对话中非完整句比例，低于 25% 触发",
        severity="medium",
    ),
    DisciplineRule(
        id="sd-4",
        name="世界观展示禁旁白",
        category="delivery",
        description="设定通过身体感受/他人反应/冲突展示，禁止叙述旁白",
        prompt_text="世界观展示禁止旁白：新设定/世界观信息必须通过角色身体感受、"
                    "他人反应、冲突或意外后果来展示，禁止以叙述者口吻直接介绍。"
                    "如\"灵力运转时会灼烧经脉\"应写成\"他运起灵力，经脉传来灼痛，"
                    "仿佛有人将烧红的铁钎捅进了骨头缝里。\"",
        check_description="检测是否存在叙述者口吻的世界观介绍句式",
        severity="high",
    ),
    DisciplineRule(
        id="sd-5",
        name="节奏变速",
        category="structure",
        description="每章 3 次明显变速：短句轰炸→留白→画面切闪",
        prompt_text="节奏必须变速：每章至少 3 次明显的节奏切换。"
                    "① 短句轰炸（3-7字连续5句以上）→ ② 留白段落（单行，不超过15字）→ ③ 画面切闪（场景/视角突然切换）。",
        check_description="检测章节中是否存在 3 次以上的节奏切换模式",
        severity="medium",
    ),
    DisciplineRule(
        id="sd-6",
        name="感官先行",
        category="sensory",
        description="先写身体反应，不写情绪标签",
        prompt_text="感官先行：不要写\"他很害怕\"，写\"他的手心渗出冷汗，心跳快得像要从嗓子眼蹦出来\"。"
                    "不要写\"她很开心\"，写\"她嘴角压都压不住地上扬，脚步轻得像是踩在云上\"。"
                    "所有情绪必须通过身体感受来传递，禁止使用情绪标签词直接标注。",
        check_description="检测情绪标签词（高兴/愤怒/悲伤/恐惧/惊讶/紧张）的直接使用",
        severity="high",
    ),
    DisciplineRule(
        id="sd-7",
        name="场景是活的",
        category="sensory",
        description="写烟尘/血腥/震感/气味/温度/光线，让场景有物理存在感",
        prompt_text="场景是活的：每个场景必须有至少一种物理感官描写——烟尘、血腥、震感、"
                    "气味（霉味/血腥/花香/金属）、温度（阴冷/燥热/闷湿）、光线（刺眼/昏暗/摇曳）。"
                    "场景不是背景布，它的状态必须与人物的状态产生互动。",
        check_description="检测每个主要场景是否包含至少一种物理感官描写",
        severity="low",
    ),
    DisciplineRule(
        id="sd-8",
        name="信息喂不灌",
        category="delivery",
        description="新设定需 3 次渐进提及才可完整展开",
        prompt_text="信息喂不灌：新设定（功法体系、势力格局、世界观规则）不能在首次出现时直接展开。"
                    "必须通过至少 3 次渐进式提及——① 一句话顺带提及 ② 场景中间接触及 ③ 剧情需要时才完整展开。"
                    "每次提及增加一层深度，但绝不倾倒。",
        check_description="检测是否存在新设定一次性大段展开",
        severity="medium",
    ),
]

# 按 severity 排序
SCENE_D_RULES.sort(key=lambda r: {"high": 0, "medium": 1, "low": 2}[r.severity])


# ============================================================
# 运行时检测器
# ============================================================

class SceneDChecker:
    """scene_d 纪律运行时检测器

    纯规则检测，零 AI 调用，毫秒级完成。
    """

    # 情绪标签词（避免直接使用）
    EMOTION_LABELS = [
        "高兴", "愤怒", "悲伤", "恐惧", "惊讶", "紧张", "兴奋",
        "沮丧", "绝望", "焦虑", "烦躁", "厌恶", "嫉妒", "羞愧",
        "尴尬", "得意", "满足", "遗憾", "后悔", "欣慰",
    ]

    # 旁白式世界观介绍句式
    NARRATION_PATTERNS = [
        r"在这个世界[里中]?，.{0,30}(?:是|有着|存在|分为)",
        r".{0,20}(?:大陆|帝国|宗门|功法|灵力|修为) (?:分为|共分|可|能够|拥有)",
        r"所谓.{2,15}，就是.{2,40}",
        r"这就要从.{2,20}说起[了]?",
    ]

    # 感官词汇
    SENSORY_WORDS = {
        "visual": ["光", "暗", "亮", "影", "色", "烁", "芒", "晖", "辉",
                    "刺眼", "昏暗", "摇曳", "幽暗", "明亮", "朦胧"],
        "auditory": ["声", "响", "鸣", "啸", "震", "吼", "嗡", "轰",
                      "沙沙", "噼啪", "咔嚓", "哗啦", "呼啸", "爆裂"],
        "tactile": ["冷", "热", "凉", "暖", "烫", "痛", "麻", "痒", "刺",
                    "灼热", "冰凉", "刺痛", "麻木", "酥麻", "沉重"],
        "olfactory": ["味", "香", "臭", "腥", "霉", "腐", "酸", "苦",
                       "花香", "血腥", "药香", "焦糊", "泥土"],
    }

    def check(self, content: str) -> Dict[str, Any]:
        """执行全部 8 条纪律的运行时检测

        Returns:
            {
                "passed": bool,
                "score": float (0-1),
                "violations": [{rule_id, rule_name, severity, message, evidence}],
                "stats": {...},
            }
        """
        violations: List[Dict[str, Any]] = []
        stats: Dict[str, Any] = {}

        for rule in SCENE_D_RULES:
            result = self._check_rule(content, rule)
            stats[rule.id] = result
            if result.get("violated"):
                violations.append({
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "severity": rule.severity,
                    "message": result["message"],
                    "evidence": result.get("evidence", []),
                })

        passed = not any(v["severity"] == "high" for v in violations)
        # 评分：8 条中通过的比例
        score = 1.0 - len(violations) / len(SCENE_D_RULES)

        return {
            "passed": passed,
            "score": round(score, 2),
            "violations": violations,
            "violation_count": len(violations),
            "stats": stats,
        }

    def _check_rule(self, content: str, rule: DisciplineRule) -> Dict[str, Any]:
        """检测单条纪律"""
        method_name = f"_check_{rule.id.replace('-', '_')}"
        method = getattr(self, method_name, None)
        if method:
            return method(content)
        return {"violated": False, "message": ""}

    # --- sd-1: 无用闲笔 ---

    def _check_sd_1(self, content: str) -> Dict[str, Any]:
        """检测是否存在装饰性细节"""
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        # 启发式：包含环境/物品细节但不含叙事推进关键词的段落
        decorative_hints = ["角落", "墙", "路边", "缝隙", "蛛网", "灰尘", "野花",
                            "杂草", "碎屑", "残片", "旧", "斑驳", "苔藓", "水渍"]
        narrative_hints = ["突然", "忽然", "紧接着", "于是", "然而", "不料",
                           "原来", "竟然", "才发现", "这意味着"]
        decorative_count = 0
        for p in paragraphs:
            has_decor = any(h in p for h in decorative_hints)
            has_narrative = any(h in p for h in narrative_hints)
            if has_decor and not has_narrative:
                decorative_count += 1

        if decorative_count >= 2:
            return {"violated": False, "message": "", "count": decorative_count}
        return {
            "violated": True,
            "message": f"装饰性细节不足（检测到 {decorative_count} 处，建议 >= 2）",
            "count": decorative_count,
        }

    # --- sd-2: 情绪多层错位 ---

    def _check_sd_2(self, content: str) -> Dict[str, Any]:
        """检测表面行为与内心感受的矛盾"""
        # 矛盾对：笑 vs 冷/痛/怒，平静 vs 崩溃/汹涌，愤怒 vs 安静/沉默
        contradiction_pairs = [
            (r"笑.{0,20}(?:冷|痛|狠|残忍|苦涩)", "笑 / 冷"),
            (r"(?:平静|冷静|淡定).{0,20}(?:崩溃|汹涌|翻涌|狂跳)", "平静 / 汹涌"),
            (r"(?:愤怒|暴怒|盛怒).{0,20}(?:安静|沉默|不语|平静)", "愤怒 / 安静"),
        ]
        found = []
        for pattern, label in contradiction_pairs:
            if re.search(pattern, content):
                found.append(label)

        if len(found) >= 1:
            return {"violated": False, "message": "", "found": found}
        return {
            "violated": True,
            "message": f"未检测到情绪多层错位（建议 >= 1 处表面-内心矛盾描写）",
            "found": found,
        }

    # --- sd-3: 对话不规整 ---

    def _check_sd_3(self, content: str) -> Dict[str, Any]:
        """统计对话非完整句比例"""
        # 提取对话行（以引号开头或包含引号的行）
        dialogue_lines = re.findall(r'[""「」](.{2,60})[""「」]', content)
        if not dialogue_lines:
            return {"violated": False, "message": "无对话内容", "ratio": 1.0}

        # 非完整句特征：省略号、破折号、1-3 字短句、被截断
        incomplete = 0
        for line in dialogue_lines:
            if "…" in line or "……" in line:
                incomplete += 1
            elif len(line.strip()) <= 5:
                incomplete += 1
            elif "——" in line:
                incomplete += 1
            elif re.match(r"^[嗯啊哦呃咦唔哼呵]$", line.strip()):
                incomplete += 1

        ratio = incomplete / len(dialogue_lines) if dialogue_lines else 0
        if ratio >= 0.25:
            return {"violated": False, "message": "", "ratio": round(ratio, 2)}
        return {
            "violated": True,
            "message": f"对话非完整句比例 {ratio:.0%}，低于 25% 阈值",
            "ratio": round(ratio, 2),
        }

    # --- sd-4: 世界观展示禁旁白 ---

    def _check_sd_4(self, content: str) -> Dict[str, Any]:
        """检测旁白式世界观介绍"""
        evidence = []
        for pattern in self.NARRATION_PATTERNS:
            for match in re.finditer(pattern, content):
                snippet = match.group(0)[:60]
                evidence.append(snippet)

        if not evidence:
            return {"violated": False, "message": ""}
        return {
            "violated": True,
            "message": f"检测到 {len(evidence)} 处旁白式世界观介绍",
            "evidence": evidence[:3],
        }

    # --- sd-5: 节奏变速 ---

    def _check_sd_5(self, content: str) -> Dict[str, Any]:
        """检测节奏切换模式"""
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if len(paragraphs) < 5:
            return {"violated": False, "message": "段落过少", "switches": 0}

        switches = 0
        prev_length = len(paragraphs[0])

        for i in range(1, len(paragraphs)):
            curr_length = len(paragraphs[i])
            # 段落长度突变（>3倍或<1/3）视为节奏切换
            if prev_length > 0 and (
                curr_length > prev_length * 3 or curr_length < prev_length / 3
            ):
                switches += 1
            prev_length = curr_length

        if switches >= 3:
            return {"violated": False, "message": "", "switches": switches}
        return {
            "violated": True,
            "message": f"节奏变速 {switches} 次，未达 3 次阈值",
            "switches": switches,
        }

    # --- sd-6: 感官先行 ---

    def _check_sd_6(self, content: str) -> Dict[str, Any]:
        """检测情绪标签词直接使用"""
        found = []
        for label in self.EMOTION_LABELS:
            # 使用正则精确匹配
            matches = list(re.finditer(re.escape(label), content))
            if matches:
                # 检查上下文：如果在引号内（对话中）则不算违规
                for m in matches:
                    pos = m.start()
                    before = content[max(0, pos - 100):pos]
                    # 简单判断：前面有引号且无配对闭合引号 → 对话中
                    if before.count('"') % 2 == 1 or before.count('「') > before.count('」'):
                        continue
                    found.append({
                        "label": label,
                        "position": pos,
                        "context": content[max(0, pos - 10):pos + len(label) + 10],
                    })

        if not found:
            return {"violated": False, "message": ""}
        return {
            "violated": True,
            "message": f"直接使用情绪标签词 {len(found)} 次：{', '.join(set(f['label'] for f in found[:5]))}",
            "labels": [f["label"] for f in found],
        }

    # --- sd-7: 场景是活的 ---

    def _check_sd_7(self, content: str) -> Dict[str, Any]:
        """检测物理感官描写覆盖率"""
        # 按段落分组为场景（连续段落）
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if len(paragraphs) < 3:
            return {"violated": False, "message": ""}

        # 将段落分场景：每 3-5 段为一个场景
        scene_size = max(3, len(paragraphs) // 4)
        scenes = [paragraphs[i:i + scene_size] for i in range(0, len(paragraphs), scene_size)]
        scenes = [s for s in scenes if len(s) >= 2]  # 过滤过短场景

        missing_senses = 0
        for scene in scenes:
            scene_text = " ".join(scene)
            has_sensory = False
            for sense_type, words in self.SENSORY_WORDS.items():
                if any(w in scene_text for w in words):
                    has_sensory = True
                    break
            if not has_sensory:
                missing_senses += 1

        if missing_senses == 0:
            return {"violated": False, "message": ""}
        return {
            "violated": True,
            "message": f"{missing_senses}/{len(scenes)} 个场景缺少物理感官描写",
            "missing": missing_senses,
            "total_scenes": len(scenes),
        }

    # --- sd-8: 信息喂不灌 ---

    def _check_sd_8(self, content: str) -> Dict[str, Any]:
        """检测设定一次性大段展开"""
        # 启发式：包含"分为""共分""可分为""包括""有以下"等分类引导词的段落
        # 且段落长度 > 200 字符 → 可能是一次性展开
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        dump_patterns = [
            r"(?:分为|共分|可分为|包括|拥有) .{0,20}(?:种|类|层|级|阶|重|品|等)",
            r"(?:共有|总计|合计) .{0,10}(?:种|类|层|级)",
            r"(?:第一.{0,5}是|首先|其一).*(?:第二|其次|其二).*(?:第三|再次|其三)",
        ]

        evidence = []
        for p in paragraphs:
            if len(p) < 200:
                continue
            for pat in dump_patterns:
                if re.search(pat, p):
                    evidence.append(p[:80] + "...")
                    break

        if not evidence:
            return {"violated": False, "message": ""}
        return {
            "violated": True,
            "message": f"检测到 {len(evidence)} 处可能的设定一次性展开",
            "evidence": evidence[:2],
        }

    # --- 生成 prompt 注入文本 ---

    @staticmethod
    def get_prompt_instructions(max_rules: int = 8) -> str:
        """生成用于 prompt 注入的纪律指导文本"""
        lines = ["\n\n## scene_d 写作纪律（必须遵守）\n"]
        for rule in SCENE_D_RULES[:max_rules]:
            lines.append(f"### {rule.id}. {rule.name}")
            lines.append(f"{rule.prompt_text}\n")
        return "\n".join(lines)

    @staticmethod
    def get_rules_by_category() -> Dict[str, List[DisciplineRule]]:
        """按类别分组返回"""
        groups: Dict[str, List[DisciplineRule]] = {}
        for rule in SCENE_D_RULES:
            groups.setdefault(rule.category, []).append(rule)
        return groups
