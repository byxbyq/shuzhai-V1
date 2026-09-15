# -*- coding: utf-8 -*-
"""书斋 V66 — 生成器 Prompt 构建（从 generator.py 拆分）

包含 ChapterGenerator 的 prompt 构建方法，作为 Mixin 使用。
"""
import re
from typing import List, Optional

from backend.constants import FORBIDDEN_WORDS, FORBIDDEN_PLOTS
from backend.services.memory_synthesizer import synthesize_memory_context
from backend.prompt_sanitizer import sanitize_light
from backend.services.scene_d_discipline import SceneDChecker
from backend.services.writer_techniques import TechniqueManager


class GeneratorPromptsMixin:
    """Prompt 构建 Mixin — 与 ChapterGenerator 合并使用"""

    def _extract_relevant_characters(self, text: str) -> List[str]:
        """从文本中提取出现的已知角色名（用于按需注入角色状态）"""
        if not self.ledger.character_states:
            return []
        relevant = []
        for name in self.ledger.character_states.keys():
            if name in text:
                relevant.append(name)
        return relevant[:8]  # 限制最多8个角色，避免 prompt 过长

    def _inject_world(self, parts: list) -> None:
        """世界观注入：注入结构化世界观设定"""
        world_text = self.world.to_prompt()
        if world_text:
            parts.append(world_text)

    def _inject_settings_library(self, parts: list) -> None:
        """设定库注入：道具/功法 + 势力/组织"""
        if not self.ledger:
            return
        lines = []
        artifacts = self.ledger.get_all_artifacts()
        if artifacts:
            lines.append("## 设定库·道具/功法")
            for a in artifacts:
                status_mark = " [已毁]" if a.get('destroyed') else ""
                owner_str = f" | 持有着:{a.get('owner','')}" if a.get('owner') else ""
                lines.append(
                    f"- [{a.get('type','未分类')}] {a.get('name','')} "
                    f"({a.get('grade','不明')}){owner_str}: {a.get('description','')}{status_mark}"
                )
            lines.append("（以上道具设定在正文中需保持一致，已毁道具不应无故出现）")

        factions = self.ledger.get_all_factions()
        if factions:
            if lines:
                lines.append("")
            lines.append("## 设定库·势力/组织")
            for f in factions:
                status_mark = "" if f.get('status') == 'active' else f" [{f.get('status','')}]"
                leader_str = f" | 首领:{f.get('leader','')}" if f.get('leader') else ""
                members = f.get('members', [])
                members_str = f" | 成员:{','.join(members)}" if members else ""
                lines.append(
                    f"- [{f.get('type','组织')}] {f.get('name','')}{leader_str}{members_str}: "
                    f"{f.get('description','')}{status_mark}"
                )
            lines.append("（以上势力设定在正文中需保持一致）")

        if lines:
            parts.append("\n".join(lines))

    def _inject_outline_context(self, parts: list, chapter_index: int) -> None:
        """全书大纲上下文（新格式 dict）：注入概括性的全书方向"""
        if not self._project:
            return
        novel_outline = self._project.novel_outline or {}
        if not novel_outline or not isinstance(novel_outline, dict):
            # 兼容旧格式 list（如果还在的话）
            if isinstance(novel_outline, list) and novel_outline:
                # 旧格式：只取幕标题作为简要参考
                novel_parts = ["## 全书大纲（旧格式）\n"]
                for act in novel_outline:
                    if isinstance(act, dict):
                        novel_parts.append(f"- {act.get('title', '')}")
                parts.append("\n".join(novel_parts))
            return

        ch_num = chapter_index + 1

        # 4.2 分卷纲要注入（三层架构：卷纲要 → 全书概括 → 单章）
        volumes = getattr(self._project, 'volumes', None) or []
        if volumes:
            cur_vol = None
            for vol in volumes:
                vol_chapters = vol.get('chapters', [])
                if ch_num in vol_chapters or (isinstance(vol_chapters, list) and vol_chapters and min(vol_chapters) <= ch_num <= max(vol_chapters)):
                    cur_vol = vol
                    break
            if cur_vol is None and volumes:
                cur_vol = volumes[0]
            if cur_vol:
                vol_outline = cur_vol.get('outline', {})
                if isinstance(vol_outline, dict):
                    summary = vol_outline.get('summary', '')
                    theme = vol_outline.get('theme', '')
                    if summary or theme:
                        vol_parts = ["## 当前卷纲要\n"]
                        vol_parts.append(f"卷名：{cur_vol.get('title', '')}")
                        if summary:
                            vol_parts.append(f"概要：{summary}")
                        if theme:
                            vol_parts.append(f"主题：{theme}")
                        key_events = vol_outline.get('key_events', [])
                        if key_events:
                            vol_parts.append("关键事件：")
                            for ke in key_events:
                                vol_parts.append(f"  · {ke}")
                        parts.append("\n".join(vol_parts))

        # 全书大纲（dict 格式）：注入概括性的方向，不包含具体章节内容
        novel_parts = ["## 全书大纲（方向性指引）\n"]
        if novel_outline.get('theme'):
            novel_parts.append(f"- 主题：{novel_outline['theme']}")
        if novel_outline.get('core_conflict'):
            novel_parts.append(f"- 核心冲突：{novel_outline['core_conflict']}")
        if novel_outline.get('story_arc'):
            novel_parts.append(f"- 故事走向：{novel_outline['story_arc']}")
        if novel_outline.get('ending'):
            novel_parts.append(f"- 结局指引：{novel_outline['ending']}")
        if novel_outline.get('long_suspense'):
            novel_parts.append(f"- 长线悬念：{novel_outline['long_suspense']}")
        if novel_outline.get('social_picture'):
            novel_parts.append(f"- 社会图景：{novel_outline['social_picture']}")
        if novel_outline.get('tone'):
            novel_parts.append(f"- 基调：{novel_outline['tone']}")
        # 角色弧光（只显示当前章相关角色的弧光）
        if novel_outline.get('character_arcs'):
            novel_parts.append("- 角色弧光：")
            for arc in novel_outline['character_arcs'][:5]:
                if isinstance(arc, dict):
                    novel_parts.append(f"  · {arc.get('character', '')}: {arc.get('arc', '')}")
        # 关键伏笔
        if novel_outline.get('key_hooks'):
            novel_parts.append("- 关键伏笔：")
            for h in novel_outline['key_hooks'][:5]:
                if isinstance(h, str):
                    novel_parts.append(f"  · {h}")
        parts.append("\n".join(novel_parts))

    def _inject_characters(self, parts: list, chapter_index: int, outline_title: str) -> None:
        """人物档案：Lorebook触发 + Truth Ledger角色状态 + 本章出场人物档案"""
        # Lorebook 关键词触发：从大纲中提取关键词，按需注入相关设定
        lorebook_text = self._trigger_lorebook(outline_title)
        if lorebook_text:
            parts.append(lorebook_text)

        # Truth Ledger context — 自动提取相关角色
        # 限制ledger只输出最近15个伏笔（太久远的对当前写作参考价值低），避免全量爆炸
        relevant_chars = self._extract_relevant_characters(outline_title)
        ledger_text = self.ledger.build_context(
            chapter_index,
            relevant_characters=relevant_chars,
            limit_foreshadowing=15  # 总是限制最近15个，避免token爆炸
        )
        if ledger_text:
            parts.append(ledger_text)

        # 人物档案注入：从项目characters中提取本章出场角色
        char_text = self._build_character_context(chapter_index, outline_title)
        if char_text:
            parts.append(char_text)

    def _inject_foreshadow(self, parts: list, chapter_index: int) -> None:
        """伏笔状态：本章待回收/已埋下的伏笔"""
        hook_text = self._build_foreshadow_context(chapter_index)
        if hook_text:
            parts.append(hook_text)

    def _inject_timeline(self, parts: list, chapter_index: int) -> None:
        """时间线注入：计划 vs 实际对照 + 前章衔接锚

        从 TimelineService 获取结构化时间线数据，注入到 prompt 中：
        - 前章实际发生的事件（最近2章）
        - 本章计划（如有）
        - 衔接锚（from_prev / to_next）
        """
        try:
            from backend.timeline_service import TimelineService
            svc = TimelineService(self.project_dir)
            data = svc.get_timeline()
            volumes = data.get("volumes", {})
            if not volumes:
                return

            # 找到当前章节在哪个卷
            ch_num = chapter_index + 1  # 1-based
            tl_parts = []

            # 收集最近2章的实际时间线 + 本章计划
            all_chs = []
            for vol_idx in sorted(volumes.keys(), key=lambda x: int(x) if x.isdigit() else 0):
                vol_data = volumes[vol_idx]
                vol_title = vol_data.get("title", "")
                chs = vol_data.get("chapters", {})
                for ci in sorted(chs.keys(), key=lambda x: int(x) if x.isdigit() else 0):
                    ci_int = int(ci) if ci.isdigit() else 0
                    all_chs.append((ci_int, vol_title, chs[ci]))

            # 找到当前章及前2章
            prev_chs = [(c, v, d) for c, v, d in all_chs if c < ch_num][-2:]
            curr_ch = [(c, v, d) for c, v, d in all_chs if c == ch_num]

            if prev_chs:
                actual_lines = []
                for ci, vol_title, ch_node in prev_chs:
                    actual = ch_node.get("actual", "")
                    if actual:
                        actual_lines.append(f"第{ci}章：{actual[:120]}")
                    events = ch_node.get("events", [])
                    if events:
                        actual_lines.append(f"  核心事件：{'; '.join(str(e) for e in events[:3])}")
                if actual_lines:
                    tl_parts.append("### 前章实际发展\n" + "\n".join(actual_lines))

            if curr_ch:
                ci, vol_title, ch_node = curr_ch[0]
                planned = ch_node.get("planned", "")
                if planned:
                    tl_parts.append(f"### 本章计划\n{planned[:200]}")
                bridge = ch_node.get("bridge", {})
                from_prev = bridge.get("from_prev", "")
                if from_prev:
                    tl_parts.append(f"### 前章衔接锚\n{from_prev}")

            if tl_parts:
                parts.append("## 时间线对照\n" + "\n\n".join(tl_parts))
        except Exception:
            pass

    def _inject_vector_memory(self, parts: list, outline: str, chapter_index: int, distilled: bool) -> None:
        """6.1 增强向量记忆召回：从本章 outline 提取关键实体，分路检索合并 top-10
        有蒸馏记忆时，蒸馏已压缩了前文关键信息，但蒸馏是摘要不是原文
        仍需少量向量召回（减半到5条）提供文风参考和衔接细节
        """
        try:
            from backend.services.project_service import get_shared_vector_memory
            shared_vm = get_shared_vector_memory()
            # 6.1 从 outline 中提取关键实体做多路检索
            entities = self._extract_key_entities_from_outline(outline)
            if entities and len(entities) >= 2:
                recall_texts = []
                seen = set()
                for entity in entities[:6]:
                    text = self.vector_memory.search_for_generation_combined(
                        entity, shared_memory=shared_vm, chapter_index=chapter_index, k=2
                    )
                    if text and text not in seen:
                        recall_texts.append(text)
                        seen.add(text)
                recall_text = "\n---\n".join(recall_texts[:5])  # 合并去重 top-5 个实体结果
                if len(recall_text.split('\n')) > 40:
                    recall_text = "\n---\n".join(recall_texts[:3])
            else:
                recall_k = 2 if distilled else 5
                recall_text = self.vector_memory.search_for_generation_combined(
                    outline, shared_memory=shared_vm, chapter_index=chapter_index, k=recall_k
                )
            if recall_text:
                parts.append(f"## 相关前文记忆（向量召回）\n{recall_text}")
        except Exception:
            pass

    def _extract_key_entities_from_outline(self, outline: str) -> list:
        """从 outline 中用正则提取关键实体（角色名、地名、道具名）"""
        if not outline:
            return []
        entities = []
        # 提取引号内的专名（角色/地名/道具常用引号标注）
        quoted = re.findall(r'[「「『『""]([^」」』』""]{1,10})[」」』』""]', str(outline))
        entities.extend(quoted)
        # 从 ledger 角色名中匹配
        if self.ledger and self.ledger.character_states:
            outline_str = str(outline)
            for name in self.ledger.character_states.keys():
                if name in outline_str and len(name) >= 2:
                    entities.append(name)
        # 道具/功法名
        if self.ledger:
            artifacts = self.ledger.get_all_artifacts()
            outline_str = str(outline)
            for a in artifacts:
                aname = a.get('name', '')
                if aname and len(aname) >= 2 and aname in outline_str:
                    entities.append(aname)
        return list(dict.fromkeys(entities))  # 去重保持顺序

    def _inject_skill_rules(self, parts: list, skill_rules: str) -> None:
        """技能包规则：从前端传来的自定义规则"""
        if skill_rules:
            parts.append(f"## 自定义写作规则（技能包）\n{sanitize_light(skill_rules)}")

    def _build_distilled_memory(self, chapter_index: int, use_distilled: bool) -> Optional[str]:
        """蒸馏记忆检测和构建：从 state_memory 聚合，替代远期章节原文

        从 state_memory/*.json 聚合角色状态/事件/伏笔/新设定，分层压缩，
        无硬字符上限，总字符数与章节数解耦。
        """
        if not use_distilled:
            return None
        try:
            # chapter_index 是 0-based，转 1-based 传给合成器
            return synthesize_memory_context(self.project_dir, chapter_index + 1)
        except Exception:
            return None

    def _build_plot_line_hint(self, chapter_index: int) -> str:
        """构建剧情线提示（主线/支线节奏指令）"""
        if not self._project or chapter_index >= len(self._project.chapters):
            return ""
        bp = self._project.chapters[chapter_index].get('blueprint', {})
        pl = bp.get('plot_line', ['主线'])
        if not isinstance(pl, list) or not pl:
            return ""
        hint = f"\n## 剧情线\n本章属于: {', '.join(pl)}\n"
        if any('支线' in p for p in pl):
            hint += "注意: 支线章节节奏可放缓，侧重人物铺垫和情感刻画\n"
        else:
            hint += "注意: 主线章节节奏紧凑，推进核心剧情\n"
        return hint

    def _build_writing_instructions(self, plot_line_hint: str, title: str, outline: str, context: str, context_label: str, chapter_index: int) -> str:
        """构建写作规范指令：包含角色设定、章节信息、通用写作规范"""
        # 用户输入清洗：context 可能包含用户自定义上下文
        context = sanitize_light(context) if context else ""
        total_chapters = len(self._project.chapters) if self._project else '?'
        genre = getattr(self, 'genre', '')
        if '玄幻' in genre or '仙侠' in genre or '奇幻' in genre or '异界' in genre:
            style_ref = '写出现代幻想类网文的质感——画面感强、设定自然融入叙事、节奏张弛有度。角色对话要有"人味"，可以带脏话、俚语、口头禅'
        elif '历史' in genre:
            style_ref = '写出历史类网文的质感——时代氛围浓厚、细节真实自然、叙事沉稳有力。角色对话要有"人味"，可以带脏话、俚语、口头禅'
        elif '言情' in genre or '恋爱' in genre or '都市' in genre:
            style_ref = '写出现代网文的质感——短句为主、口语化、生活感强、节奏利落。角色对话要有"人味"，可以带脏话、俚语、口头禅'
        else:
            style_ref = '写出现代网文的质感——短句为主、口语化、生活感强、节奏利落。角色对话要有"人味"，可以带脏话、俚语、口头禅'

        # 伏笔回收提示：根据当前章节需要回收的伏笔给出自然收尾指引
        ending_phase_hint = ""
        if self._project:
            ch_num = chapter_index + 1
            foreshadows = getattr(self._project, 'foreshadows', None) or []
            # 找出计划在本章回收的伏笔
            due_foreshadows = [f for f in foreshadows if f.get('resolve_chapter') == ch_num and f.get('status') != 'resolved']
            # 找出尚未回收的旧伏笔（可能需要在后续章节回收）
            pending_old = [f for f in foreshadows if f.get('status') == 'pending' and f.get('plant_chapter', 999) < ch_num - 2]

            if due_foreshadows:
                names = '、'.join(f.get('title', f.get('description', ''))[:20] for f in due_foreshadows[:5])
                ending_phase_hint = f"""
## 伏笔回收
本章需要回收以下伏笔，请在正文中自然处理，不要生硬：
{names}"""
            elif pending_old and ch_num >= total_chapters * 0.7:
                # 故事已过70%，提醒逐步回收旧伏笔
                ending_phase_hint = """
## 注意
故事已进入后半段，请注意逐步回收前期埋下的伏笔，不要全部堆到最后。"""

        scene_d_text = SceneDChecker.get_prompt_instructions()

        return f"""你是起点中文网白金级网文大神，笔下出过3本万订以上作品。你深谙网文的黄金法则——代入感、节奏感、爽感缺一不可。你写的文字像有魔力一样，让读者点开就停不下来，熬到凌晨三点也要看下一章。

现在请你以巅峰状态写作本章，每一句话都要抓住读者的心。
{plot_line_hint}
## 章节标题
{title}

## 当前章节
第{chapter_index + 1}章（共{total_chapters}章）

## 章节大纲（必须覆盖每一个段落，不得遗漏任何一段）
{outline}

{context_label}
{context}

## 写作铁律（必须刻进DNA里遵守）

### 一、代入感是网文的命根
1. **POV深度绑定**：全程跟紧视角人物，读者知道的 = 视角人物知道的。读者不知道的，视角人物也不知道。不要跳出来做上帝解说
2. **感官细节先行**：别告诉读者"他很紧张"，写他的——手心出汗、喉结滚动、心跳声盖过了周围的嘈杂、指尖发麻、嘴里发苦
3. **情绪传染**：先让视角人物有情绪，读者自然会有。高兴就写嘴角压不住，愤怒就写太阳穴突突跳，恐惧就写后脖颈发凉
4. **少说多做**：能通过动作/表情/对话表达的，绝对不用旁白解释。"他愣住了"比"他感到十分惊讶"强一百倍

### 二、文字表达
1. 句式灵活多变，长短句自然穿插。紧张时全是短句，一个字一个字往外蹦；抒情时句子可以拉长，像呼吸一样舒缓
2. 段落长短严重不均：有的一句话独立成段（制造冲击力），有的五六句铺陈场景。绝对不要每段都是三行，那是教科书
3. 用"的"不用"之"：这是现代网文，不是文言文。正常说话，正常写作
4. 少用连接词。"然而""因此""于是""紧接着"能删就删，用动作和场景切换自然过渡
5. 句首要多样化，连续两句开头绝对不能一样。连续三段开头绝对不能都是人名

### 三、场景与语气
1. 场景是活的：战斗要写出烟尘味、血腥味、兵器碰撞的震手感；日常要写出烟火气、温度、光线的变化
2. 每个角色说话都不一样：有人话多有人话少，有人爱装逼有人很直，有人说话带刺有人喜欢绕弯子。绝对不能所有角色都是一个语气
3. 对话要像真人：不一定每句话都在推进剧情。人会说废话、会转移话题、会言不由衷、会说一半就停。一段对话中可以有30%的内容是"看似无用的闲话"——这种闲话让角色更像真人，而不是剧情传递机器。但要把握：闲话不能长时间拖慢节奏，快慢穿插。
4. 每个选择都有代价。选A就失去B，赢了这一场就要付出别的。没有代价的选择读者不会在乎

### 四、节奏——网文的灵魂
1. **钩子法则**：
   - 章节开头300字内必须有钩子（悬念/冲突/反常/疑问），绝对不能慢悠悠地铺场景
   - 每一节末尾留小钩子，整章末尾留大钩子。让读者看完本能地点"下一章"
   - 钩子类型：悬念钩子（他到底是谁？）、危机钩子（刀已经架在脖子上了）、情绪钩子（她竟然背叛了他？）
2. **爽点节奏**：
   - 小爽点（打脸/装X/小收获）每1-2章一个
   - 中爽点（突破/报仇/获得重要东西）每5-10章一个
   - 大爽点（阶段boss战/重大转折）每卷1-2个
   - 爽点之前必须有压抑：压得越低，弹得越高
3. **张弛有度**：
   - 紧张的战斗/冲突之后，必须有一小段缓冲（日常/对话/休整）
   - 但缓冲不是灌水，缓冲段里也要埋线索、铺感情、为下一个高潮蓄力
4. **信息交付**：世界观设定要"喂"给读者，不要"灌"给读者。通过剧情、对话、冲突自然带出来，谁会耐着性子看你写大段设定？

### 五、反AI味——像人写的，像大神写的
1. **口语化**：用碎句、省略号、破折号、半句话。角色对话要像真人说话，会打断、会结巴、会说一半改主意、会回避问题、会言不由衷
2. **删掉这些词**："突然""忽然""仿佛""似乎""宛若""犹如"每章最多各1次。能用实写就不用比喻
3. **具体化**：不写"一股寒意"，写"后脖颈汗毛一根根竖起来"；不写"他很愤怒"，写"指节捏得发白，指缝里渗出血丝"
4. **绝对不要写总结句**："这意味着…""不难看出…""这证明了…""由此可见…"。让读者自己体会，你是写故事的，不是讲道理的
5. **不要完美**：真人写的东西不是每一句都工整对仗。可以有口语化的词，可以有不那么"漂亮"的句子。真实感比华丽重要
6. **文风参考**：{style_ref}
7. 禁用词汇：{', '.join(FORBIDDEN_WORDS[:10])}
8. 禁用情节：{', '.join(FORBIDDEN_PLOTS)}
9. 字数要求：严格按上文<wordcount>标签中的目标字数写作；如无标签则写到2500字以上。宁多勿少，写够了再收尾

{scene_d_text}

直接输出章节正文。不要输出章节标题、不要加"未完待续"等结尾语。
写的时候，想象你正在连载，读者就在屏幕对面等着，每一章都要让他们拍大腿喊"卧槽牛逼"。
{ending_phase_hint}"""

    def _build_generation_prompt(self, title: str, outline: str, context: str, chapter_index: int = 0, issues: List[str] = None, **kwargs) -> str:
        parts = []

        # 1. 世界观注入
        self._inject_world(parts)

        # 2. 全书大纲上下文
        self._inject_outline_context(parts, chapter_index)

        # 3. 蒸馏记忆检测（供后续各步骤判断是否启用蒸馏优化）
        use_distilled = kwargs.get('use_distilled_memory', True) if kwargs else True
        distilled_memory_text = self._build_distilled_memory(chapter_index, use_distilled)
        self._distilled_cache = distilled_memory_text  # 供 _inject_characters 等内部方法引用

        # 3.5 结构化设定库（道具/功法/势力）
        self._inject_settings_library(parts)

        # 4. 人物档案 + Lorebook + Truth Ledger
        outline_str = str(outline) if outline else ''
        title_str = str(title) if title else ''
        context_str = str(context if context else '')
        self._inject_characters(parts, chapter_index, outline_str + " " + title_str + " " + context_str)

        # 4.5 前3章摘要（叙事连续性）
        if self._project and chapter_index > 0:
            recent_summaries = []
            for prev_idx in range(max(0, chapter_index - 3), chapter_index):
                if prev_idx < len(self._project.chapters):
                    prev_ch = self._project.chapters[prev_idx]
                    s = prev_ch.get("summary", "")
                    if s:
                        recent_summaries.append(f"第{prev_idx + 1}章: {s}")
            if recent_summaries:
                parts.append("## 前章剧情摘要\n" + "\n".join(recent_summaries))

        # 5. 伏笔状态
        self._inject_foreshadow(parts, chapter_index)

        # 5.5 时间线注入（计划 vs 实际 + 前章衔接锚）
        self._inject_timeline(parts, chapter_index)

        # 5.6 支线追踪注入
        if self.ledger:
            subplot_text = self.ledger.get_subplot_context(chapter_index + 1)
            if subplot_text:
                parts.append(subplot_text)

        # 6. 向量记忆召回
        self._inject_vector_memory(parts, outline, chapter_index, bool(distilled_memory_text))

        # 7. 技能包规则
        skill_rules = kwargs.get('skill_rules', '') if kwargs else ''
        self._inject_skill_rules(parts, skill_rules)

        # 8. 蒸馏记忆注入到 prompt（蒸馏检测已在前文完成）
        if distilled_memory_text:
            parts.append(distilled_memory_text)

        # 9. 清理临时缓存
        self._distilled_cache = None

        # 10. 根据是否有蒸馏记忆，调整上下文标签
        # 有蒸馏记忆时，context 中只有最近章节的原文末尾，标注清楚让 AI 知道这是衔接用而非完整前文
        context_label = "## 最近章节原文（用于衔接上一章结尾）" if distilled_memory_text else "## 上下文"

        # 11. 写作规范指令
        plot_line_hint = self._build_plot_line_hint(chapter_index)
        instructions = self._build_writing_instructions(plot_line_hint, title, outline, context, context_label, chapter_index)
        parts.append(instructions)

        # 11.5 作家技法卡注入（按章节类型自动激活）
        chapter_type = self._detect_chapter_type(title, outline) if hasattr(self, '_detect_chapter_type') else 'daily'
        technique_mgr = TechniqueManager()
        cards = technique_mgr.activate_for_chapter_type(chapter_type)
        if cards:
            parts.append(technique_mgr.build_prompt(cards))

        # 11.6 承诺台账：待兑现的叙事承诺
        pending_cmt = getattr(self, '_pending_commitments_context', '')
        if pending_cmt:
            parts.append(pending_cmt)

        # 12. 上一版修复问题
        if issues:
            parts.append(f"\n## 上一版需要修复的问题\n" + "\n".join(f"- {i}" for i in issues))

        # 13. 去AI味动态反馈：注入上一章审计问题作为本章引导
        if self.ledger:
            feedback_text = self.ledger.get_audit_feedback(chapter_index + 1)
            if feedback_text:
                parts.append(f"\n## 去AI味动态引导\n{feedback_text}")

        return "\n\n".join(parts)

    def _build_spot_fix_prompt(self, current_para: str, prev_para: str,
                               next_para: str, issue_desc: str) -> str:
        """构建Spot-Fix的AI prompt：告诉AI只修改指定段落，不要改动其他内容"""
        parts = []

        parts.append("你是一个小说章节编辑器。以下是一段需要修复的段落，请根据问题描述进行修改。")

        # 问题描述（用户输入，需清洗）
        parts.append(f"## 问题描述\n{sanitize_light(issue_desc)}")

        # 前文上下文
        if prev_para.strip():
            parts.append(f"## 前文上下文（仅供参考，不要修改）\n{prev_para.strip()}")

        # 需要修复的段落
        parts.append(f"## 需要修复的段落\n{current_para.strip()}")

        # 后文上下文
        if next_para.strip():
            parts.append(f"## 后文上下文（仅供参考，不要修改）\n{next_para.strip()}")

        # 要求
        parts.append("""## 要求
1. 只修改上面"需要修复的段落"，不要改动前文和后文
2. 保持段落风格、语气、人称一致
3. 保持段落长度大致相近
4. 直接输出修复后的完整段落文本，不要添加任何解释、标记或代码块符号
5. 不要输出"修复后的段落："之类的前缀""")

        return "\n\n".join(parts)
