"""
作家技法卡（Writer Technique Cards）

HW-2: 40+ 张可组合的作家技法卡，按章节类型自动激活，提供 prompt 注入的写作指导。

分类体系：
- opening (开篇)     — 8 张
- pacing (节奏)      — 7 张
- dialogue (对话)    — 5 张
- description (描写) — 7 张
- tension (张力)     — 6 张
- character (人物)   — 5 张
- style (风格)       — 5 张

用法：
    manager = TechniqueManager()
    cards = manager.activate_for_chapter_type("battle")
    prompt_snippet = manager.build_prompt(cards, max_cards=5)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


# ============================================================
# 数据模型
# ============================================================

@dataclass
class TechniqueCard:
    """单张技法卡"""
    id: str
    name: str
    category: str
    prompt_text: str              # 注入 prompt 的技法指导
    weight: float = 1.0           # 权重，越高越优先激活
    chapter_types: List[str] = field(default_factory=list)  # 适用章节类型
    tags: List[str] = field(default_factory=list)           # 标签


# ============================================================
# 40+ 技法卡库
# ============================================================

TECHNIQUE_CARDS: List[TechniqueCard] = [
    # ============ opening (开篇) — 8 张 ============

    TechniqueCard(
        id="op-01", name="悬念钩子", category="opening", weight=1.0,
        chapter_types=["battle", "climax", "mystery"],
        prompt_text="开篇悬念钩子：前 300 字必须包含一个让读者无法划走的钩子——"
                    "一个反常细节、一句令人不安的话、一个悬而未决的动作。",
    ),
    TechniqueCard(
        id="op-02", name="冷开场", category="opening", weight=0.8,
        chapter_types=["daily", "transition", "emotion"],
        prompt_text="冷开场：从日常细节切入——一杯茶、一阵风、一个眼神——"
                    "而非直接进入情节。让读者先浸入场景氛围再推进。",
    ),
    TechniqueCard(
        id="op-03", name="热开场", category="opening", weight=0.9,
        chapter_types=["battle", "climax"],
        prompt_text="热开场：直接从打斗/冲突/危机中间切入，不给读者喘息机会。"
                    "先制造冲击，再通过回忆或旁白补充上下文。",
    ),
    TechniqueCard(
        id="op-04", name="倒叙钩子", category="opening", weight=0.7,
        chapter_types=["mystery", "climax", "emotion"],
        prompt_text="倒叙钩子：先展示结果（尸体/废墟/离别），再回溯过程。"
                    "用\"三个时辰前\"\"直到多年以后他才明白\"等标记过渡。",
    ),
    TechniqueCard(
        id="op-05", name="对话开场", category="opening", weight=0.7,
        chapter_types=["dialogue", "daily", "emotion"],
        prompt_text="对话开场：第一章第一句就是对话，不带引号归属说明，"
                    "让读者通过内容猜测说话人身份和场景。",
    ),
    TechniqueCard(
        id="op-06", name="场景定锚", category="opening", weight=0.9,
        chapter_types=["setup", "transition", "daily"],
        prompt_text="场景定锚：开篇用一句话锁定时空——\"腊月的风像刀子一样刮过长安城的石板路\""
                    "——同时给出季节、地点、氛围三个信息。",
    ),
    TechniqueCard(
        id="op-07", name="视角锚定", category="opening", weight=1.0,
        chapter_types=["all"],
        prompt_text="视角锚定：首段必须明确当前 POV 角色，用感官描写（看到了什么/听到了什么/闻到了什么）"
                    "而不是旁白声明。禁止开篇即上帝视角。",
    ),
    TechniqueCard(
        id="op-08", name="情绪先行", category="opening", weight=0.8,
        chapter_types=["emotion", "climax"],
        prompt_text="情绪先行：开篇不介绍场景，先写角色的身体感受——心跳、呼吸、肌肉紧绷——"
                    "让读者先感受到情绪再看到画面。",
    ),

    # ============ pacing (节奏) — 7 张 ============

    TechniqueCard(
        id="pc-01", name="短句加速", category="pacing", weight=1.0,
        chapter_types=["battle", "climax"],
        prompt_text="短句加速：战斗/高潮段落使用 3-7 字短句连续 5 句以上，营造窒息感。"
                    "以句号分割，不使用逗号连接。示例：\"拳到。骨裂。血溅三尺。\"",
    ),
    TechniqueCard(
        id="pc-02", name="长句沉缓", category="pacing", weight=0.9,
        chapter_types=["emotion", "daily", "transition"],
        prompt_text="长句沉缓：情感/日常段落使用 20+ 字长句，用逗号制造舒缓的呼吸节奏。"
                    "每段 2-3 句即可，段落间用空行制造留白。",
    ),
    TechniqueCard(
        id="pc-03", name="留白断裂", category="pacing", weight=0.8,
        chapter_types=["climax", "emotion", "mystery"],
        prompt_text="留白断裂：在高潮之后插入一个极短段落（不超过 10 字），"
                    "强制读者停顿。示例：\"然后一切都安静了。\"",
    ),
    TechniqueCard(
        id="pc-04", name="画面切闪", category="pacing", weight=0.8,
        chapter_types=["battle", "climax", "mystery"],
        prompt_text="画面切闪：在关键动作中间突然切换到另一个场景/视角，"
                    "只用空行分隔，不解释过渡。制造紧迫感和信息不对称。",
    ),
    TechniqueCard(
        id="pc-05", name="时间跳跃", category="pacing", weight=0.7,
        chapter_types=["transition", "daily", "setup"],
        prompt_text="时间跳跃：用\"三日后\"\"半个月过去\"等短语直接跳过平淡期，"
                    "不写过渡段落。配合角色状态的细微变化（\"他瘦了一圈\"）暗示时间流逝。",
    ),
    TechniqueCard(
        id="pc-06", name="节奏波形", category="pacing", weight=0.9,
        chapter_types=["all"],
        prompt_text="节奏波形：确保本章至少经历一次完整的\"加速→顶峰→减速\"波形。"
                    "加速段用短句+动作，顶峰用画面切闪或留白断裂，减速段用长句+内心独白。",
    ),
    TechniqueCard(
        id="pc-07", name="多线并进", category="pacing", weight=0.7,
        chapter_types=["climax", "battle"],
        prompt_text="多线并进：高潮章节至少 2 条叙事线同时推进，"
                    "通过快速切换制造\"同时发生\"的紧迫感。每条线 3-5 段即切换。",
    ),

    # ============ dialogue (对话) — 5 张 ============

    TechniqueCard(
        id="dl-01", name="潜台词对话", category="dialogue", weight=1.0,
        chapter_types=["emotion", "mystery", "daily"],
        prompt_text="潜台词对话：角色说的和想的是两回事。每段对话下面隐藏真实的意图。"
                    "用动作描写（\"他摩挲着茶杯的边缘\"）暗示未说出口的话。",
    ),
    TechniqueCard(
        id="dl-02", name="打断战术", category="dialogue", weight=0.8,
        chapter_types=["battle", "climax", "emotion"],
        prompt_text="打断战术：关键对话中至少有 1 次被打断——可以是物理打断（\"砰！门被踹开\"）"
                    "或言语打断（\"够了！\"）。打断点必须恰好卡在最重要的话说到一半。",
    ),
    TechniqueCard(
        id="dl-03", name="沉默即台词", category="dialogue", weight=0.9,
        chapter_types=["emotion", "mystery", "climax"],
        prompt_text="沉默即台词：用沉默替代回答。当角色被问到关键问题时，"
                    "不写回答，写动作、写表情变化、写环境的声响。沉默比任何台词都有力量。",
    ),
    TechniqueCard(
        id="dl-04", name="口语化肌理", category="dialogue", weight=0.9,
        chapter_types=["daily", "transition", "setup"],
        prompt_text="口语化肌理：日常对话中加入语气词、方言词尾、省略主语。"
                    "\"走了啊\"\"嗯\"\"吃了吗\"\"还行吧\"——不需要每句话都传达信息。",
    ),
    TechniqueCard(
        id="dl-05", name="身份口癖", category="dialogue", weight=0.7,
        chapter_types=["all"],
        prompt_text="身份口癖：每个角色有独特的说话方式——官场人物多用敬语和含蓄表达，"
                    "江湖人物直白粗犷，少女多用叠词和反问，老者多用谚语和长句。",
    ),

    # ============ description (描写) — 7 张 ============

    TechniqueCard(
        id="ds-01", name="五感矩阵", category="description", weight=1.0,
        chapter_types=["all"],
        prompt_text="五感矩阵：每个新场景至少覆盖 3 种感官。视觉（颜色/光线）+ 听觉（远近声音）"
                    "+ 触觉（温度/质感）。优先写非视觉感官——气味和触觉比视觉更有沉浸感。",
    ),
    TechniqueCard(
        id="ds-02", name="动作分解", category="description", weight=0.9,
        chapter_types=["battle", "climax"],
        prompt_text="动作分解：关键动作不要一笔带过。\"他拔剑\"→\"右手扣住剑柄，拇指顶开护手，"
                    "腕骨发出轻微的咔哒声，剑身出鞘三寸时寒光已映上他的瞳孔。\"",
    ),
    TechniqueCard(
        id="ds-03", name="类比具象化", category="description", weight=0.8,
        chapter_types=["all"],
        prompt_text="类比具象化：抽象概念用熟悉的事物类比。\"他的灵力磅礴\"→\"他体内的灵力"
                    "像溃堤的洪水，在经脉中横冲直撞，每一次冲击都让他的骨骼发出不堪重负的呻吟。\"",
    ),
    TechniqueCard(
        id="ds-04", name="身体在场", category="description", weight=0.9,
        chapter_types=["emotion", "battle", "climax"],
        prompt_text="身体在场：描写必须有肉体参与。不写\"他很紧张\"，写\"手心的汗浸湿了剑柄的缠绳\"。"
                    "不写\"她很疲惫\"，写\"眼皮像灌了铅，每眨一下都要用尽全身力气\"。",
    ),
    TechniqueCard(
        id="ds-05", name="环境即心境", category="description", weight=0.8,
        chapter_types=["emotion", "mystery"],
        prompt_text="环境即心境：用环境反射角色情绪。悲伤时下雨/阴天，愤怒时燥热/蝉鸣，"
                    "恐惧时幽暗/狭窄。环境描写的主观色彩必须与 POV 角色情绪一致。",
    ),
    TechniqueCard(
        id="ds-06", name="负面美学", category="description", weight=0.7,
        chapter_types=["battle", "climax", "mystery"],
        prompt_text="负面美学：战斗/危机场景写出\"脏\"的感觉——血不是红色的，是\"粘稠的、"
                    "带着铁锈味的温热液体\"。伤口不是\"深可见骨\"，是\"翻卷的皮肉间露出白色的骨茬\"。",
    ),
    TechniqueCard(
        id="ds-07", name="留白式描写", category="description", weight=0.7,
        chapter_types=["mystery", "emotion"],
        prompt_text="留白式描写：不直接描写对象本身，而是写它产生的效果。"
                    "不写怪物长什么样，写\"他听到自己的牙齿在打颤，那是身体比理智更早做出的反应\"。",
    ),

    # ============ tension (张力) — 6 张 ============

    TechniqueCard(
        id="tn-01", name="倒计时", category="tension", weight=1.0,
        chapter_types=["battle", "climax", "mystery"],
        prompt_text="倒计时：设置明确的时间压力——\"还有一炷香的时间\"\"天亮之前必须离开\""
                    "\"毒发还有三个时辰\"。在叙事中反复提醒时间的流逝。",
    ),
    TechniqueCard(
        id="tn-02", name="信息不对称", category="tension", weight=0.9,
        chapter_types=["mystery", "climax", "emotion"],
        prompt_text="信息不对称：读者知道但角色不知道——读者看到反派布下的陷阱，"
                    "主角却毫不知情地走向它。或者角色知道但读者不知道——主角做出了反常举动，"
                    "读者需要继续阅读才能理解。",
    ),
    TechniqueCard(
        id="tn-03", name="选择代价", category="tension", weight=0.9,
        chapter_types=["climax", "emotion", "battle"],
        prompt_text="选择代价：主角必须做出两难选择，且每个选择都有真实的、不可逆的代价。"
                    "不是\"救A还是救B\"的伪选择，而是\"救A=背叛B\"的真实道德困境。",
    ),
    TechniqueCard(
        id="tn-04", name="伏笔回收", category="tension", weight=0.8,
        chapter_types=["climax", "mystery"],
        prompt_text="伏笔回收：回收至少 1 个前文埋下的伏笔。回收方式要出乎意料——"
                    "之前提到的一个看似无用的细节，在此刻成为关键。让读者产生\"原来如此\"的惊喜。",
    ),
    TechniqueCard(
        id="tn-05", name="节拍递增", category="tension", weight=0.8,
        chapter_types=["battle", "climax"],
        prompt_text="节拍递增：冲突每升级一次，赌注就翻倍。回合1：赢了能活，输了受伤。"
                    "回合2：赢了救同伴，输了同伴死。回合3：赢了一切结束，输了世界毁灭。",
    ),
    TechniqueCard(
        id="tn-06", name="假性安全", category="tension", weight=0.7,
        chapter_types=["mystery", "transition", "daily"],
        prompt_text="假性安全：在紧张之后给读者一个喘息窗口——角色以为安全了、危机过去了——"
                    "然后在最放松的时刻给予更猛烈的打击。安全的假象是恐惧的放大器。",
    ),

    # ============ character (人物) — 5 张 ============

    TechniqueCard(
        id="ch-01", name="缺陷驱动", category="character", weight=1.0,
        chapter_types=["all"],
        prompt_text="缺陷驱动：确保本章至少展示主角的 1 个性格缺陷如何影响他的决策。"
                    "骄傲让他拒绝帮助，恐惧让他选择逃避，善良让他被人利用。",
    ),
    TechniqueCard(
        id="ch-02", name="成长回响", category="character", weight=0.8,
        chapter_types=["climax", "emotion", "transition"],
        prompt_text="成长回响：在关键时刻让角色回忆起过去的相似情境，但做出不同的选择。"
                    "用 1-2 句话的闪回展示\"他已经不是当初的那个人了\"。",
    ),
    TechniqueCard(
        id="ch-03", name="配角高光", category="character", weight=0.7,
        chapter_types=["battle", "climax", "daily"],
        prompt_text="配角高光：给 1 个配角一个独立的高光时刻——不是帮主角，而是展示他自己的能力、"
                    "信念或牺牲。让配角短暂地成为他自身故事的主角。",
    ),
    TechniqueCard(
        id="ch-04", name="关系磨损", category="character", weight=0.8,
        chapter_types=["emotion", "daily", "transition"],
        prompt_text="关系磨损：展示一段重要关系中的细微裂痕——一句无心的伤人的话、"
                    "一个被忽略的眼神、一次言不由衷的安慰。裂痕不需要本章修复，但要被读者感知到。",
    ),
    TechniqueCard(
        id="ch-05", name="内部独白", category="character", weight=0.7,
        chapter_types=["emotion", "mystery", "transition"],
        prompt_text="内部独白：在关键决策点插入一段不超过 100 字的内部独白，"
                    "展示角色的思考过程。用斜体或不加引号，用口语化的碎句。",
    ),

    # ============ style (风格) — 5 张 ============

    TechniqueCard(
        id="st-01", name="网文质感", category="style", weight=1.0,
        chapter_types=["all"],
        prompt_text="网文质感：保持短句为主（平均 8-15 字），段落 2-5 行。"
                    "每 500 字至少换一次视角/场景/话题。拒绝纯文学式的长段落和密集描写。",
    ),
    TechniqueCard(
        id="st-02", name="白描克制", category="style", weight=0.7,
        chapter_types=["transition", "daily", "setup"],
        prompt_text="白描克制：在非高潮段落使用白描手法——只写动作和对话，不写内心。"
                    "让读者通过角色的行为来揣测他的想法。海明威式的冰山原则。",
    ),
    TechniqueCard(
        id="st-03", name="排比增强", category="style", weight=0.7,
        chapter_types=["battle", "climax", "emotion"],
        prompt_text="排比增强：在高潮段落使用排比句增强气势。不是单纯的\"他害怕\"，而是"
                    "\"他在害怕。他的手在害怕。他的每一根骨头都在害怕。\"——通过递进式排比放大情绪。",
    ),
    TechniqueCard(
        id="st-04", name="反差放大", category="style", weight=0.8,
        chapter_types=["emotion", "climax", "mystery"],
        prompt_text="反差放大：用极端反差增强效果。用安静衬托暴烈，用笑声衬托悲伤，"
                    "用光线衬托黑暗。反差越大，冲击越强。",
    ),
    TechniqueCard(
        id="st-05", name="回环呼应", category="style", weight=0.7,
        chapter_types=["emotion", "climax"],
        prompt_text="回环呼应：本章结尾的某个意象/句子与开篇呼应，形成闭环结构。"
                    "开篇写\"杯子里的茶已经凉了\"，结尾写\"他把那杯凉透的茶一饮而尽\"。",
    ),
]

# 验证卡片数量
assert len(TECHNIQUE_CARDS) >= 40, f"技法卡不足 40 张，当前 {len(TECHNIQUE_CARDS)} 张"


# ============================================================
# 技法管理器
# ============================================================

class TechniqueManager:
    """作家技法卡管理器

    按章节类型自动激活技法卡，支持加权随机选取。
    单次最多激活 5 张，避免 prompt 过载。
    """

    # 章节类型映射别名
    TYPE_ALIASES: Dict[str, List[str]] = {
        "battle": ["battle", "climax"],
        "climax": ["climax", "battle", "emotion"],
        "emotion": ["emotion", "daily"],
        "daily": ["daily", "transition"],
        "transition": ["transition", "daily", "setup"],
        "setup": ["setup", "transition"],
        "mystery": ["mystery", "climax"],
    }

    def activate_for_chapter_type(self, chapter_type: str) -> List[TechniqueCard]:
        """按章节类型激活技法卡

        规则：
        1. 匹配 chapter_type 精确或别名（TYPE_ALIASES）
        2. "all" 类型始终激活
        3. 按权重排序，取前 8 张候选
        4. 加权随机选 5 张
        """
        # 获取可匹配的类型列表
        match_types = set(self.TYPE_ALIASES.get(chapter_type, [chapter_type]))
        match_types.add("all")

        # 筛选可激活的卡
        candidates: List[tuple] = []  # (card, weight)
        seen_ids: Set[str] = set()

        for card in TECHNIQUE_CARDS:
            if card.id in seen_ids:
                continue
            card_types = set(card.chapter_types) if card.chapter_types else {"all"}
            if card_types & match_types:
                candidates.append((card, card.weight))
                seen_ids.add(card.id)

        # 按权重降序排序
        candidates.sort(key=lambda x: -x[1])

        # 取前 8 张候选
        pool = candidates[:8]

        if len(pool) <= 5:
            return [p[0] for p in pool]

        # 加权随机选 5 张（不放回）
        selected: List[TechniqueCard] = []
        remaining = list(pool)

        for _ in range(5):
            if not remaining:
                break
            total_weight = sum(w for _, w in remaining)
            r = random.uniform(0, total_weight)
            cumulative = 0.0
            chosen_idx = 0
            for idx, (card, w) in enumerate(remaining):
                cumulative += w
                if r <= cumulative:
                    chosen_idx = idx
                    break
            selected.append(remaining[chosen_idx][0])
            remaining.pop(chosen_idx)

        return selected

    @staticmethod
    def build_prompt(cards: List[TechniqueCard], max_cards: int = 5) -> str:
        """将技法卡转换为 prompt 注入文本"""
        if not cards:
            return ""

        lines = ["\n\n## 本章推荐技法"]
        for i, card in enumerate(cards[:max_cards], 1):
            lines.append(f"### 技法{i}. {card.name}（{card.category}）")
            lines.append(card.prompt_text)
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def list_cards_by_category() -> Dict[str, List[TechniqueCard]]:
        """按类别列出所有技法卡"""
        groups: Dict[str, List[TechniqueCard]] = {}
        for card in TECHNIQUE_CARDS:
            groups.setdefault(card.category, []).append(card)
        return groups

    @staticmethod
    def get_card_by_id(card_id: str) -> Optional[TechniqueCard]:
        """按 ID 获取单张卡"""
        for card in TECHNIQUE_CARDS:
            if card.id == card_id:
                return card
        return None
