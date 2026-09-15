# -*- coding: utf-8 -*-
"""ChapterGenerator 人设/大纲/蓝图生成与状态提取（从 generator.py 拆分）"""
import json, logging, re
from typing import Optional, Dict, Any

from backend.prompt_sanitizer import sanitize_user_input, sanitize_light
from backend.constants import FORBIDDEN_WORDS
from backend.services.memory_synthesizer import synthesize_memory_context

logger = logging.getLogger(__name__)


class ChapterBlueprintMixin:
    """提供人物生成、大纲生成、蓝图解析与状态提取方法"""

    def _build_character_context(self, chapter_index: int, outline_text: str) -> str:
        """构建人物档案上下文：注入本章出场人物的静态档案 + 动态节点"""
        _proj = self.project
        chars = getattr(_proj, 'characters', []) if _proj else []
        if not chars:
            return ""

        # 获取本章blueprint里的character_nodes（动态节点）
        ch = None
        try:
            if _proj and chapter_index < len(_proj.chapters):
                ch = _proj.chapters[chapter_index]
        except Exception as e:
            logger.warning("获取章节blueprint失败: %s", e)
        char_nodes = []
        if ch and isinstance(ch.get('blueprint'), dict):
            char_nodes = ch['blueprint'].get('character_nodes', [])

        # 如果有动态节点，优先注入有节点的人物；否则注入全部核心人物（让AI知道全书人物关系网）
        relevant_chars = []
        if char_nodes:
            node_names = {n.get('name', '') for n in char_nodes}
            relevant_chars = [c for c in chars if c.get('name', '') in node_names]
        else:
            # 先按名字匹配大纲中的出场人物
            matched = [c for c in chars if c.get('name', '') and c['name'] in outline_text]
            if matched:
                relevant_chars = matched[:6]
            else:
                # 大纲没提到人物名时，注入前8个核心人物（按重要性排序）
                sorted_chars = sorted(chars, key=lambda c: {'主角': 0, '主要': 1, '次要': 2, '路人': 3}.get(c.get('importance', ''), 4))
                relevant_chars = sorted_chars[:8]

        if not relevant_chars:
            return ""

        lines = []
        for c in relevant_chars:
            name = c.get('name', '')
            line = f"- {name}（{c.get('faction','')}·{c.get('importance','')}）: "
            details = []
            if c.get('identity'): details.append(f"身份[{c['identity']}]")
            if c.get('background'): details.append(f"背景[{c['background']}]")
            if c.get('personality'): details.append(f"性格[{c['personality']}]")
            if c.get('obsession'): details.append(f"执念[{c['obsession']}]")
            if c.get('weakness'): details.append(f"软肋[{c['weakness']}]")
            if c.get('goal'): details.append(f"目标[{c['goal']}]")
            line += " ".join(details)
            # 羁绊
            bonds = c.get('bonds', [])
            if bonds and isinstance(bonds, list):
                bond_strs = [f"{b.get('target','')}:{b.get('relation','')}" for b in bonds if isinstance(b, dict)]
                if bond_strs:
                    line += " | 羁绊[" + ", ".join(bond_strs) + "]"
            # 动态节点
            for n in char_nodes:
                if n.get('name') == name:
                    if n.get('appearance') == 'first':
                        line += " | ⚠️本章首次登场"
                    elif n.get('appearance') == 'exit':
                        line += " | ⚠️本章退场"
                    if n.get('status_change'):
                        line += f" | 本章变化[{n['status_change']}]"
                    break
            lines.append(line)

        result = "## 本章人物档案（严格遵守人设）\n" + "\n".join(lines)
        # 如有首次登场人物，追加自然介绍指令
        if any("本章首次登场" in l for l in lines):
            result += "\n\n⚠️ 首次登场人物需在符合剧情的情境下，自然地介绍其身份背景。可通过叙述旁白、其他角色对话、或路人议论等方式融入剧情，不要突兀地堆砌设定。"
        return result

    def _build_foreshadow_context(self, chapter_index: int) -> str:
        """构建伏笔上下文：注入活跃伏笔+主动提醒AI推进回收，按逾期/待回收排序"""
        try:
            from backend.services.project_service import get_ledger
            ledger = get_ledger()
            if not ledger:
                return ""
        except Exception:
            return ""

        ch_num = chapter_index + 1
        active_hooks = ledger.get_pending_hooks()
        if not active_hooks:
            return ""

        lines = ["## 伏笔状态（以下伏笔必须在正文中推进或回收）"]
        for h in active_hooks[:10]:
            line = f"- [{h.status}] 第{h.planted_chapter}章埋下: {h.content[:40]}"
            expected = getattr(h, 'expected_recovery_chapter', 0) or 0
            try:
                expected = int(expected)
            except (ValueError, TypeError):
                expected = 0
            if expected and expected <= ch_num:
                line += " ⚠ 已逾期"
            elif expected:
                line += f" (预期第{expected}章回收)"
            lines.append(line)
        return "\n".join(lines)

    def _trigger_lorebook(self, text: str) -> str:
        """Lorebook 关键词触发：按需注入与当前大纲相关的设定项
        遍历 freeform 设定 + 结构化世界观字段，只有当关键词出现在 text 中时才注入
        """
        import re
        parts = []

        # 1. freeform 设定（跳过已被结构化字段覆盖的 key）
        _covered_keys = {"整体风格", "时代背景", "核心设定", "氛围基调", "叙事风格", "时代环境", "世界规则"}
        for key, val in self.world.freeform.items():
            if key in _covered_keys:
                continue
            keywords = [key]
            val_keywords = re.findall(r'[\u4e00-\u9fa5]{2,4}', val or "")
            keywords.extend(val_keywords[:5])
            for kw in keywords:
                if kw and len(kw) >= 2 and kw in text:
                    parts.append(f"- {key}: {val}")
                    break

        # 2. 叙事风格关键词触发
        ns = self.world.narrative_style
        for field, val in ns.items():
            if not val:
                continue
            kws = re.findall(r'[\u4e00-\u9fa5]{2,4}', val)
            for kw in kws:
                if kw in text:
                    parts.append(f"- 叙事风格.{field}: {val}")
                    break

        # 3. 时代环境关键词触发
        era = self.world.era
        for field, val in era.items():
            if not val:
                continue
            kws = re.findall(r'[\u4e00-\u9fa5]{2,4}', val)
            for kw in kws:
                if kw in text:
                    parts.append(f"- 时代环境.{field}: {val}")
                    break

        # 4. 世界规则关键词触发
        for rule in self.world.world_rules:
            rule_str = rule if isinstance(rule, str) else (str(rule.get('key','')) + ' ' + str(rule.get('val','')) if isinstance(rule, dict) else str(rule))
            kws = re.findall(r'[\u4e00-\u9fa5]{2,4}', rule_str)
            for kw in kws:
                if kw in text:
                    parts.append(f"- 世界规则: {rule_str}")
                    break

        if parts:
            return "## 触发的相关设定（Lorebook）\n" + "\n".join(parts)
    def generate_characters(self, novel_outline: str = "") -> list:
        """基于世界观+全书大纲生成结构化人物档案
        Returns: [{name, identity, faction, personality, background, obsession, weakness, goal, bonds, importance, ...}]
        """
        world_text = self.world.to_prompt()
        outline_part = ""
        if novel_outline:
            outline_part = f"\n\n【全书大纲】\n{novel_outline[:3000]}"
            mode_hint = "仔细阅读大纲，提取大纲中出现的所有角色（包括只提到名字的角色），为每个角色生成完整人物档案。不要遗漏任何角色。"
        else:
            mode_hint = "基于世界观设定，预生成一套完整的角色库。要求：1个主角、2-3个核心配角（盟友/同伴）、1-2个核心反派、2-3个次要配角。角色之间要有羁绊关系。角色要符合世界观设定，不要违反禁止事项。"

        prompt = f"""你是专业小说角色设计师。{mode_hint}

【输出要求 - 最重要规则】
1. 直接输出 JSON 数组，不要任何分析、解释、寒暄或思考过程
2. JSON 必须放在 ```json 代码块中
3. 不要在代码块外写任何文字

【世界观设定】
{world_text or '（未设定）'}{outline_part}

【角色档案字段要求】
1. 为每个角色生成完整档案：姓名/身份/阵营(主角/配角/反派/中立)/性格/身世过往/执念/软肋/目标/人物羁绊/角色定位(核心/次要)
2. 人物羁绊用结构化格式：[{{"target":"角色名","relation":"仇恨/信任/爱慕/利用/师徒","note":"说明"}}]
3. 核心人物至少1个主角、1个核心反派
4. 性格、执念、软肋必须具体，不要泛泛而谈
5. 人物不得违背世界观设定（时代环境、世界规则）
6. 【核心矛盾绑定 - 最重要】主角的性格、执念、软肋必须与世界观的核心力量体系形成闭环绑定：
   - 主角的力量来源必须绑定个人创伤或原生缺失（力量越强 = 越暴露自身弱点）
   - 主角最想要的东西，恰恰是主角的能力在剥夺的东西（例如：力场隔绝伤害，也隔绝亲密）
   - 力量的代价必须具体且不可逆（生理反噬/精神消耗/情感封闭/寿命燃烧）——不允许"用多了会累"这种模糊描述
7. 【配角独立目标】每个核心配角必须有完全独立于主角的欲望、秘密和行动动机：
   - 配角的行动不是为了帮主角，而是为了实现自己的目标——只是恰好与主角的路径交叉或冲突
   - 反派必须有读者能理解甚至同情的动机，不能只是"坏"
8. 【能力代价】如果主角拥有特殊能力，必须在档案中明确：
   - cost字段：使用能力的生理/精神代价
   - curse字段：能力带来的无法摆脱的诅咒或副作用

【返回格式示例】
```json
[{{"name":"角色名","identity":"身份","faction":"主角/配角/反派","personality":"性格","background":"身世","obsession":"执念","weakness":"软肋","goal":"目标","bonds":[{{"target":"","relation":"","note":""}}],"importance":"核心/次要","cost":"使用能力的代价","curse":"能力带来的诅咒"}}]
```"""
        raw = self.ai.generate(prompt, max_tokens=4096)
        # 解析JSON
        import re, json
        # 第1层：尝试提取json代码块（处理可能被截断的情况）
        json_match = re.search(r'```json\s*([\s\S]+?)\s*```', raw)
        if json_match:
            try:
                chars = json.loads(json_match.group(1))
                if isinstance(chars, list):
                    # 过滤掉非dict元素（AI可能返回字符串列表）
                    chars = [c for c in chars if isinstance(c, dict)]
                    if chars:
                        self._validate_character_bonds(chars)
                        return chars
            except json.JSONDecodeError as e:
                logger.debug("角色生成第1层失败（闭合json代码块解析）: %s", e)
        # 第2层：尝试提取未闭合的json代码块（AI返回被截断时）
        json_match2 = re.search(r'```json\s*([\s\S]+)', raw)
        if json_match2:
            try:
                chars = json.loads(json_match2.group(1).rstrip('`').rstrip())
                if isinstance(chars, list):
                    chars = [c for c in chars if isinstance(c, dict)]
                    if chars:
                        self._validate_character_bonds(chars)
                        return chars
            except json.JSONDecodeError as e:
                logger.debug("角色生成第2层失败（未闭合json代码块解析）: %s", e)
        # 第3层：尝试直接解析
        try:
            chars = json.loads(raw)
            if isinstance(chars, list):
                chars = [c for c in chars if isinstance(c, dict)]
                if chars:
                    self._validate_character_bonds(chars)
                    return chars
        except Exception as e:
            logger.debug("角色生成第3层失败（直接JSON解析）: %s", e)
        # 第4层：尝试提取第一个[到最后的]之间的内容
        try:
            start = raw.find('[')
            end = raw.rfind(']')
            if start >= 0 and end > start:
                json_str = raw[start:end+1]
                chars = json.loads(json_str)
                if isinstance(chars, list):
                    chars = [c for c in chars if isinstance(c, dict)]
                    if chars:
                        self._validate_character_bonds(chars)
                    return chars
        except Exception as e:
            logger.debug("角色生成第4层失败（方括号截取解析）: %s", e)
            # 第5层：如果标准解析失败，尝试修复常见的JSON格式问题
            try:
                start = raw.find('[')
                end = raw.rfind(']')
                if start >= 0 and end > start:
                    json_str = raw[start:end+1]
                    # 移除可能的尾随逗号
                    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
                    chars = json.loads(json_str)
                    if isinstance(chars, list):
                        self._validate_character_bonds(chars)
                        return chars
            except Exception as e2:
                logger.debug("角色生成第5层失败（修复尾随逗号后解析）: %s", e2)
        # 第6层：处理截断的JSON（AI输出被截断时），逐步补全闭合括号
        try:
            start = raw.find('[')
            if start >= 0:
                json_str = raw[start:]
                # 移除末尾的不完整部分，尝试逐层闭合
                # 先找到最后一个完整的 } 或 ]
                last_complete = max(json_str.rfind('},'), json_str.rfind('}]'), json_str.rfind('}\n'))
                if last_complete > 0:
                    # 截取到最后一个完整对象
                    candidate = json_str[:last_complete+1]
                    # 移除尾随逗号
                    candidate = re.sub(r',\s*$', '', candidate)
                    # 计数需要补多少层 ]
                    depth = 0
                    max_depth = 0
                    for ch in candidate:
                        if ch == '[' or ch == '{':
                            depth += 1
                            max_depth = max(max_depth, depth)
                        elif ch == ']' or ch == '}':
                            depth -= 1
                    # 补全闭合括号
                    closes = ''
                    d = depth
                    # 从内层往外补：先补 } 再补 ]
                    while d > 0:
                        closes += '}]' if d <= 2 else '}'
                        d -= 1
                    # 更智能的补全：先数开括号
                    open_braces = candidate.count('{') - candidate.count('}')
                    open_brackets = candidate.count('[') - candidate.count(']')
                    closes = '}' * max(0, open_braces) + ']' * max(0, open_brackets)
                    fixed = candidate + closes
                    chars = json.loads(fixed)
                    if isinstance(chars, list):
                        chars = [c for c in chars if isinstance(c, dict) and c.get('name')]
                        if chars:
                            self._validate_character_bonds(chars)
                            logger.info("角色生成第6层成功（截断修复）: 提取到 %d 个角色", len(chars))
                            return chars
        except Exception as e3:
            logger.debug("角色生成第6层失败（截断修复）: %s", e3)
        logger.error("角色生成失败: 6层fallback全部失效，原始输出前500字符: %s", raw[:500])
        return []

    def _validate_character_bonds(self, chars: list):
        """人物羁绊交叉校验：标记矛盾对（如A恨B但B信任A）"""
        _opposite = {
            "仇恨": ["信任", "爱慕", "师徒"],
            "信任": ["仇恨", "利用"],
            "爱慕": ["仇恨"],
            "利用": ["信任", "师徒"],
        }
        for i, a in enumerate(chars):
            a_bonds = a.get("bonds", [])
            if not isinstance(a_bonds, list):
                continue
            for bond in a_bonds:
                # bonds可能是字符串或对象
                if isinstance(bond, str):
                    continue  # 字符串格式的bonds跳过校验
                if not isinstance(bond, dict):
                    continue
                target_name = bond.get("target", "")
                relation = bond.get("relation", "")
                # 找到目标角色
                for j, b in enumerate(chars):
                    if j == i or b.get("name") != target_name:
                        continue
                    b_bonds = b.get("bonds", [])
                    if not isinstance(b_bonds, list):
                        continue
                    for b_bond in b_bonds:
                        if b_bond.get("target") == a.get("name"):
                            b_rel = b_bond.get("relation", "")
                            opposites = _opposite.get(relation, [])
                            if b_rel in opposites:
                                # 标记矛盾
                                note = bond.get("note", "")
                                bond["note"] = f"[⚠️羁绊矛盾: {target_name}对{a.get('name')}={b_rel}] {note}"
                                break
    def generate_outline(self, title: str, genre: str = "", length: int = 10, inspiration: str = "", volume_index: int = None):
        """生成全书大纲 - 基于世界观+角色设定，可选灵感碎片
        volume_index: 若指定，则按卷生成该卷的纲要（summary/theme/key_events）
        """
        # 4.4 按卷生成：若指定 volume_index，注入该卷已有上下文
        vol_context = ""
        if volume_index is not None:
            try:
                proj = self.project
                volumes = getattr(proj, 'volumes', None) or [] if proj else []
                if 0 <= volume_index < len(volumes):
                    vol = volumes[volume_index]
                    vol_outline = vol.get('outline', {})
                    if isinstance(vol_outline, dict):
                        summary = vol_outline.get('summary', '')
                        theme = vol_outline.get('theme', '')
                        key_events = vol_outline.get('key_events', [])
                        if summary or theme or key_events:
                            vp = [f"【当前卷已有纲要：{vol.get('title', '')}】"]
                            if summary:
                                vp.append(f"卷概要：{summary}")
                            if theme:
                                vp.append(f"卷主题：{theme}")
                            if key_events:
                                vp.append("卷关键事件：")
                                for ke in key_events:
                                    vp.append(f"  · {ke}")
                            vol_context = "\n".join(vp) + "\n"
            except Exception as e:
                logger.warning("获取卷上下文失败: %s", e)
        world_text = self.world.to_prompt() if self.world else ""
        char_text = ""
        freeform_world = ""
        try:
            from backend.services.project_service import state
            proj = self.project or (state.project if state else None)
            if proj:
                # 读取自由格式世界观设定（步骤①面板编辑的内容）
                ws = getattr(proj, 'world_settings', None) or {}
                if ws and isinstance(ws, dict):
                    ws_lines = []
                    for k, v in ws.items():
                        if v and str(v).strip():
                            ws_lines.append(f"- {k}：{v}")
                    if ws_lines:
                        freeform_world = "\n\n【自由格式世界观设定（步骤①）】\n" + "\n".join(ws_lines)
                # 读取角色设定
                cs = proj.character_settings or {}
                if cs:
                    char_lines = []
                    for name, data in cs.items():
                        if isinstance(data, dict):
                            char_lines.append(f"- {name}：{data.get('description', '')}")
                        else:
                            char_lines.append(f"- {name}：{data}")
                    char_text = "\n\n【已有角色设定】\n" + "\n".join(char_lines)
        except Exception as e:
            logger.warning("读取角色设定失败: %s", e)

        world_part = f"\n\n【世界观设定】\n{world_text}" if world_text else ""
        char_part = char_text if char_text else ""
        inspiration_part = ""
        if inspiration:
            safe_inspiration = sanitize_user_input(inspiration)
            inspiration_part = f"\n\n【作者灵感碎片 — 大纲必须围绕此核心思路展开】\n{safe_inspiration}\n\n请将以上灵感碎片作为全书大纲的核心骨架，在此基础上补充和完善。"

        prompt = f"""为{genre or ''}小说《{title}》生成全书大纲，约{length}章完结。
{vol_context if vol_context else ''}
{world_part}{freeform_world}{char_part}{inspiration_part}

要求：
- 全书大纲是概括性、方向性的，不要分章节，不要列出每章内容
- 以{length}章为基准的整体故事走向
- 必须有明确的结局走向指引
- 【最高优先级】如果已有世界观和角色设定，大纲必须严格基于这些设定生成
  - 必须使用世界观中完全相同的角色名、地名、力量体系名称
  - 禁止引入世界观中不存在的概念、角色或设定
  - 故事背景、社会结构、核心矛盾必须与世界观一致

类型指南：{genre}

输出格式（必须是以下8个章节，严格按格式输出）：

## 主题
（一句话概括全书在讲什么，15-30字）

## 核心冲突
（明线冲突 + 暗线冲突，2-3句话。明线是表层故事矛盾，暗线是深层主题冲突）

## 故事走向
（起承转合的时间线叙述，150-300字。从开局到结局的完整脉络，不要分章节，用叙述性文字写）

## 世界观锚点
（核心世界观要素：世界结构、力量体系、关键势力、特殊设定。已提供的就引用，不要重复展开）

## 主要角色弧光
（3-5个主要角色的弧光，每个角色一行：角色名 | 从X到Y的转变）

## 关键伏笔
（3-5个关键伏笔，每个一行：伏笔内容 | 何时埋下 | 何时揭示）

## 长线悬念
（贯穿全书的终极疑问，1-2句话。从第1章埋下种子，到结局才揭晓。例：力场泡泡从何而来？远古遗留还是人类进化产物？会不会存在"泡泡吞噬持有者"的风险？此悬念不宜在中期完全解答，要分散为小线索穿插在各卷——如果能的话，暗示在第几卷给出部分线索、第几章揭示真相。不要一次性抛出。）

## 社会图景
（普通人视角的社会规则，2-3句话。包括：普通人如何看待超凡力量？是崇拜、恐惧、管控还是猎杀？官方有无监管法案？是否存在围绕力量体系的黑市交易或地下组织？普通人的日常生活如何被力量体系影响？——这部分不属于世界观"设定"，而是这些设定在普通人生活中产生的涟漪。）

## 结局指引
（故事以什么方式收尾，1-2句话。不要写具体结局细节，只给方向）

## 基调
（1-2个词，如：热血、沉重、诙谐、悲壮）

禁止：分章节列出"第X章·章名"这种章节级描述。全书大纲是方向性指引，不是章节目录。"""
        raw_text = self.ai.generate(prompt)
        return self._parse_novel_outline(raw_text, volume_index is not None)

    def _parse_novel_outline(self, raw_text: str, is_volume: bool = False) -> Dict[str, Any]:
        """解析AI生成的全书大纲Markdown文本为结构化dict

        Args:
            raw_text: AI返回的原始Markdown文本
            is_volume: 是否为卷纲要（True时返回卷纲要格式，False时返回全书大纲格式）

        Returns:
            结构化的dict
        """
        import re
        text = raw_text.strip()

        # 移除代码块标记（如果有）
        text = re.sub(r'^```(?:json|markdown)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

        result = {
            'theme': '',
            'core_conflict': '',
            'story_arc': '',
            'world_anchor': '',
            'character_arcs': [],
            'key_hooks': [],
            'long_suspense': '',
            'social_picture': '',
            'ending': '',
            'tone': ''
        }

        current_section = None
        section_lines = []

        def flush_section():
            nonlocal current_section, section_lines
            if not current_section or not section_lines:
                return
            content = '\n'.join(section_lines).strip()
            if current_section == 'theme':
                result['theme'] = content
            elif current_section == 'core_conflict':
                result['core_conflict'] = content
            elif current_section == 'story_arc':
                result['story_arc'] = content
            elif current_section == 'world_anchor':
                result['world_anchor'] = content
            elif current_section == 'ending':
                result['ending'] = content
            elif current_section == 'tone':
                result['tone'] = content
            elif current_section == 'long_suspense':
                result['long_suspense'] = content
            elif current_section == 'social_picture':
                result['social_picture'] = content
            elif current_section == 'character_arcs':
                arcs = []
                for line in section_lines:
                    line = line.strip()
                    if line:
                        if '|' in line:
                            parts = [p.strip() for p in line.split('|', 1)]
                            arcs.append({'character': parts[0], 'arc': parts[1] if len(parts) > 1 else ''})
                        elif line.startswith('- '):
                            arc_text = line[2:].strip()
                            if '|' in arc_text:
                                parts = [p.strip() for p in arc_text.split('|', 1)]
                                arcs.append({'character': parts[0], 'arc': parts[1] if len(parts) > 1 else ''})
                            else:
                                arcs.append({'character': '', 'arc': arc_text})
                        else:
                            arcs.append({'character': '', 'arc': line})
                result['character_arcs'] = arcs
            elif current_section == 'key_hooks':
                hooks = []
                for line in section_lines:
                    line = line.strip()
                    if line:
                        if line.startswith('- '):
                            hooks.append(line[2:].strip())
                        else:
                            hooks.append(line)
                result['key_hooks'] = hooks
            section_lines = []

        for line in text.split('\n'):
            stripped = line.strip()
            heading_match = re.match(r'^#+\s*(.+?)\s*$', stripped)
            if heading_match:
                flush_section()
                heading = heading_match.group(1).strip()
                if '主题' in heading:
                    current_section = 'theme'
                elif '核心冲突' in heading:
                    current_section = 'core_conflict'
                elif '故事走向' in heading or '完整故事弧线' in heading or '故事线' in heading:
                    current_section = 'story_arc'
                elif '世界观锚点' in heading or '世界观' in heading:
                    current_section = 'world_anchor'
                elif '角色弧光' in heading or '人物弧光' in heading:
                    current_section = 'character_arcs'
                elif '关键伏笔' in heading or '伏笔' in heading:
                    current_section = 'key_hooks'
                elif '结局指引' in heading or '结局' in heading:
                    current_section = 'ending'
                elif '基调' in heading or '风格' in heading:
                    current_section = 'tone'
                elif '长线悬念' in heading or '悬念' in heading:
                    current_section = 'long_suspense'
                elif '社会图景' in heading or '社会' in heading:
                    current_section = 'social_picture'
                else:
                    current_section = None
            elif current_section:
                section_lines.append(line)

        flush_section()

        # 如果是卷纲要，转换为卷纲要格式
        if is_volume:
            vol_result = {
                'theme': result.get('theme', ''),
                'summary': result.get('story_arc', ''),
                'key_events': result.get('key_hooks', []),
                'character_arcs': result.get('character_arcs', [])
            }
            return vol_result

        return result

    def generate_chapter_outline(self, title: str, context: str = "", chapter_index: int = 0) -> Dict[str, Any]:
        """生成章节大纲 - 返回结构化蓝图 + 原始文本
        Returns:
            {
                "raw": str,          # AI原始返回文本
                "blueprint": dict,   # 解析后的结构化蓝图（失败时为None）
                "outline_text": str  # 从蓝图提取的纯文本大纲（用于兼容旧存储）
            }
        """
        # 用户输入清洗：title/context 可能包含用户自定义内容
        title = sanitize_light(title) if title else title
        context = sanitize_light(context) if context else context
        # P0: 始终注入全书大纲的概括性方向（新格式 dict）
        act_text = ""
        try:
            proj = self.project
            if proj:
                novel_outline = proj.novel_outline or {}
                if isinstance(novel_outline, dict) and novel_outline:
                    # 新格式：注入概括性方向
                    parts = []
                    if novel_outline.get('theme'):
                        parts.append(f"- 主题：{novel_outline['theme']}")
                    if novel_outline.get('core_conflict'):
                        parts.append(f"- 核心冲突：{novel_outline['core_conflict']}")
                    if novel_outline.get('story_arc'):
                        parts.append(f"- 故事走向：{novel_outline['story_arc']}")
                    if novel_outline.get('ending'):
                        parts.append(f"- 结局指引：{novel_outline['ending']}")
                    if novel_outline.get('tone'):
                        parts.append(f"- 基调：{novel_outline['tone']}")
                    if novel_outline.get('character_arcs'):
                        arc_lines = []
                        for arc in novel_outline['character_arcs'][:5]:
                            if isinstance(arc, dict):
                                arc_lines.append(f"  · {arc.get('character','')}: {arc.get('arc','')}")
                        if arc_lines:
                            parts.append("- 角色弧光：")
                            parts.extend(arc_lines)
                    if novel_outline.get('key_hooks'):
                        parts.append("- 关键伏笔：")
                        for h in novel_outline['key_hooks'][:5]:
                            if isinstance(h, str):
                                parts.append(f"  · {h}")
                    if parts:
                        act_text = "## 全书大纲（方向性指引）\n" + "\n".join(parts) + "\n"
                elif isinstance(novel_outline, list) and novel_outline:
                    # 旧格式 list：只取幕标题作为参考（兼容）
                    parts = []
                    for act in novel_outline:
                        if isinstance(act, dict):
                            parts.append(f"- {act.get('title', '')}")
                    if parts:
                        act_text = "## 全书大纲（旧格式，仅幕标题）\n" + "\n".join(parts) + "\n"
        except Exception as e:
            logger.warning("读取全书大纲失败: %s", e)

        # 4.3 注入当前卷纲要上下文
        vol_text = ""
        try:
            volumes = getattr(proj, 'volumes', None) or [] if proj else []
            if volumes:
                ch_num = chapter_index + 1
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
                        key_events = vol_outline.get('key_events', [])
                        if summary or theme or key_events:
                            vol_parts = [f"## 当前卷纲要：{cur_vol.get('title', '')}"]
                            if summary:
                                vol_parts.append(f"卷概要：{summary}")
                            if theme:
                                vol_parts.append(f"卷主题：{theme}")
                            if key_events:
                                vol_parts.append("卷关键事件：")
                                for ke in key_events:
                                    vol_parts.append(f"  · {ke}")
                            vol_text = "\n".join(vol_parts) + "\n"
        except Exception as e:
            logger.warning("读取卷纲要失败: %s", e)

        # 如果前端没传context，自动构建世界观+角色+前文摘要
        if not context or len(context) < 50:
            ctx_parts = []
            # 世界观设定
            world_text = self.world.to_prompt()
            if world_text:
                ctx_parts.append(world_text)
            # 角色档案
            char_text = self._build_character_context(chapter_index, title)
            if char_text:
                ctx_parts.append(f"## 本小说的主要人物\n{char_text}")
            # 前一章大纲摘要（避免重复）
            if self.project and chapter_index > 0:
                prev_ch = self.project.chapters[chapter_index - 1] if chapter_index - 1 < len(self.project.chapters) else None
                if prev_ch:
                    prev_outline = prev_ch.get("outline", "")
                    if prev_outline and len(prev_outline) > 50:
                        ctx_parts.append(f"## 前一章大纲（避免重复）\n{prev_outline[:500]}")
            # 蒸馏记忆（如果有的话）- 从 state_memory 聚合，无硬字符上限
            try:
                # chapter_index 是 0-based，转 1-based 传给合成器
                distilled = synthesize_memory_context(self.project_dir, chapter_index + 1)
                if distilled and len(distilled) > 100:
                    ctx_parts.append(f"## 已有剧情摘要（蒸馏记忆）\n{distilled}")
            except Exception as e:
                logger.warning("合成蒸馏记忆失败: %s", e)
            # 灵感碎片（头脑风暴卡片）
            try:
                if self.project and self.project.brainstorm_cards:
                    cards = self.project.brainstorm_cards[:10]
                    if cards:
                        cards_text = "\n".join([f"- [{c.get('impact','medium')}] {c.get('title','')}: {c.get('desc','')}" for c in cards])
                        if cards_text:
                            ctx_parts.append(f"## 灵感碎片（必须融入本章大纲）\n{cards_text}")
            except Exception as e:
                logger.warning("读取灵感碎片失败: %s", e)
            context = "\n\n".join(ctx_parts)

        # 将卷纲要和当前幕事件强制前置到context最前面（最高优先级）
        if vol_text:
            context = vol_text + "\n" + context
        if act_text:
            context = act_text + "\n\n【强制约束】本章大纲必须严格基于上方\"当前幕\"中的事件来规划。上方列出的当前幕事件是本章必须完成的核心剧情主线，不得偏离、不得跳过、不得自行编造其他幕的剧情。\n\n" + context

        prompt = f"""为章节《{title}》生成详细大纲。这是第{chapter_index + 1}章的专属大纲，内容必须与其他章节不同。

{context}

【核心约束 - 必须遵守】
1. **最高优先级：严格基于上方"当前幕"中的事件来规划本章剧情**。当前幕事件是本章必须完成的核心主线，不得偏离或自行编造其他剧情
2. 严格使用上方"小说设定"中的世界观和力量体系，禁止引入任何设定中不存在的概念（如量子物理、墨丘利、跨维度通道等）
3. 严格使用上方"主要人物"和"人物档案"中的角色名和身份，禁止创造新角色或使用其他故事的角色名
4. 场景必须发生在设定描述的世界中，禁止出现与设定无关的地点
5. 如果有前一章内容，必须自然衔接，不要重复前一章的场景和事件
6. 每章的开场场景、触发事件、关键转折都必须不同
7. 如果上方提供了"灵感碎片"，必须将其中适合本章的灵感融入大纲情节中（作为关键事件、转折点或人物动机）

请返回以下JSON格式（放在 ```json 代码块中），然后附上可读说明：

```json
{{
  "title": "{title}",
  "plot_line": ["主线"],
  "intro": {{
    "scene": "场景描述",
    "atmosphere": "氛围",
    "trigger": "触发事件",
    "word_count": 500
  }},
  "development": [
    {{
      "scene": "场景1",
      "location": "地点",
      "characters": ["角色名"],
      "event": "关键事件",
      "choice": "角色选择",
      "cost": "代价",
      "info_reveal": "信息释放"
    }}
  ],
  "climax": {{
    "conflict": "冲突最大化描述",
    "key_choice": "关键选择",
    "cost": "代价",
    "twist": "转折点"
  }},
  "ending": {{
    "new_state": "新状态",
    "info_reveal": "信息揭露",
    "next_hook": "下一章钩子"
  }},
  "word_target": 3000
}}
```

禁止词汇：{', '.join(FORBIDDEN_WORDS[:8])}

要求：
1. 每个场景必须有具体事件，不要概述
2. 角色选择必须有代价
3. 信息释放要服务于总纲
4. plot_line标注本章所属剧情线（主线/支线A/支线B等），一章可属多条线"""
        raw = self.ai.generate(prompt, max_tokens=8192)

        # 从AI返回中提取JSON代码块
        blueprint = None
        json_str = None
        # 先尝试闭合的代码块
        m = re.search(r'```json\s*\n(.*?)\n```', raw, re.DOTALL)
        if m:
            json_str = m.group(1)
        else:
            # 尝试未闭合的代码块（AI返回被截断时）
            m = re.search(r'```json\s*\n([\s\S]+)', raw)
            if m:
                json_str = m.group(1).rstrip('`').rstrip()
            else:
                # 尝试匹配没有代码块的裸JSON
                m = re.search(r'\{[^{}]*"intro".*?\}', raw, re.DOTALL)
                if m:
                    json_str = m.group(0)

        if json_str:
            try:
                blueprint = json.loads(json_str)
            except (json.JSONDecodeError, IndexError):
                # JSON解析失败，尝试更宽松的匹配
                try:
                    # 找第一个{到最后一个}
                    start = raw.find('{')
                    end = raw.rfind('}')
                    if start != -1 and end != -1 and end > start:
                        blueprint = json.loads(raw[start:end+1])
                except json.JSONDecodeError:
                    blueprint = None

        # 如果JSON完全解析失败，尝试从截断文本中正则提取部分结构
        if not blueprint:
            blueprint = self._extract_partial_blueprint(raw)

        # 过滤空/无效 blueprint：至少要有 intro.scene 才算有效
        if blueprint and not blueprint.get("intro", {}).get("scene"):
            logger.debug("第%d章生成的 blueprint 缺少 intro.scene，视为无效", chapter_index + 1)
            blueprint = None

        # 从蓝图提取纯文本大纲（兼容旧前端存储）
        outline_text = ""
        if blueprint:
            parts = []
            intro = blueprint.get("intro", {})
            if intro and intro.get("scene"):
                parts.append(f"【起】{intro.get('scene','')} — {intro.get('trigger','')}")
            for dev in blueprint.get("development", []):
                scene = dev.get("scene", "")
                event = dev.get("event", "")
                if scene and event:
                    parts.append(f"【承】{scene}：{event}")
                elif scene:
                    parts.append(f"【承】{scene}")
            climax = blueprint.get("climax", {})
            if climax and climax.get("conflict"):
                parts.append(f"【转】{climax.get('conflict','')} — {climax.get('twist','')}")
            ending = blueprint.get("ending", {})
            if ending and ending.get("new_state"):
                parts.append(f"【合】{ending.get('new_state','')} → {ending.get('next_hook','')}")
            outline_text = "\n".join(parts)
            # 如果提取的文本太短（<100字），说明蓝图不完整，用raw作为fallback
            if len(outline_text) < 100 and raw:
                outline_text = raw.strip()[:2000]

        return {
            "raw": raw,
            "blueprint": blueprint,
            "outline_text": outline_text
        }

    def _extract_partial_blueprint(self, raw: str) -> Optional[Dict]:
        """当JSON解析失败（截断/格式错误）时，从原始文本中正则提取部分蓝图结构"""
        bp = {}
        # 提取intro
        m_intro = re.search(r'"intro"\s*:\s*\{([^}]*)\}', raw, re.DOTALL)
        if m_intro:
            intro_str = m_intro.group(0)
            try:
                bp["intro"] = json.loads(intro_str)
            except Exception as e:
                logger.debug("解析intro JSON失败，使用正则提取: %s", e)
                bp["intro"] = {}
                for key in ["scene", "atmosphere", "trigger", "word_count"]:
                    m = re.search(rf'"{key}"\s*:\s*"([^"]*)"', intro_str)
                    if m:
                        bp["intro"][key] = m.group(1)
        # 提取development数组（可能截断，提取完整的项）
        dev_items = re.findall(r'"scene"\s*:\s*"([^"]{5,500})"', raw)
        if dev_items:
            bp["development"] = [{"scene": s} for s in dev_items[:5]]
        # 提取climax
        m_climax = re.search(r'"climax"\s*:\s*\{([^}]*)\}', raw, re.DOTALL)
        if m_climax:
            climax_str = m_climax.group(0)
            try:
                bp["climax"] = json.loads(climax_str)
            except Exception as e:
                logger.debug("解析climax JSON失败，使用正则提取: %s", e)
                bp["climax"] = {}
                for key in ["conflict", "key_choice", "cost", "twist"]:
                    m = re.search(rf'"{key}"\s*:\s*"([^"]{5,500})"', climax_str)
                    if m:
                        bp["climax"][key] = m.group(1)
        # 提取ending
        m_ending = re.search(r'"ending"\s*:\s*\{([^}]*)\}', raw, re.DOTALL)
        if m_ending:
            ending_str = m_ending.group(0)
            try:
                bp["ending"] = json.loads(ending_str)
            except Exception as e:
                logger.debug("解析ending JSON失败，使用正则提取: %s", e)
                bp["ending"] = {}
                for key in ["new_state", "info_reveal", "next_hook"]:
                    m = re.search(rf'"{key}"\s*:\s*"([^"]{5,500})"', ending_str)
                    if m:
                        bp["ending"][key] = m.group(1)
        # 提取title
        m_title = re.search(r'"title"\s*:\s*"([^"]{2,100})"', raw)
        if m_title:
            bp["title"] = m_title.group(1)
        # 至少有intro才算有效
        return bp if bp else None

    def extract_state(self, content: str, chapter_idx: int) -> dict:
        """从章节正文提取结构化状态变更"""
        prompt = f"""分析以下小说章节，提取结构化信息。只返回JSON，不要解释。

{content[:4000]}

JSON格式：
{{
  "foreshadowing": [{{"content": "伏笔描述", "expected_recovery": 预计回收章号(数字)}}],
  "character_changes": {{"角色名": {{"field": "new_value"}}}},
  "new_items": [{{"name": "物品名", "nature": "性质", "owner": "持有人"}}]
}}

字段说明：
- foreshadowing: 疑似伏笔（未解答对话/奇怪物件/灵异预兆/异常能力）
- character_changes: 角色状态变化（health/emotion/realm/location/possessions）
- new_items: 新出现的重要物品"""
        result = self.ai.generate(prompt)

        # Parse JSON from result
        try:
            import json
            # Strip markdown code fences
            clean = result.replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
        except Exception:
            pass

    def run_project_level_analysis(self) -> dict:
        """全书级分析：大纲质量(10维) + 世界观质量(10维) + 人物质量(10维) = 30维
        在项目完本或用户手动触发时调用，不接入每章生成流程。"""
        from backend.routers.validate import (
            _do_validate_outline_quality, OutlineQualityRequest,
            _do_validate_settings_quality, SettingsQualityRequest,
            _do_validate_characters_quality, CharactersQualityRequest,
        )

        results = {}

        # 1. 大纲质量（10维）
        try:
            outline_result = _do_validate_outline_quality(OutlineQualityRequest())
            results["outline_quality"] = outline_result
            logger.info("[全书分析] 大纲质量检查完成")
        except Exception as e:
            logger.warning(f"[全书分析] 大纲质量检查失败: {e}")
            results["outline_quality"] = {"error": str(e)}

        # 2. 世界观质量（10维）
        try:
            settings_result = _do_validate_settings_quality(SettingsQualityRequest())
            results["settings_quality"] = settings_result
            logger.info("[全书分析] 世界观质量检查完成")
        except Exception as e:
            logger.warning(f"[全书分析] 世界观质量检查失败: {e}")
            results["settings_quality"] = {"error": str(e)}

        # 3. 人物质量（10维）
        try:
            characters_result = _do_validate_characters_quality(CharactersQualityRequest())
            results["characters_quality"] = characters_result
            logger.info("[全书分析] 人物质量检查完成")
        except Exception as e:
            logger.warning(f"[全书分析] 人物质量检查失败: {e}")
            results["characters_quality"] = {"error": str(e)}

    def apply_state_extraction(self, content: str, chapter_idx: int, chapter_title: str, validation_issues: list = None):
        """提取状态并写入 Truth Ledger。validation_issues: 检查结果，用于辅助判断是否应写入异常状态"""
        data = self.extract_state(content, chapter_idx)

        # 如果检查发现了角色一致性严重问题（如死亡复活），标记到ledger警告
        if validation_issues:
            char_warnings = []
            for issue in validation_issues:
                issue_str = str(issue)
                if any(kw in issue_str for kw in ("死亡", "复活", "前后矛盾", "不一致", "崩塌")):
                    char_warnings.append(issue_str)
            if char_warnings:
                self.ledger.add_validation_warning(chapter_idx, chapter_title, char_warnings)

        # Apply character changes
        for name, changes in data.get("character_changes", {}).items():
            self.ledger.update_character(name, **changes, chapter=chapter_idx)

        # Apply foreshadowing
        new_hook_ids = []
        for hook in data.get("foreshadowing", []):
            hid = self.ledger.add_hook(hook["content"], chapter_idx,
                expected_recovery_chapter=hook.get("expected_recovery", 0))
            new_hook_ids.append(hid)

        # Apply new items to character possessions
        for item in data.get("new_items", []):
            owner = item.get("owner", "")
            if owner:
                self.ledger.ensure_character(owner)
                cs = self.ledger.character_states[owner]
                # 确保possessions是list（修复旧数据可能是字符串的问题）
                if isinstance(cs.possessions, str):
                    cs.possessions = [cs.possessions] if cs.possessions else []
                cs.possessions.append(item.get("name", ""))
                self.ledger.save()

        # Log chapter
        self.ledger.log_chapter(chapter_idx, chapter_title,
            new_foreshadowing=new_hook_ids,
            character_changes=data.get("character_changes", {}))

        # 5.2 生成章节摘要并存入 project.json
        try:
            summary = self.generate_chapter_summary(content, chapter_idx, chapter_title)
            if summary and self.project:
                if chapter_idx < len(self.project.chapters):
                    self.project.chapters[chapter_idx]["summary"] = summary
                    self.project.save_all()
        except Exception as e:
            logger.warning("保存章节摘要失败: %s", e)

