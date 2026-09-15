# -*- coding: utf-8 -*-
"""
小说蒸馏服务 - 将爆款小说蒸馏为可执行写作技能包
基于 novel-distiller 的 RIA-TV++ 流水线，适配书斋V65

核心流程：
  阶段0: 整书理解 (Adler改编法)
  阶段1: 五路并行提取 (情节/技法/场景/反面/世界观设计方法)
  阶段1.5: 三重验证 (跨章佐证/预测力/独特性)
  阶段2: RIA++构造 (R原文/I方法论/A1案例/A2触发/E执行/B边界)
"""

import os
import re
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# 书斋自身的 AI 服务
from backend.ai_client import AIClient


# ============================================================
# 常量
# ============================================================

MAX_INPUT_CHARS = 80000
SAMPLE_CHARS = 60000

EXTRACTORS = {
    "plot": "情节结构提取器",
    "tech": "写作技法提取器",
    "scene": "场景实例提取器",
    "anti": "烂俗套路提取器",
    "world": "世界观设计提取器",
}

EXTRACTOR_PROMPTS = {}


def _load_extractor_prompts():
    """加载5个提取器的 system prompt。"""
    global EXTRACTOR_PROMPTS

    EXTRACTOR_PROMPTS["plot"] = """你是资深小说编辑兼叙事学研究者，擅长拆解畅销小说的结构骨架。

## 你的任务
阅读给定的小说文本，提取作者使用的**情节结构技巧**。不要提取具体剧情内容，而是提取"作者怎么编排情节"的**可迁移方法论**。

## 识别范围
1. 三幕式结构变体 - 铺垫/冲突/解决的编排方式
2. 多线交叉 - 主线与支线的交织时机、信息差的制造与释放
3. 倒叙插叙 - 时间线打乱的手法、回忆切入时机
4. 悬念递进 - 信息隐藏与揭示的节奏、谜题分层投放
5. 高潮转折 - 情绪最高点的构建方法、反转的铺垫技巧
6. 结尾悬念 - 章末钩子设计、卷尾留白、埋线技巧
7. 节奏控制 - 快慢交替的张弛设计、信息密度变化
8. 升级节奏 - 升级曲线、战力膨胀控制、爽点投放频率

## 提取要求
每条候选必须包含以下字段，**source_quote 必须是原文直接引用，不超过150字**：
- id: 唯一标识，格式 plot-序号（如 plot-001）
- title: 简洁标题，概括这个结构技巧
- type: 结构类型，从以下选一：three-act/multi-thread/flashback/suspense-progression/climax-twist/ending-hook/pacing/progression-curve
- source_chapter: 原文出处章节（如"第12章"）
- source_quote: 原文直接引用，≤150字
- summary: 2-4句话概括这个技巧怎么做，以及为什么有效
- tags: 3-5个标签

## 提取原则
1. 只提取可迁移的方法论，不复述剧情
2. 必须基于原文证据，每条候选都要有原文引用
3. 优先提取反复出现的模式

请输出 YAML 格式的候选列表。"""

    EXTRACTOR_PROMPTS["tech"] = """你是资深网文编辑兼写作技法研究者，擅长分析作者的文字层面技巧。

## 你的任务
从小说文本中提取**笔法套路和写作技法**——不是写了什么，而是怎么写的。

## 识别范围
1. 视角切换 -  POV切换时机、信息控制权的转移
2. 信息控制 - 隐瞒/揭示的节奏、伏笔投放密度
3. 节奏控制 - 句子长短变化、段落密度、场景切换频率
4. 情绪操控 - 读者情绪的调动手法、共情建立技巧
5. 对话技法 - 潜台词设计、对话中的信息差、对话推动情节
6. 心理描写 - 内心独白的切入时机、意识流技巧
7. 环境烘托 - 情景交融、以景衬情、氛围营造
8. 悬念笔法 - 叙述性诡计、不可靠叙述、误导技巧

## 提取要求
每条候选必须包含：
- id: tech-序号（如 tech-001）
- title: 简洁标题
- type: 技法类型：perspective/information-control/pacing/emotion/dialogue/psychology/environment/suspense
- source_chapter: 出处章节
- source_quote: 原文引用，≤150字
- summary: 2-4句话概括技法和效果
- tags: 3-5个标签

请输出 YAML 格式。"""

    EXTRACTOR_PROMPTS["scene"] = """你是场景构建专家，擅长分析小说中各类场景的写作公式。

## 你的任务
从小说中提取**可复用的场景构建公式**——特定类型场景的标准写法。

## 识别范围
1. 开头钩子 - 小说开篇、章节开头的钩子设计
2. 战斗场景 - 战斗描写的节奏、视角、爽点设计
3. 对话场景 - 多人对话、对峙、谈判的写法
4. 心理场景 - 内心挣扎、顿悟、抉择时刻
5. 环境场景 - 新地图登场、世界观展示场景
6. 揭秘场景 - 真相揭露、伏笔回收的写法
7. 情感场景 - 生离死别、重逢、告白等情感高潮
8. 日常场景 - 过渡章节、轻松调剂的写法

## 提取要求
每条候选必须包含：
- id: scene-序号（如 scene-001）
- title: 场景类型 + 核心技巧（如"战斗场景：三段式升级法"）
- type: 场景类型：opening/battle/dialogue/psychology/worldbuilding/reveal/emotion/slice-of-life
- source_chapter: 出处章节
- source_quote: 原文引用，≤200字
- summary: 2-4句话概括这个场景公式怎么构建
- tags: 3-5个标签

请输出 YAML 格式。"""

    EXTRACTOR_PROMPTS["anti"] = """你是网文质量检测专家，擅长识别烂俗套路和写作问题。

## 你的任务
从小说中提取**反面教材**——作者踩过的坑、烂俗桥段、质量问题，以及（如果有的话）作者是如何补救的。

## 识别范围
1. AI味重的写法 - 模板化表达、空洞形容词、无信息量排比
2. 烂俗桥段 - 退婚流、系统流、赘婿流等过度使用的套路
3. 降智情节 - 角色智商掉线、为推动剧情牺牲逻辑
4. 逻辑漏洞 - 设定矛盾、时间线混乱、行为动机不明
5. 节奏灾难 - 拖沓冗长、信息密度过低、灌水章节
6. 人物崩坏 - OOC（Out of Character）、人设前后不一
7. 爽点失效 - 铺垫不足、反派太弱、打脸不够爽
8. 情感虚假 - 尬哭、尬笑、情绪转折突兀

## 提取要求
每条候选必须包含：
- id: anti-序号（如 anti-001）
- title: 问题类型 + 具体表现（如"战斗场景：反派降智"）
- type: 问题类型：ai-flavor/cliche/stupid-plot/plot-hole/pacing-disaster/ooc/payoff-failure/emotion-fake
- source_chapter: 出处章节
- source_quote: 原文引用，≤150字
- summary: 2-3句话描述问题是什么，以及为什么是问题
- improvement: 如果作者在别处有补救或优化，写出来；否则空着
- tags: 3-5个标签

请输出 YAML 格式。"""

    EXTRACTOR_PROMPTS["world"] = """你是世界观架构师，擅长分析虚构世界的构建方法。

## 你的任务
从小说中提取**世界观设计方法**——不是世界观的内容是什么，而是作者怎么设计和展现世界观的。

## 识别范围
1. 能力体系设计 - 力量等级、修炼体系、能力规则的构建方法
2. 社会结构设计 - 势力格局、阶级制度、组织架构
3. 地理环境设计 - 地图设计、地域特色、场景空间感
4. 规则设定方法 - 世界规则的揭示节奏、冰山理论的运用
5. 设定融入叙事 - 如何通过剧情自然展示设定而非堆砌
6. 势力关系设计 - 多方势力的制衡、利益纠葛、合纵连横
7. 文化习俗设计 - 语言、服饰、礼仪、节日等文化细节
8. 历史背景构建 - 世界历史如何影响当前故事

## 提取要求
每条候选必须包含：
- id: world-序号（如 world-001）
- title: 设计方法名称（如"能力体系：分级命名法"）
- type: 设计类型：power-system/social-structure/geography/rule-revelation/show-don't-tell/faction-relations/culture-customs/history-building
- source_chapter: 出处章节
- source_quote: 原文引用，≤150字
- summary: 2-4句话概括这个设计方法的核心和效果
- tags: 3-5个标签

请输出 YAML 格式。"""


_load_extractor_prompts()


# ============================================================
# 工具函数
# ============================================================

def split_chapters(text: str) -> list:
    patterns = [
        r'^第[零一二三四五六七八九十百千万\d]+[章节回卷][^\n]*',
        r'^Chapter\s+\d+',
        r'^第\d+章',
        r'^\d+[、.\s]',
    ]
    combined = '|'.join(f'(?m:{p})' for p in patterns)
    splits = re.split(combined, text)
    chapters = [s.strip() for s in splits if s.strip()]
    return chapters


def sample_text(text: str, max_chars: int = SAMPLE_CHARS) -> str:
    total = len(text)
    if total <= max_chars:
        return text
    third = max_chars // 3
    head = text[:third]
    mid_start = total // 2 - third // 2
    mid = text[mid_start:mid_start + third]
    tail = text[total - third:]
    parts = [
        f"【开头部分】\n{head}",
        f"【中间部分】\n{mid}",
        f"【结尾部分】\n{tail}",
    ]
    return "\n\n...\n\n".join(parts)


def parse_yaml_candidates(text: str) -> list:
    code_match = re.search(r'```ya?ml\s*\n(.*?)```', text, re.DOTALL)
    yaml_text = code_match.group(1) if code_match else text

    candidates = []
    current = {}

    for line in yaml_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- id:"):
            if current:
                candidates.append(current)
            current = {"id": stripped.split(":", 1)[1].strip().strip('"').strip("'")}
        elif current and ":" in stripped:
            parts = stripped.split(":", 1)
            key = parts[0].strip().lstrip("-")
            val = parts[1].strip() if len(parts) > 1 else ""
            val = val.strip('"').strip("'")
            if key == "tags":
                val = [t.strip().strip('"').strip("'") for t in val.strip("[]").split(",") if t.strip()]
            current[key] = val

    if current:
        candidates.append(current)
    return candidates


def slugify(text: str) -> str:
    slug = re.sub(r'[^\w\u4e00-\u9fff]+', '-', text).strip('-').lower()
    return slug[:60] if slug else "unnamed"


def _ai_generate(system_prompt: str, user_content: str, temperature: float = 0.7,
                  max_tokens: int = 4096) -> str:
    """使用书斋的 AI 服务生成内容。"""
    ai = AIClient()
    full_prompt = f"{system_prompt}\n\n用户：{user_content}"
    result = ai.generate(full_prompt, temperature=temperature, max_tokens=max_tokens)
    return result


# ============================================================
# 格式适配：content 对象 → markdown 字符串
# ============================================================

def content_object_to_markdown(content: dict, skill_name: str = "") -> str:
    """
    将 novel-distiller 的 content 对象转为 markdown 字符串，
    以适配书斋V65的技能包体系（content 字段期望字符串）。

    RIA++ 六要素 → markdown 格式
    """
    if not content:
        return ""

    if isinstance(content, str):
        return content

    parts = []

    if skill_name:
        parts.append(f"# {skill_name}")
        parts.append("")

    reading = content.get("reading", "")
    if reading:
        parts.append("## 原文引用 (Reading)")
        parts.append("")
        parts.append(f"> {reading}")
        parts.append("")

    interpretation = content.get("interpretation", "")
    if interpretation:
        parts.append("## 方法论 (Interpretation)")
        parts.append("")
        parts.append(interpretation)
        parts.append("")

    example = content.get("example", "")
    if example:
        parts.append("## 书中案例 (Example)")
        parts.append("")
        parts.append(example)
        parts.append("")

    trigger = content.get("trigger", "")
    if trigger:
        parts.append("## 触发场景 (Trigger)")
        parts.append("")
        parts.append(trigger)
        parts.append("")

    execution = content.get("execution", "")
    if execution:
        parts.append("## 可执行步骤 (Execution)")
        parts.append("")
        parts.append(execution)
        parts.append("")

    boundary = content.get("boundary", "")
    if boundary:
        parts.append("## 边界与限制 (Boundary)")
        parts.append("")
        parts.append(boundary)
        parts.append("")

    return "\n".join(parts)


# ============================================================
# 单章蒸馏函数
# ============================================================

def distill_single_chapter(chapter_text: str, chapter_index: int, prev_state: dict = None) -> dict:
    """单章蒸馏：将一章正文蒸馏为 5 维结构化摘要 JSON，总长不超过 800 字符。

    Args:
        chapter_text: 本章正文文本
        chapter_index: 章节序号
        prev_state: 前章蒸馏结果（用于衔接锚对比），可选

    Returns:
        5 维结构化摘要 dict:
        {
            "chapter_index": int,
            "characters": [{"name": str, "location": str, "mood": str, "realm": str, "items": [str], "alive": bool}],
            "events": [str],           # 1-3 个核心事件，每个一句话
            "foreshadowing": {"planted": [{"content": str, "expected_chapter": int}], "resolved": [{"content": str, "method": str}]},
            "new_settings": [str],     # 新引入的规则/道具/世界观概念
            "bridge": {"from_prev": str, "to_next": str}  # 衔接锚
        }
    """
    ai = AIClient()

    # 章节正文截取前 8000 字符
    trimmed = chapter_text[:8000]

    # 前章状态片段
    prev_context = ""
    if prev_state:
        prev_summary = json.dumps(prev_state, ensure_ascii=False, indent=2)
        prev_context = f"\n【前章蒸馏摘要（用于衔接对比）】\n{prev_summary[:1500]}\n"

    system_prompt = """你是小说章节蒸馏专家。你的任务是将一章小说正文蒸馏为严格 JSON 格式的 5 维结构化摘要。

5 个维度说明：
1. characters：本章结束时每个角色的状态（name/位置/心绪/境界/持有物/存活）。只写有变化的角色。无变化则写空数组。
2. events：本章 1-3 个核心事件，每个一句话（≤30字）。
3. foreshadowing：本章种的伏笔（planted: content+预计回收章）和回收的伏笔（resolved: content+回收方式）。无则写空对象。
4. new_settings：本章新引入的规则/道具/世界观概念（每个≤20字）。无则写空数组。
5. bridge：from_prev 承接上章的状态点（≤40字），to_next 留给下章的状态点（≤40字）。

重要约束：
- 总输出 JSON 文本不超过 800 字符
- 只写有变化/有信息量的维度
- characters 中只包含本章状态发生变化的角色
- 严格 JSON 格式，不要输出任何其他内容"""

    user_prompt = f"""请蒸馏以下小说章节。

【第 {chapter_index} 章正文】
{trimmed}
{prev_context}
请输出严格 JSON，总长不超过 800 字符。"""

    try:
        result = ai.generate(
            system_prompt + "\n\n" + user_prompt,
            temperature=0.3,
            max_tokens=1024
        )
        # 提取 JSON
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            result = json_match.group(0)
        data = json.loads(result)
        data["chapter_index"] = chapter_index
        # 确保必填字段存在
        data.setdefault("characters", [])
        data.setdefault("events", [])
        data.setdefault("foreshadowing", {})
        data.setdefault("new_settings", [])
        data.setdefault("bridge", {"from_prev": "", "to_next": ""})
        return data
    except Exception as e:
        logger.warning("单章蒸馏失败，返回空结构: %s", e)
        # 降级：返回空结构
        return {
            "chapter_index": chapter_index,
            "characters": [],
            "events": [],
            "foreshadowing": {},
            "new_settings": [],
            "bridge": {"from_prev": "", "to_next": ""},
        }


def save_state_memory(project_dir: str, chapter_index: int, state_data: dict, project=None):
    """将单章蒸馏结果写入 state_memory 目录，并维护 _index.json。

    若提供 project 参数，使用 TransactionContext 保证章节 JSON 与 _index.json
    的原子写入；否则回退到传统的两次 open().write() 方式。

    Args:
        project_dir: 项目根目录路径
        chapter_index: 章节序号
        state_data: distill_single_chapter 返回的蒸馏数据
        project: 可选，NovelProject 实例，提供后启用事务原子写入
    """
    mem_dir = os.path.join(project_dir, "state_memory")
    os.makedirs(mem_dir, exist_ok=True)

    output = {
        "chapter_index": chapter_index,
        "distilled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "characters": state_data.get("characters", []),
        "events": state_data.get("events", []),
        "foreshadowing": state_data.get("foreshadowing", {}),
        "new_settings": state_data.get("new_settings", []),
        "bridge": state_data.get("bridge", {}),
    }

    chapter_file = os.path.join(mem_dir, f"{chapter_index:03d}.json")
    index_path = os.path.join(mem_dir, "_index.json")

    # 构建索引数据
    index_data = []
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        except Exception:
            index_data = []

    index_data = [e for e in index_data if e.get("chapter_index") != chapter_index]
    index_data.append({
        "chapter_index": chapter_index,
        "file": f"{chapter_index:03d}.json",
        "distilled_at": output["distilled_at"],
    })
    index_data.sort(key=lambda x: x["chapter_index"])

    if project is not None:
        # 使用 TransactionContext 原子写入两个文件
        from backend.storage_transaction import TransactionContext
        with TransactionContext(project) as tx:
            tx.register_file_write(chapter_file, json.dumps(output, ensure_ascii=False, indent=2))
            tx.register_file_write(index_path, json.dumps(index_data, ensure_ascii=False, indent=2))
    else:
        # 传统方式：先写章节 JSON 再写索引
        with open(chapter_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)

    # 失效记忆合成器缓存
    try:
        from backend.services.memory_synthesizer import _invalidate_cache
        _invalidate_cache(project_dir)
    except Exception as e:
        logger.warning("失效记忆合成器缓存失败: %s", e)


# ============================================================
# 蒸馏服务主类
# ============================================================

class DistillService:
    """小说蒸馏服务 - RIA-TV++ 流水线"""

    def __init__(self, novel_text: str, novel_name: str = "未命名小说",
                 decon_data: dict = None, source_type: str = "raw"):
        self.novel_text = novel_text
        self.novel_name = novel_name
        self.decon_data = decon_data  # 拆书五维分析结果（可选）
        self.source_type = source_type  # 蒸馏策略：raw(原始文本) | decon(基于拆书数据)
        self.chapters = []
        self.api_calls = 0

    def _ai_call(self, system_prompt: str, user_content: str, temperature: float = 0.7,
                 max_tokens: int = 4096) -> str:
        self.api_calls += 1
        return _ai_generate(system_prompt, user_content, temperature, max_tokens)

    # ----------------------------------------------------------------
    # 阶段0: 整书理解
    # ----------------------------------------------------------------
    def stage0_overview(self) -> dict:
        self.chapters = split_chapters(self.novel_text)
        total_chars = len(self.novel_text)

        system = "你是一位资深小说编辑和文学批评家。你的任务是阅读小说文本，生成一份整书理解文档。请用中文回答，输出 Markdown 格式。"

        # 策略分支：decon模式用拆书结构化数据为主，raw模式用原始文本
        use_decon = (self.source_type == "decon" and self.decon_data)

        if use_decon:
            # decon策略：拆书五维分析作为主要数据源，减少原文采样（省token）
            sampled = sample_text(self.novel_text, SAMPLE_CHARS // 2)
            decon_context = self._build_decon_context(primary=True)
            user = f"""请基于以下拆书五维分析结果和小说文本采样，生成整书理解文档。

## 小说文件名
{self.novel_name}

{decon_context}

## 小说文本（采样补充）
{sampled}

## 请输出以下内容（Markdown格式）:

### 基本信息
- 书名、作者（从文本推断）、类型/题材、总字数（约）、章节数、核心受众

### 核心冲突
- 外部冲突、内部冲突、主题冲突

### 主线结构
- 三幕式拆解（开端/发展/高潮结局，标注大致章节范围）
- 主要支线列表

### 人物关系图
- 主要角色表格（角色/身份/动机/与主角关系/弧线）
- 关系网络（文本描述）

### 世界观概要
- 世界类型、核心设定、世界规则

### 写作风格特征
- 叙事视角、文风特点、标志性技法、节奏数据

### 蒸馏建议
- 建议重点提取的技法方向（3-5条）

请基于拆书分析和原文内容进行综合判断，不要凭空编造。如果某些信息无法获取，标注"无法确定"。"""
        else:
            # raw策略：原始文本作为唯一数据源（原有行为，向后兼容）
            sampled = sample_text(self.novel_text, SAMPLE_CHARS)
            # 如果有拆书数据，作为补充上下文注入（兼容旧deep-analyze路径）
            decon_context = ""
            if self.decon_data:
                decon_context = self._build_decon_context(primary=False)

            user = f"""请阅读以下小说文本（可能为采样），生成整书理解分析。

## 小说文件名
{self.novel_name}

## 小说文本（采样）
{sampled}
{decon_context}
## 请输出以下内容（Markdown格式）:

### 基本信息
- 书名、作者（从文本推断）、类型/题材、总字数（约）、章节数、核心受众

### 核心冲突
- 外部冲突、内部冲突、主题冲突

### 主线结构
- 三幕式拆解（开端/发展/高潮结局，标注大致章节范围）
- 主要支线列表

### 人物关系图
- 主要角色表格（角色/身份/动机/与主角关系/弧线）
- 关系网络（文本描述）

### 世界观概要
- 世界类型、核心设定、世界规则

### 写作风格特征
- 叙事视角、文风特点、标志性技法、节奏数据

### 蒸馏建议
- 建议重点提取的技法方向（3-5条）

请基于原文内容进行分析，不要凭空编造。如果某些信息无法从文本中获取，标注"无法确定"。"""

        result = self._ai_call(system, user, temperature=0.3, max_tokens=4096)

        overview = {
            "novel_name": self.novel_name,
            "total_chars": total_chars,
            "chapter_count": len(self.chapters),
            "overview_md": result,
            "source_type": self.source_type,
            "created_at": datetime.now().isoformat(),
        }
        return overview

    def _build_decon_context(self, primary: bool = False) -> str:
        """构建拆书五维分析上下文文本。

        Args:
            primary: True=作为主要数据源（decon策略），False=作为补充参考（raw策略兼容）
        """
        if not self.decon_data:
            return ""

        label = "拆书五维分析（主要数据源）" if primary else "拆书五维分析（参考）"
        lines = [f"\n## {label}\n"]

        for dim, val in self.decon_data.items():
            if val is None:
                continue
            if isinstance(val, (str, int, float)):
                lines.append(f"- {dim}: {str(val)[:300]}\n")
            elif isinstance(val, dict):
                # 展开dict的key-value
                lines.append(f"- {dim}:\n")
                for k, v in val.items():
                    if v is not None:
                        lines.append(f"  - {k}: {str(v)[:200]}\n")
            elif isinstance(val, list):
                lines.append(f"- {dim}: {', '.join(str(v)[:100] for v in val[:8])}\n")

        return "".join(lines)

    # ----------------------------------------------------------------
    # 阶段1: 五路并行提取
    # ----------------------------------------------------------------
    def stage1_extract(self, overview: dict) -> dict:
        all_candidates = {}

        # 策略分支：decon模式减少原文采样（拆书数据已提供结构化线索），raw模式用全量采样
        use_decon = (self.source_type == "decon" and self.decon_data)
        if use_decon:
            # decon策略：采样量减半（拆书五维分析已提供提取方向）
            sampled = sample_text(self.novel_text, MAX_INPUT_CHARS // 2)
            decon_context = self._build_decon_context(primary=True)
        else:
            # raw策略：全量采样（原有行为，向后兼容）
            sampled = sample_text(self.novel_text, MAX_INPUT_CHARS)
            decon_context = ""
            # 如果有拆书数据但用的是raw策略，作为补充参考
            if self.decon_data:
                decon_context = self._build_decon_context(primary=False)

        overview_md = overview.get('overview_md', '')[:2000]

        for ext_name, ext_title in EXTRACTORS.items():
            prompt = EXTRACTOR_PROMPTS.get(ext_name, "")
            if not prompt:
                all_candidates[ext_name] = []
                continue

            system = prompt

            if use_decon:
                # decon策略：拆书数据作为提取方向引导，原文采样作为证据来源
                user = f"""## 小说名称
{self.novel_name}

{decon_context}

## 小说文本（采样，作为提取证据来源）
{sampled}

## 整书理解参考
{overview_md}

## 提取要求
请优先参考上方"拆书五维分析"中对应维度的分析结论，从小说文本中找到原文证据支撑，提取可迁移的写作方法论。

请按照你的提取规则，严格输出 YAML 格式。"""
            else:
                # raw策略：原文为唯一数据源（原有行为）
                user = f"""## 小说名称
{self.novel_name}

## 小说文本
{sampled}

## 整书理解参考
{overview_md}

请按照你的提取规则，从以上小说文本中提取候选条目，严格输出 YAML 格式。"""

            try:
                result = self._ai_call(system, user, temperature=0.4, max_tokens=4096)
                candidates = parse_yaml_candidates(result)
                all_candidates[ext_name] = candidates
            except Exception as e:
                logger.warning("提取器 %s 异常: %s", ext_name, e)
                all_candidates[ext_name] = []

        merged = []
        for ext_name, candidates in all_candidates.items():
            for c in candidates:
                c["extractor"] = ext_name
                merged.append(c)

        return {
            "candidates_by_extractor": all_candidates,
            "all_candidates": merged,
            "total": len(merged),
            "source_type": self.source_type,
        }

    # ----------------------------------------------------------------
    # 阶段1.5: 三重验证
    # ----------------------------------------------------------------
    def stage1_5_verify(self, candidates_data: dict) -> dict:
        all_candidates = candidates_data.get("all_candidates", [])
        if not all_candidates:
            return {"verified": [], "total": 0}

        system = """你是写作技法验证专家。你的任务是对提取的小说写作技法候选进行三重验证:

V1 跨章佐证: 该技法在书中至少2处独立使用（反面教材可放宽）
V2 预测力: 能用这个技法解释其他小说中的类似写法
V3 独特性: 不是"写好文章"之类的常识

对每条候选给出验证结果和理由。输出 JSON 数组格式。"""

        batch_size = 10
        verified_all = []

        for i in range(0, len(all_candidates), batch_size):
            batch = all_candidates[i:i + batch_size]

            batch_text = json.dumps(batch, ensure_ascii=False, indent=2)
            user = f"""请对以下候选技法逐条进行三重验证。

## 小说名称
{self.novel_name}

## 候选技法列表
{batch_text}

## 小说文本参考（采样）
{sample_text(self.novel_text, 20000)}

## 输出要求
对每条候选输出 JSON 对象，包含以下字段:
- id: 候选ID
- v1_passed: true/false
- v1_reason: 验证理由
- v2_passed: true/false
- v2_reason: 验证理由（如通过，列出可解释的其他小说）
- v3_passed: true/false
- v3_reason: 验证理由
- overall: "pass" / "downgrade" / "reject"
- suggestion: 如果降级或通过，给出建议

输出 JSON 数组，不要输出其他内容。"""

            try:
                result = self._ai_call(system, user, temperature=0.2, max_tokens=4096)
                json_match = re.search(r'```json\s*\n(.*?)```', result, re.DOTALL)
                if json_match:
                    result = json_match.group(1)
                bracket_match = re.search(r'\[.*\]', result, re.DOTALL)
                if bracket_match:
                    result = bracket_match.group(0)
                verification_results = json.loads(result)

                for v in verification_results:
                    cid = v.get("id", "")
                    for c in batch:
                        if c.get("id") == cid:
                            c["verification"] = v
                            if v.get("overall") in ("pass", "downgrade"):
                                verified_all.append(c)
                            break
            except Exception as e:
                logger.warning("验证流程异常，降级保留: %s", e)
                for c in batch:
                    c["verification"] = {"overall": "downgrade", "reason": "验证流程异常, 降级保留"}
                    verified_all.append(c)

        passed = sum(1 for c in verified_all if c.get("verification", {}).get("overall") == "pass")
        downgraded = sum(1 for c in verified_all if c.get("verification", {}).get("overall") == "downgrade")

        return {
            "verified": verified_all,
            "total": len(verified_all),
            "passed": passed,
            "downgraded": downgraded,
        }

    # ----------------------------------------------------------------
    # 阶段2: RIA++ 构造
    # ----------------------------------------------------------------
    def stage2_ria_construct(self, verified_data: dict) -> list:
        verified = verified_data.get("verified", [])
        if not verified:
            return []

        system = """你是写作技法蒸馏专家。你的任务是将通过验证的小说技法候选项，构造为完整的 RIA++ 技能卡片。

RIA++ 六要素:
- R (Reading): 原文引用 — 来自候选的 source_quote
- I (Interpretation): 方法论重写 — 将具体写法提炼为通用方法论
- A1 (Example): 书中案例 — 该技法在书中的具体使用效果分析
- A2 (Trigger): 触发场景 — 什么时候该用这个技法
- E (Execution): 可执行步骤 — 具体的操作步骤 (1. 2. 3.)
- B (Boundary): 边界与限制 — 什么时候不该用, 失败模式

输出 JSON 对象, 包含完整技能包字段。"""

        skills_all = []

        for i, candidate in enumerate(verified):
            user = f"""请将以下技法候选构造为完整的 RIA++ 技能卡片。

## 候选信息
{json.dumps(candidate, ensure_ascii=False, indent=2)}

## 小说名称
{self.novel_name}

## 输出要求
输出一个 JSON 对象, 包含以下字段:
{{
  "id": "技能ID (用候选的id, 加上小说名slug前缀)",
  "name": "技能标题 (简洁有力)",
  "type": "skill",
  "category": "writing-technique",
  "description": "触发条件+使用场景, 1-2句话",
  "source": "{self.novel_name}",
  "tags": ["标签1", "标签2", ...],
  "content": {{
    "reading": "原文引用 (来自候选的source_quote)",
    "interpretation": "方法论重写 (将具体写法提炼为通用方法论, 3-5句话)",
    "example": "书中案例分析 (该技法在书中的效果, 2-3句话)",
    "trigger": "触发场景 (什么时候该用, 1-2句话)",
    "execution": "可执行步骤 (1. xxx 2. xxx 3. xxx, 具体可操作)",
    "boundary": "边界与限制 (什么时候不该用, 失败模式, 2-3句话)"
  }},
  "related_skills": [],
  "verification": 候选的验证信息
}}

只输出 JSON, 不要输出其他内容。"""

            try:
                result = self._ai_call(system, user, temperature=0.5, max_tokens=2048)
                json_match = re.search(r'```json\s*\n(.*?)```', result, re.DOTALL)
                if json_match:
                    result = json_match.group(1)
                brace_match = re.search(r'\{.*\}', result, re.DOTALL)
                if brace_match:
                    result = brace_match.group(0)
                skill = json.loads(result)

                skill.setdefault("id", f"{slugify(self.novel_name)}-{candidate.get('id', i)}")
                skill.setdefault("name", candidate.get("title", "未命名技能"))
                skill.setdefault("type", "skill")
                skill.setdefault("category", "writing-technique")
                skill.setdefault("source", self.novel_name)
                skill.setdefault("tags", candidate.get("tags", []))
                skill.setdefault("content", {})
                skill.setdefault("related_skills", [])
                skill["_extractor"] = candidate.get("extractor", "")
                skill["_candidate_type"] = candidate.get("type", "")

                skills_all.append(skill)
            except Exception as e:
                logger.warning("构造技能卡片失败: %s", e)

        return skills_all

    # ----------------------------------------------------------------
    # 运行完整流水线
    # ----------------------------------------------------------------
    def run(self, start_stage: int = 0, end_stage: int = 2) -> dict:
        """
        运行蒸馏流水线。

        Args:
            start_stage: 起始阶段 (0/1/1.5/2)
            end_stage: 结束阶段 (0/1/1.5/2)

        Returns:
            dict: 包含 overview / candidates / verified / skills / api_calls
        """
        result = {}

        overview = self.stage0_overview()
        result["overview"] = overview

        if end_stage >= 1:
            candidates = self.stage1_extract(overview)
            result["candidates"] = candidates

            if end_stage >= 1.5:
                verified = self.stage1_5_verify(candidates)
                result["verified"] = verified

                if end_stage >= 2:
                    skills = self.stage2_ria_construct(verified)
                    result["skills"] = skills

        result["api_calls"] = self.api_calls
        result["novel_name"] = self.novel_name
        result["novel_chars"] = len(self.novel_text)
        result["chapter_count"] = len(self.chapters)
        result["skill_count"] = len(result.get("skills", []))

        return result


