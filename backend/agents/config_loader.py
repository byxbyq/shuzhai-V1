# -*- coding: utf-8 -*-
"""
书斋 V66 - Agent 配置加载器

从 agent_config.json 读取 Agent 配置，提供动态拼装 INTENT_PROMPT、
Agent 注册信息获取、共享常量查询等功能。

单例模式，首次访问时加载并缓存。
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class AgentConfig:
    """Agent 配置加载器（单例）。

    使用方式::

        cfg = AgentConfig()
        agents = cfg.get_agents()
        prompt = cfg.build_intent_prompt()
        genres = cfg.get_constants()["genre_list"]
    """

    _instance: Optional["AgentConfig"] = None

    def __new__(cls) -> "AgentConfig":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
            cls._instance._data = None
        return cls._instance

    def _ensure_loaded(self) -> None:
        """确保配置已加载（幂等）"""
        if self._loaded:
            return
        config_path = os.path.join(os.path.dirname(__file__), "agent_config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            self._loaded = True
            agent_count = len(self._data.get("agents", []))
            intent_count = sum(len(a.get("intents", [])) for a in self._data.get("agents", []))
            logger.info(
                "[config_loader] 配置加载完成: %d 个Agent, %d 个意图",
                agent_count, intent_count,
            )
        except Exception as e:
            logger.error("[config_loader] 配置文件加载失败: %s", e)
            self._data = {"agents": [], "constants": {}, "standalone_intents": {}, "_meta": {}}
            self._loaded = True

    # ── 查询接口 ──

    def get_agents(self) -> list:
        """返回全部 Agent 配置条目（list of dict）"""
        self._ensure_loaded()
        return self._data.get("agents", [])

    def get_agent_by_id(self, agent_id: str) -> Optional[dict]:
        """按 agent_id 查找配置条目"""
        self._ensure_loaded()
        for agent in self._data.get("agents", []):
            if agent.get("id") == agent_id:
                return agent
        return None

    def get_agent_by_intent(self, intent: str) -> Optional[dict]:
        """按意图名称反向查找所属 Agent 配置条目"""
        self._ensure_loaded()
        for agent in self._data.get("agents", []):
            for item in agent.get("intents", []):
                if item.get("intent") == intent:
                    return agent
        return None

    def get_all_intents(self) -> list:
        """返回全部意图列表（拍平 agents[].intents[]），每项含 intent/description/examples/params + 所属 agent_id"""
        self._ensure_loaded()
        result = []
        for agent in self._data.get("agents", []):
            for item in agent.get("intents", []):
                entry = dict(item)
                entry["agent_id"] = agent.get("id")
                result.append(entry)
        return result

    def get_standalone_intents(self) -> dict:
        """返回独立意图（如 edit_selection）"""
        self._ensure_loaded()
        return self._data.get("standalone_intents", {})

    def get_constants(self) -> dict:
        """返回共享常量字典"""
        self._ensure_loaded()
        return self._data.get("constants", {})

    # ── Prompt 动态生成 ──

    def build_intent_prompt(self) -> str:
        """从配置动态生成 INTENT_PROMPT 文本。

        等价于旧的 prompts.INTENT_PROMPT，但内容由 agent_config.json 驱动。
        """
        self._ensure_loaded()
        agents = self._data.get("agents", [])
        standalone = self._data.get("standalone_intents", {})

        lines = []
        lines.append("你是一个意图识别引擎。用户会用自然语言下达指令，你需要识别意图并返回JSON。")
        lines.append("")
        lines.append("可选意图列表（intent字段）：")
        lines.append("")

        # ── Agent 意图编号 ──
        idx = 1
        for agent in agents:
            for item in agent.get("intents", []):
                intent = item["intent"]
                desc = item.get("description", "")
                lines.append(f'{idx}. "{intent}" - {desc}')
                idx += 1

        # ── 独立意图 ──
        standalone_idx_start = idx
        for si_name, si_info in standalone.items():
            lines.append(f'{idx}. "{si_name}" - {si_info.get("description", "")}')
            idx += 1
        standalone_idx_end = idx

        lines.append("")
        lines.append("返回格式（严格JSON，不要解释）：")
        lines.append("{")
        lines.append('  "intent": "意图名称",')
        lines.append('  "params": {')
        lines.append('    "chapter_index": 数字或null,')

        # 合并所有独特参数
        all_params = self._collect_unique_params(agents)
        for i, (key, desc) in enumerate(all_params):
            comma = "," if i < len(all_params) - 1 else ""
            lines.append(f'    "{key}": "{desc}" 或 null{comma}')

        lines.append("  },")
        lines.append('  "reply": "一句话回复用户，说明你将要做什么"')
        lines.append("}")

        lines.append("")
        lines.append("示例：")

        # 从配置生成示例
        examples = self._collect_examples(agents)
        for ex in examples[:25]:  # 限制示例数量
            lines.append(ex)

        lines.append("")
        lines.append("注意：")
        lines.append("- chapter_index 从0开始（第1章=0）")
        lines.append("- 如果用户说\"当前章\"或\"这章\"，chapter_index 设为 -1（表示用当前章节）")
        lines.append("- 如果用户没指定章节但需要章节参数，chapter_index 设为 null（表示用当前章节）")
        lines.append("- 【重要】不要编造功能！如果你不能实际执行某个操作（如删除章节、调整顺序、改电影剧本），必须选general_chat并诚实告诉用户该功能暂未实现，不要说\"好的我来帮你\"然后实际做不到")
        lines.append("- general_chat的reply必须包含\"该功能暂未实现\"或\"我暂时无法\"等诚实表述，不能假装能做")
        lines.append("- 全文查找替换必须选find_replace，不要选optimize_text")
        lines.append("- 分析章节内容（节奏、人物弧光、逻辑、质量）选analyze_chapter，不要选check_xxx（检查规则）或optimize_text")

        return "\n".join(lines)

    # ── 内部辅助 ──

    def _collect_unique_params(self, agents: list) -> list:
        """收集所有意图的参数名和描述（去重）"""
        seen = set()
        result = []
        # 先把核心参数放前面
        core_params = [
            ("chapter_index", "数字或null"),
            ("format", "txt/epub/pdf 或 null"),
            ("check_type", "drift/style/continuity/completeness/all 或 null"),
            ("character", "角色名 或 null"),
            ("template_id", "模板id 或 null"),
            ("sense_type", "visual/auditory/olfactory/tactile/gustatory/all 或 null"),
            ("scene", "场景描述 或 null"),
            ("hook_id", "伏笔id 或 null"),
            ("hook_content", "伏笔内容 或 null"),
            ("force_name", "势力名 或 null"),
            ("location_name", "地点名 或 null"),
            ("item_name", "物品名 或 null"),
            ("description", "描述文本 或 null"),
            ("search_query", "搜索关键词 或 null"),
            ("text", "待分析文本 或 null"),
            ("setting_text", "设定内容文本 或 null"),
            ("message", "给AI的附加指令 或 null"),
            ("find_text", "要查找的文本 或 null"),
            ("replace_text", "要替换为的文本 或 null"),
            ("target_index", "目标章节位置（reorder用） 或 null"),
            ("analyze_type", "rhythm/character_arc/logic/quality/structure 或 null"),
            ("title", "小说标题 或 null"),
            ("genre", "题材类型 或 null"),
            ("stage", "wizard阶段名 或 null"),
            ("page", "页面名（open_page用） 或 null"),
            ("vol_index", "卷序号（0开始，第1卷=0） 或 null"),
            ("entity_type", "force/location/item（delete_world_entity用） 或 null"),
            ("entity_name", "元素名称（delete_world_entity用） 或 null"),
            ("field", "人物字段名（edit_character用：identity/faction/personality/background/obsession/weakness/goal） 或 null"),
            ("value", "新值（edit_character用） 或 null"),
            ("reason", "废弃原因（abandon_hook用） 或 null"),
        ]
        for key, desc in core_params:
            seen.add(key)
            result.append((key, desc))
        # 再收集配置中独有的参数
        for agent in agents:
            for item in agent.get("intents", []):
                for pkey in item.get("params", {}):
                    if pkey not in seen:
                        seen.add(pkey)
                        result.append((pkey, item["params"][pkey]))
        return result

    def _collect_examples(self, agents: list) -> list:
        """从配置收集意图示例"""
        examples = []

        # 高频意图硬编码示例（保证与旧版一致的关键用例）
        high_freq = {
            "check_continuity": '用户："检查第一章连贯性" → {"intent":"check_continuity","params":{"chapter_index":0},"reply":"好的，我来检查第1章与前后章节的连贯性"}',
            "get_stats": '用户："这周写了多少字" → {"intent":"get_stats","params":{},"reply":"我来查看你的写作统计"}',
            "export_book": '用户："导出epub" → {"intent":"export_book","params":{"format":"epub"},"reply":"正在导出EPUB格式电子书"}',
            "continue_writing": '用户："帮我续写500字" → {"intent":"continue_writing","params":{"message":"续写500字"},"reply":"好的，我来续写"}',
            "apply_template": '用户："用退婚流模板" → {"intent":"apply_template","params":{"template_id":"rebirth_revenge"},"reply":"正在应用重生复仇流模板"}',
            "general_chat": '用户："你好" → {"intent":"general_chat","params":{},"reply":"你好！我是书斋AI助手，可以帮你检查章节、生成内容、导出书籍等，有什么需要？"}',
            "add_setting": '用户："添加设定：炁是造化、是灵机" → {"intent":"add_setting","params":{"setting_text":"炁是造化、是灵机"},"reply":"已将设定添加到世界观中"}',
            "edit_selection": '用户（选中文字后）："把这段描写加细节" → {"intent":"edit_selection","params":{"message":"把这段描写加细节"},"reply":"好的，我来修改选中的文字"}',
            "add_chapter": '用户："新建第6章" → {"intent":"add_chapter","params":{"chapter_index":5},"reply":"好的，新建第6章"}',
            "delete_chapter": '用户："删除第5章" → {"intent":"delete_chapter","params":{"chapter_index":4},"reply":"确定要删除第5章吗？"}',
            "reorder_chapter": '用户："把第2章移到第4章后面" → {"intent":"reorder_chapter","params":{"chapter_index":1,"target_index":3},"reply":"好的，调整章节顺序"}',
            "find_replace": '用户："把陆远替换为路远" → {"intent":"find_replace","params":{"find_text":"陆远","replace_text":"路远"},"reply":"好的，全文替换"}',
            "analyze_chapter": '用户："分析第1章的节奏和结构" → {"intent":"analyze_chapter","params":{"chapter_index":0,"analyze_type":"rhythm"},"reply":"好的，我来分析第1章"}',
            "open_page": '用户："打开伏笔管理" → {"intent":"open_page","params":{"page":"伏笔管理"},"reply":"好的，正在打开伏笔管理面板"}',
            "summarize_plot": '用户："总结一下故事主线" → {"intent":"summarize_plot","params":{},"reply":"好的，我来梳理故事主线"}',
            "create_project": '用户："新建一本仙侠小说叫《问道苍穹》" → {"intent":"create_project","params":{"title":"问道苍穹","genre":"仙侠"},"reply":"好的，新建仙侠小说《问道苍穹》"}',
            "add_character": '用户："添加角色：林墨，28岁程序员，性格冷静" → {"intent":"add_character","params":{"character":"林墨","description":"28岁程序员，性格冷静"},"reply":"好的，添加角色林墨"}',
            "generate_all_outlines": '用户："生成全部章节大纲" → {"intent":"generate_all_outlines","params":{},"reply":"好的，生成全部章节大纲"}',
            "generate_all_chapters": '用户："全部生成" → {"intent":"generate_all_chapters","params":{},"reply":"好的，生成全部正文"}',
            "generate_characters": '用户："生成人物档案" → {"intent":"generate_characters","params":{},"reply":"好的，生成人物档案"}',
            "wizard": '用户："仙侠"（在创作向导中回答题材）→ {"intent":"wizard","params":{"stage":"ask_genre","message":"仙侠"},"reply":"好的，你选择了仙侠题材"}',
            "search": '用户："搜索唐朝官制" → {"intent":"search","params":{"query":"唐朝官制"},"reply":"好的，正在搜索唐朝官制相关信息"}',
            "rename_chapter": '用户："把第3章改名为风起云涌" → {"intent":"rename_chapter","params":{"chapter_index":2,"title":"风起云涌"},"reply":"好的，重命名第3章"}',
            "delete_volume": '用户："删除第2卷" → {"intent":"delete_volume","params":{"vol_index":1},"reply":"好的，删除第2卷"}',
            "edit_character": '用户："把林墨的性格改成冷淡寡言" → {"intent":"edit_character","params":{"character":"林墨","field":"personality","value":"冷淡寡言"},"reply":"好的，修改林墨的性格"}',
            "delete_world_entity": '用户："删除势力青云门" → {"intent":"delete_world_entity","params":{"entity_type":"force","entity_name":"青云门"},"reply":"好的，删除势力青云门"}',
        }
        # 已处理的意图
        done = set()
        for intent_name, example in high_freq.items():
            examples.append(example)
            done.add(intent_name)
        # 补充配置中还有但未覆盖的意图
        for agent in agents:
            for item in agent.get("intents", []):
                intent = item["intent"]
                if intent in done:
                    continue
                ex_list = item.get("examples", [])
                if ex_list:
                    examples.append(
                        f'用户："{ex_list[0]}" → {{"intent":"{intent}","params":{{}},"reply":"好的"}}'
                    )
                    done.add(intent)
        return examples


# ── 模块级便捷访问 ──

def get_config() -> AgentConfig:
    """获取 AgentConfig 单例"""
    return AgentConfig()
