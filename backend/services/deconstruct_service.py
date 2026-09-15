# -*- coding: utf-8 -*-
"""
书斋 V64 - 拆书分析服务
对源作品进行多维深度拆解，并转化为用户自己的世界观、角色和大纲。
"""
import json
import re
import logging
from typing import Optional, List

from backend.ai_client import AIClient

logger = logging.getLogger(__name__)


class DeconstructService:
    """拆书分析核心服务"""

    # 默认分析维度
    DEFAULT_DIMENSIONS = [
        "structure",
        "characters",
        "worldbuilding",
        "theme",
        "plot_mechanics",
    ]

    # 维度中文名映射
    DIMENSION_LABELS = {
        "structure": "叙事结构",
        "characters": "人物体系",
        "worldbuilding": "世界观设定",
        "theme": "主题思想",
        "plot_mechanics": "情节技法",
    }

    def __init__(self, project_dir: str):
        """
        初始化拆书服务
        :param project_dir: 项目目录路径
        """
        self.project_dir = project_dir
        self.ai = AIClient()
        logger.info(f"DeconstructService 初始化完成, 项目目录: {project_dir}")

    # ============================================================
    # 文本预处理
    # ============================================================

    def _chunk_text(self, content: str, max_chars: int = 8000) -> List[str]:
        """
        将长文本分块，尽量在段落边界处断开
        :param content: 原始文本
        :param max_chars: 每块最大字符数
        :return: 文本块列表
        """
        if len(content) <= max_chars:
            return [content]

        chunks = []
        paragraphs = content.split("\n")
        current_chunk = ""

        for para in paragraphs:
            # 如果当前段加上新段落不超限，则合并
            if len(current_chunk) + len(para) + 1 <= max_chars:
                if current_chunk:
                    current_chunk += "\n" + para
                else:
                    current_chunk = para
            else:
                # 当前块已满，保存
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                # 新段落本身如果超长，硬截断
                if len(para) > max_chars:
                    # 在 max_chars 附近找最近的句号/感叹号/问号
                    for i in range(max_chars - 1, max(0, max_chars - 500), -1):
                        if para[i] in "。！？.!?\n":
                            chunks.append(para[: i + 1])
                            current_chunk = para[i + 1 :]
                            break
                    else:
                        chunks.append(para[:max_chars])
                        current_chunk = para[max_chars:]
                else:
                    current_chunk = para

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        logger.info(f"文本分块完成: {len(content)}字 → {len(chunks)}个块")
        return chunks

    # ============================================================
    # AI 摘要
    # ============================================================

    def _summarize_chunk(self, chunk: str) -> str:
        """
        对单个文本块进行 AI 摘要
        :param chunk: 文本块
        :return: 摘要文本
        """
        prompt = f"""你是一位专业的小说编辑。请对以下小说片段进行摘要，提取关键情节和设定信息。

要求：
1. 保留所有重要人物及其行为
2. 保留关键情节转折
3. 保留独特的设定信息（世界观、力量体系等）
4. 摘要控制在500字以内
5. 不要添加任何评价或分析

小说片段：
{chunk}

请直接输出摘要，不要加任何前缀说明。"""

        try:
            result = self.ai.generate(prompt)
            # 清理可能的思考标签
            result = re.sub(r"<think\b.*?</think\b\s*>", "", result, flags=re.DOTALL)
            return result.strip()
        except Exception as e:
            logger.error(f"摘要文本块失败: {e}")
            return chunk[:500]  # fallback: 截取前500字

    def _summarize_full_book(self, content: str) -> str:
        """
        全文分层摘要：长文本 → N个chunk摘要 → 合并 → 最终摘要 → 压缩版全书梗概
        :param content: 全文内容
        :return: 全书梗概（2000-3000字）
        """
        word_count = len(content)
        if word_count <= 20000:
            # 短文本直接摘要
            return self._summarize_chunk(content)

        # 长文本：分层摘要
        logger.info(f"开始分层摘要: {word_count}字")

        # 第一层：分块摘要
        chunks = self._chunk_text(content, max_chars=8000)
        chunk_summaries = []
        for i, chunk in enumerate(chunks):
            logger.info(f"摘要第 {i+1}/{len(chunks)} 块...")
            summary = self._summarize_chunk(chunk)
            chunk_summaries.append(summary)

        # 第二层：合并摘要
        merged = "\n\n---\n\n".join(chunk_summaries)

        # 如果合并后仍超过8000字，递归摘要
        if len(merged) > 12000:
            logger.info(f"合并摘要仍过长({len(merged)}字)，递归摘要...")
            # 分两批合并
            mid = len(chunk_summaries) // 2
            part1 = self._summarize_chunk("\n\n".join(chunk_summaries[:mid]))
            part2 = self._summarize_chunk("\n\n".join(chunk_summaries[mid:]))
            merged = part1 + "\n\n" + part2

        # 最终摘要：生成压缩版全书梗概
        final_prompt = f"""你是一位资深小说编辑。请根据以下小说各部分摘要，撰写一份完整的全书梗概。

要求：
1. 按时间顺序梳理主线情节
2. 明确主要人物的成长弧线
3. 概括核心世界观设定
4. 点明主题思想
5. 控制在2000-3000字
6. 这是分析性梗概，不是续写

各部分摘要：
{merged[:10000]}

请输出完整的全书梗概。"""

        try:
            result = self.ai.generate(final_prompt)
            result = re.sub(r"<think\b.*?</think\b\s*>", "", result, flags=re.DOTALL)
            logger.info(f"全书梗概生成完成: {len(result)}字")
            return result.strip()
        except Exception as e:
            logger.error(f"生成全书梗概失败: {e}")
            return merged[:3000]  # fallback

    # ============================================================
    # 维度分析
    # ============================================================

    def analyze_dimension(
        self, summary: str, dimension: str, content_sample: str = ""
    ) -> dict:
        """
        分析单个维度
        :param summary: 全书摘要/梗概
        :param dimension: 维度名 (structure/characters/worldbuilding/theme/plot_mechanics)
        :param content_sample: 原文采样（用于细节分析）
        :return: 分析结果 dict
        """
        label = self.DIMENSION_LABELS.get(dimension, dimension)

        # 构建上下文
        context = summary
        if content_sample:
            context = summary + "\n\n【原文片段参考】\n" + content_sample[:2000]

        # 根据维度选择 prompt
        prompts = {
            "structure": self._prompt_structure(context),
            "characters": self._prompt_characters(context),
            "worldbuilding": self._prompt_worldbuilding(context),
            "theme": self._prompt_theme(context),
            "plot_mechanics": self._prompt_plot_mechanics(context),
        }

        prompt = prompts.get(dimension)
        if not prompt:
            logger.warning(f"未知维度: {dimension}")
            return {}

        logger.info(f"开始分析维度: {label}")
        try:
            result = self.ai.generate(prompt)
            result = re.sub(r"<think\b.*?</think\b\s*>", "", result, flags=re.DOTALL)
            parsed = self._parse_json(result)
            if not parsed and result.strip():
                # JSON解析失败，尝试用AI重新提取JSON
                logger.info(f"维度 [{label}] 首次解析失败，尝试AI重新提取JSON...")
                retry_prompt = f"""从以下文本中提取JSON对象，只输出JSON，不要输出任何其他文字：

{result[:3000]}"""
                retry_result = self.ai.generate(retry_prompt)
                retry_result = re.sub(r"<think\b.*?</think\b\s*>", "", retry_result, flags=re.DOTALL)
                parsed = self._parse_json(retry_result)
            if parsed:
                logger.info(f"维度 [{label}] 分析完成")
                return parsed
            else:
                logger.warning(f"维度 [{label}] JSON解析失败，原始返回: {result[:200]}...")
                return {}
        except Exception as e:
            logger.error(f"维度 [{label}] 分析异常: {e}")
            return {}

    # ============================================================
    # 各维度 Prompt
    # ============================================================

    def _prompt_structure(self, context: str) -> str:
        return f"""你是一位小说结构分析师。请分析以下小说的叙事结构，输出严格JSON。

小说梗概：
{context}

请分析并输出以下JSON格式（不要加任何其他文字）：

{{
  "act_structure": "几幕结构（如：三幕剧/四幕剧/五幕剧/英雄之旅），一句话概括",
  "acts": [
    {{
      "name": "幕名/阶段名",
      "range": "涵盖范围简述",
      "key_events": ["关键事件1", "关键事件2"],
      "turning_point": "该幕的情感转折点或情节转折",
      "function": "该幕在整体结构中的功能"
    }}
  ],
  "tension_curve": [
    {{"position": "开头/前1/3/中点/后1/3/结尾", "level": "低/中/高/极高", "event": "对应事件"}}
  ],
  "pacing_analysis": "节奏分析：哪些部分快节奏、哪些慢节奏，节奏变化的技巧"
}}

请确保JSON格式完整正确，每个字段都必须填写。"""

    def _prompt_characters(self, context: str) -> str:
        return f"""你是一位小说人物分析师。请分析以下小说的人物体系，输出严格JSON。

小说梗概：
{context}

请分析并输出以下JSON格式（不要加任何其他文字）：

{{
  "protagonist": {{
    "name": "主角姓名",
    "role": "在故事中的角色定位",
    "goals": ["目标1", "目标2"],
    "flaws": ["缺陷1", "缺陷2"],
    "arc": "完整的人物弧线描述",
    "key_relationships": ["与谁的关键关系"]
  }},
  "antagonist": {{
    "name": "反派姓名",
    "type": "反派类型（对抗型/竞争型/环境型/内在型）",
    "motivation": "动机",
    "methods": ["手段1", "手段2"],
    "complexity": "复杂度：扁平/立体/灰色"
  }},
  "supporting": [
    {{
      "name": "配角姓名",
      "role": "角色功能（导师/盟友/爱侣/丑角/门槛守卫等）",
      "function": "在故事中的作用",
      "arc": "角色发展弧线"
    }}
  ],
  "relationship_graph": [
    {{
      "from": "角色A",
      "to": "角色B",
      "type": "关系类型（同盟/敌对/爱慕/师徒/竞争/家人）",
      "dynamics": "关系动态变化描述"
    }}
  ]
}}

请确保JSON格式完整正确，每个字段都必须填写。如果没有明确信息，请根据文本合理推断并标注"(推断)"。"""

    def _prompt_worldbuilding(self, context: str) -> str:
        return f"""你是一位世界观分析师。请分析以下小说的世界观设定，输出严格JSON。

小说梗概：
{context}

请分析并输出以下JSON格式（不要加任何其他文字）：

{{
  "magic_system": {{
    "name": "力量/魔法体系名称",
    "type": "类型（硬魔法/软魔法/科技/灵气/武侠/其他）",
    "rules": ["规则1", "规则2", "规则3"],
    "cost": "使用力量的代价",
    "hierarchy": "力量等级体系"
  }},
  "technology_level": "科技水平描述",
  "geography": [
    {{
      "name": "地名/区域名",
      "type": "区域类型（王国/城市/秘境/战场等）",
      "features": "特征描述",
      "significance": "在故事中的意义"
    }}
  ],
  "social_structure": {{
    "political": "政治体制",
    "economy": "经济体系",
    "classes": ["阶层1", "阶层2"],
    "conflicts": "社会矛盾"
  }},
  "unique_rules": [
    "这个世界独有的规则或设定亮点"
  ]
}}

请确保JSON格式完整正确，每个字段都必须填写。没有明确信息的项目请标注"(原文未详述，推断)"。"""

    def _prompt_theme(self, context: str) -> str:
        return f"""你是一位文学主题分析师。请分析以下小说的主题思想，输出严格JSON。

小说梗概：
{context}

请分析并输出以下JSON格式（不要加任何其他文字）：

{{
  "core_themes": [
    {{
      "theme": "主题名称",
      "expression": "主题如何在故事中体现",
      "key_scenes": ["体现该主题的关键场景"]
    }}
  ],
  "recurring_motifs": [
    {{
      "motif": "母题/意象",
      "occurrences": "出现方式和频率",
      "meaning": "象征意义"
    }}
  ],
  "value_conflicts": [
    {{
      "values": ["价值A", "价值B"],
      "manifestation": "冲突如何在情节中体现",
      "resolution": "冲突的解决方式（或未解决）"
    }}
  ],
  "moral_questions": [
    "小说提出的道德/哲学问题"
  ]
}}

请确保JSON格式完整正确，每个字段都必须填写。"""

    def _prompt_plot_mechanics(self, context: str) -> str:
        return f"""你是一位小说情节技法分析师。请分析以下小说的情节设计技巧，输出严格JSON。

小说梗概：
{context}

请分析并输出以下JSON格式（不要加任何其他文字）：

{{
  "hooks": [
    {{
      "hook": "钩子描述",
      "type": "类型（悬念/疑问/承诺/情感/反转预告）",
      "placement": "安放位置",
      "effectiveness": "效果评估"
    }}
  ],
  "suspense_techniques": [
    {{
      "technique": "技法名称",
      "description": "具体应用方式",
      "example": "书中案例简述"
    }}
  ],
  "revelation_patterns": [
    {{
      "what": "揭示的内容",
      "when": "揭示时机",
      "method": "揭示方式（对话/闪回/发现/证词等）",
      "impact": "对读者的影响"
    }}
  ],
  "twists": [
    {{
      "twist": "反转内容",
      "type": "反转类型（身份/真相/动机/结局）",
      "setup": "铺垫方式",
      "surprise_level": "意外程度：高/中/低"
    }}
  ]
}}

请确保JSON格式完整正确，每个字段都必须填写。"""

    # ============================================================
    # 主入口：拆书分析
    # ============================================================

    def deconstruct(
        self,
        content: str,
        dimensions: list = None,
        on_progress: callable = None,
    ) -> dict:
        """
        主入口：对文本进行完整拆书分析
        :param content: 待分析文本
        :param dimensions: 要分析的维度列表，默认全部
        :param on_progress: 进度回调 (stage, current, total)
        :return: 拆书结果 dict
        """
        if dimensions is None:
            dimensions = self.DEFAULT_DIMENSIONS

        word_count = len(content)
        logger.info(f"开始拆书分析: {word_count}字, 维度: {dimensions}")

        # 阶段0：预处理
        if on_progress:
            on_progress("预处理", 0, len(dimensions) + 1)

        # 构建 source_meta（从内容尝试提取）
        source_meta = self._extract_source_meta(content, word_count)

        # 阶段1：生成全书梗概（长文本走分层摘要）
        if on_progress:
            on_progress("生成梗概", 0, len(dimensions) + 1)
        summary = self._summarize_full_book(content)

        # 阶段2：逐维度分析（串行，因为AI可能有限流）
        result = {
            "source_meta": source_meta,
            "structure": {},
            "characters": {},
            "worldbuilding": {},
            "theme": {},
            "plot_mechanics": {},
        }

        for i, dim in enumerate(dimensions):
            if on_progress:
                on_progress(f"分析{self.DIMENSION_LABELS.get(dim, dim)}", i + 1, len(dimensions) + 1)

            # 对人物和世界观维度，提供原文采样以获取更详细信息
            content_sample = ""
            if dim in ("characters", "worldbuilding"):
                content_sample = content[:5000]  # 前5000字通常包含大量设定信息

            dim_result = self.analyze_dimension(summary, dim, content_sample)
            result[dim] = dim_result

        if on_progress:
            on_progress("完成", len(dimensions) + 1, len(dimensions) + 1)

        logger.info(f"拆书分析完成: {len(content)}字")
        return result

    def _extract_source_meta(self, content: str, word_count: int) -> dict:
        """
        尝试从内容中提取源作品元信息
        """
        # 取前2000字让AI提取
        sample = content[:2000]
        prompt = f"""请从以下小说开头片段中提取基本信息，输出严格JSON：

片段：
{sample}

输出格式：
{{
  "title": "书名（如能推断）",
  "author": "作者（如能推断）",
  "genre": "小说类型（玄幻/科幻/都市/历史/悬疑/言情/武侠/游戏/轻小说/其他）",
  "word_count": {word_count},
  "style_notes": "文风特点简要描述"
}}

如果无法推断某项，填"未知"。只输出JSON，不要其他文字。"""

        try:
            result = self.ai.generate(prompt)
            result = re.sub(r"<think\b.*?</think\b\s*>", "", result, flags=re.DOTALL)
            meta = self._parse_json(result)
            if not meta and result.strip():
                # 重试：让AI重新提取JSON
                retry = self.ai.generate(f"从以下文本中提取JSON对象，只输出JSON：\n{result[:2000]}")
                retry = re.sub(r"<think\b.*?</think\b\s*>", "", retry, flags=re.DOTALL)
                meta = self._parse_json(retry)
            if meta:
                meta["word_count"] = word_count  # 确保字数准确
                return meta
        except Exception as e:
            logger.warning(f"提取源作品元信息失败: {e}")

        return {
            "title": "未知",
            "author": "未知",
            "genre": "未知",
            "word_count": word_count,
            "style_notes": "",
        }

    # ============================================================
    # 转化：拆书结果 → 用户自己的创作蓝图
    # ============================================================

    def transform(self, deconstruction: dict, user_vision: dict) -> dict:
        """
        将拆书结果转化为用户自己的世界观+角色+大纲
        :param deconstruction: 拆书结果 dict
        :param user_vision: 用户构想 dict
            {genre, tone, core_idea, constraints, ...}
        :return: 转化结果 dict (与现有blueprint兼容)
        """
        logger.info("开始转化拆书结果...")

        # 序列化拆书结果为文本供AI参考
        decon_text = json.dumps(deconstruction, ensure_ascii=False, indent=2)
        vision_text = json.dumps(user_vision, ensure_ascii=False, indent=2)

        # ---- 第一部分：世界观卡片 ----
        worldview = self._transform_worldview(decon_text, vision_text)

        # ---- 第二部分：角色卡片 ----
        characters = self._transform_characters(decon_text, vision_text)

        # ---- 第三部分：大纲蓝图 ----
        outline = self._transform_outline(decon_text, vision_text)

        result = {
            "worldview_cards": worldview,
            "character_cards": characters,
            "outline_blueprint": outline,
        }

        logger.info("转化完成")
        return result

    def _transform_worldview(self, decon_text: str, vision_text: str) -> list:
        prompt = f"""你是创意写作导师。请根据以下【拆书分析报告】和【用户构想】，帮助用户创作一个全新的世界观。

【拆书分析报告】（仅供学习参考）
{decon_text[:4000]}

【用户构想】
{vision_text}

【严禁抄袭规则】
1. 绝对禁止搬运源作品的具体设定、名字、地名、力量体系名称
2. 禁止直接使用源作品的角色名、组织名、专有名词
3. 只借鉴叙事结构和设计思路，所有具体内容必须原创
4. 如果某个设定与源作品相似度过高（>60%），标注为"需修改"

请输出严格JSON格式（不要加其他文字）：

[
  {{
    "world_name": "世界名称（原创）",
    "core_rules": ["世界核心规则1", "世界核心规则2"],
    "power_system": {{
      "name": "力量体系名称",
      "type": "类型",
      "rules": ["规则1", "规则2"],
      "hierarchy": "等级体系"
    }},
    "geography": [
      {{"name": "区域名", "type": "类型", "features": "特征"}}
    ],
    "factions": [
      {{"name": "势力名", "type": "类型", "goal": "目标", "features": "特征"}}
    ],
    "unique_appeal": "这个世界最独特的卖点/吸引力"
  }}
]

请确保所有内容都是原创的，与源作品有明显差异。"""

        return self._call_and_parse_list(prompt, "世界观卡片")

    def _transform_characters(self, decon_text: str, vision_text: str) -> list:
        prompt = f"""你是创意写作导师。请根据以下【拆书分析报告】和【用户构想】，帮助用户设计全新的角色阵容。

【拆书分析报告】（仅供学习参考）
{decon_text[:4000]}

【用户构想】
{vision_text}

【严禁抄袭规则】
1. 绝对禁止搬运源作品角色的名字、外貌、性格组合、能力设定
2. 禁止使用相同的角色关系和命运轨迹
3. 只借鉴角色功能和叙事作用的设计思路
4. 每个角色必须有与源作品明显不同的独特特征

请输出严格JSON格式（不要加其他文字）：

[
  {{
    "name": "角色姓名（原创）",
    "archetype": "原型（英雄/导师/门槛守卫/信使/变形者/阴影/盟友/骗徒）",
    "role": "在故事中的功能",
    "goals": ["目标1", "目标2"],
    "flaws": ["缺陷1", "缺陷2"],
    "arc_description": "角色弧线描述",
    "relationships": [
      {{"with": "关联角色名", "type": "关系类型", "dynamics": "关系动态"}}
    ]
  }}
]

至少设计4-6个角色，包含主角、反派和关键配角。请确保所有内容原创。"""

        return self._call_and_parse_list(prompt, "角色卡片")

    def _transform_outline(self, decon_text: str, vision_text: str) -> dict:
        prompt = f"""你是创意写作导师。请根据以下【拆书分析报告】和【用户构想】，为用户设计一个原创小说大纲。

【拆书分析报告】（仅供学习参考）
{decon_text[:4000]}

【用户构想】
{vision_text}

【严禁抄袭规则】
1. 绝对禁止使用源作品的情节线、桥段组合、具体事件设计
2. 禁止复制源作品的结构模板直接填入新内容
3. 只借鉴叙事节奏和结构原理
4. 大纲中的每个情节点都应该是原创构思

请输出严格JSON格式（不要加其他文字）：

{{
  "title": "小说标题（原创，可根据用户构想调整）",
  "acts": [
    {{
      "name": "第X幕名称",
      "summary": "该幕概要（100-200字）",
      "key_beats": ["关键节点1", "关键节点2", "关键节点3"]
    }}
  ],
  "chapters": [
    {{
      "number": 1,
      "title": "章节标题",
      "belongs_to_act": 1,
      "summary": "该章概要（50-150字）",
      "pov": "视角角色",
      "key_scenes": ["场景1", "场景2"]
    }}
  ]
}}

请设计3-4幕，每幕3-5章，总共至少12章。确保大纲整体有清晰的起承转合。"""

        result = self._call_and_parse_dict(prompt, "大纲蓝图")
        if not result:
            return {"title": "", "acts": [], "chapters": []}
        return result

    # ============================================================
    # 工具方法
    # ============================================================

    def _parse_json(self, text: str) -> Optional[dict]:
        """
        解析AI返回的JSON，处理思考过程、markdown代码块等情况
        """
        if not text:
            return None

        # 清理 <think>...</think> 标签
        clean = re.sub(r"<think\b.*?</think\b\s*>", "", text, flags=re.DOTALL)
        # 清理未闭合的 <think> 标签（只有开头没有结尾）
        clean = re.sub(r"<think\b[^>]*>", "", clean)

        clean = clean.strip()

        # 去掉 markdown 代码块标记
        clean = re.sub(r"```(?:json)?\s*", "", clean)
        clean = re.sub(r"```\s*", "", clean)

        # 尝试直接解析
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            pass

        # 尝试提取第一个 { 到最后一个 } 之间的内容（跳过思考过程）
        match = re.search(r"\{[\s\S]*\}", clean)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                # 尝试修复尾随逗号后解析
                try:
                    fixed = re.sub(r",\s*([}\]])", r"\1", match.group())
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass

        # 尝试提取 JSON 数组
        match = re.search(r"\[[\s\S]*\]", clean)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, list):
                    return result[0] if result else None
            except json.JSONDecodeError:
                pass

        # 尝试修复常见问题：尾随逗号
        try:
            fixed = re.sub(r",\s*([}\]])", r"\1", clean)
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        logger.warning(f"JSON解析失败，尝试暴力提取。原始文本前200字: {text[:200]}")

        # 暴力提取：找到第一个 { ，用括号匹配找到对应的 }
        first_brace = clean.find("{")
        if first_brace >= 0:
            depth = 0
            in_string = False
            escape = False
            for i in range(first_brace, len(clean)):
                ch = clean[i]
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"' and not escape:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = clean[first_brace:i+1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            # 尝试修复尾随逗号
                            try:
                                fixed = re.sub(r",\s*([}\]])", r"\1", candidate)
                                return json.loads(fixed)
                            except json.JSONDecodeError:
                                pass
                        break

        return None

    def _call_and_parse_dict(self, prompt: str, label: str) -> Optional[dict]:
        """调用AI并解析为dict"""
        try:
            result = self.ai.generate(prompt)
            result = re.sub(r"<think\b.*?</think\b\s*>", "", result, flags=re.DOTALL)
            parsed = self._parse_json(result)
            if parsed and isinstance(parsed, dict):
                logger.info(f"[{label}] 生成完成")
                return parsed
            logger.warning(f"[{label}] 返回不是dict: {type(parsed)}")
            return None
        except Exception as e:
            logger.error(f"[{label}] 调用失败: {e}")
            return None

    def _call_and_parse_list(self, prompt: str, label: str) -> list:
        """调用AI并解析为list"""
        try:
            result = self.ai.generate(prompt)
            result = re.sub(r"<think\b.*?</think\b\s*>", "", result, flags=re.DOTALL)
            parsed = self._parse_json(result)
            if parsed and isinstance(parsed, list):
                logger.info(f"[{label}] 生成完成: {len(parsed)}项")
                return parsed
            # 如果返回的是dict但包含列表字段，尝试提取
            if parsed and isinstance(parsed, dict):
                for val in parsed.values():
                    if isinstance(val, list):
                        return val
                return [parsed]  # 把整个dict当作一项
            logger.warning(f"[{label}] 返回不是list: {type(parsed)}")
            return []
        except Exception as e:
            logger.error(f"[{label}] 调用失败: {e}")
            return []

    def _safe_parse_json_list(self, text: str) -> list:
        """安全解析JSON数组，返回list"""
        # 清理 <think> 标签
        clean = re.sub(r"<think\b.*?</think\b\s*>", "", text, flags=re.DOTALL)
        clean = re.sub(r"<think\b[^>]*>", "", clean)
        clean = clean.strip()
        clean = re.sub(r"```(?:json)?\s*", "", clean)
        clean = re.sub(r"```\s*", "", clean)

        try:
            result = json.loads(clean)
            if isinstance(result, list):
                return result
            if isinstance(result, dict):
                # 如果返回dict但需要list，检查是否有list字段
                for val in result.values():
                    if isinstance(val, list):
                        return val
                return [result]
        except json.JSONDecodeError:
            pass

        # 暴力提取：找到第一个 [ ，用括号匹配找到对应的 ]
        first_bracket = clean.find("[")
        if first_bracket >= 0:
            depth = 0
            in_string = False
            escape = False
            for i in range(first_bracket, len(clean)):
                ch = clean[i]
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"' and not escape:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        candidate = clean[first_bracket:i+1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            try:
                                fixed = re.sub(r",\s*([}\]])", r"\1", candidate)
                                return json.loads(fixed)
                            except json.JSONDecodeError:
                                pass
                        break

        # fallback: 正则
        match = re.search(r"\[[\s\S]*\]", clean)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return []
