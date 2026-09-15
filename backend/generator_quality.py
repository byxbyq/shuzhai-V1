# -*- coding: utf-8 -*-
"""ChapterGenerator 质量检查与修复方法（从 generator.py 拆分）"""
import logging
from typing import Optional, List, Dict

from backend.constants import FORBIDDEN_WORDS
from backend.post_process_rules import (
    DE_DENSITY_TARGET, CONNECTOR_REPLACEMENTS, AI_WORDS_LIMIT, AI_WORDS_SYNONYMS,
    DE_REPLACEMENTS,
)
from backend.services.guard_pipeline import (
    GuardPipeline, GuardSeverity, create_default_pipeline,
)

logger = logging.getLogger(__name__)

# GuardSeverity → 业务 severity 映射
_GUARD_SEVERITY_MAP = {
    GuardSeverity.BLOCK: "high",
    GuardSeverity.WARN: "medium",
    GuardSeverity.INFO: "low",
}


class ChapterQualityMixin:
    """提供章节内容质量检查、修复与后处理"""

    _guard_pipeline: Optional[GuardPipeline] = None

    @classmethod
    def _get_guard_pipeline(cls) -> GuardPipeline:
        """惰性初始化 GuardPipeline 单例"""
        if cls._guard_pipeline is None:
            cls._guard_pipeline = create_default_pipeline()
        return cls._guard_pipeline

    def _detect_chapter_type(self, title: str, outline: str) -> str:
        """智能判断章节类型，用于自适应温度
        返回值: battle/climax/emotion/daily/transition/setup/mystery
        """
        text = (title or "") + " " + (outline or "")
        battle_keywords = ["战", "打", "杀", "斗", "决战", "交锋", "出手", "激战", "碾压", "反杀",
                           "突破", "渡劫", "出手", "底牌", "拼命", "搏杀", "血战", "围攻"]
        climax_keywords = ["转折", "反转", "真相", "揭秘", "高潮", "爆发", "摊牌", "决裂", "觉醒",
                           "晋级", "突破", "飞升", "质变", "颠覆"]
        emotion_keywords = ["哭", "泪", "感动", "心痛", "难过", "悲伤", "告白", "误会", "和解",
                            "生离死别", "牺牲", "诀别", "不舍", "拥抱"]
        daily_keywords = ["日常", "休息", "修炼", "修行", "出发", "赶路", "闲聊", "吃饭", "逛街",
                          "购物", "整理", "准备", "训练", "学习", "研究"]
        mystery_keywords = ["谜", "疑", "真相", "线索", "发现", "察觉", "探", "查", "追查", "秘密", "暗中"]

        scores = {"battle": 0, "climax": 0, "emotion": 0, "daily": 0,
                  "transition": 0, "setup": 0, "mystery": 0}
        for kw in battle_keywords:
            if kw in text: scores["battle"] += 1
        for kw in climax_keywords:
            if kw in text: scores["climax"] += 1
        for kw in emotion_keywords:
            if kw in text: scores["emotion"] += 1
        for kw in daily_keywords:
            if kw in text: scores["daily"] += 1
        for kw in mystery_keywords:
            if kw in text: scores["mystery"] += 1

        best = max(scores, key=scores.get)
        # 如果没有匹配到任何关键词，默认返回 transition
        if scores[best] == 0:
            return "transition"
        return best

    REVIEW_DIMENSION_REPAIR_MAP = {
        "人物塑造力": {
            "instruction": "加强人物塑造：增加角色的微表情、小动作、口头禅、思维活动，让角色像真人一样有温度。每个重要角色至少加2处体现个性的细节描写。",
            "temperature_delta": 0.05
        },
        "情感穿透力": {
            "instruction": "加强情感浓度：不要直白说「他很悲伤」，要通过生理反应（手抖、喉咙发紧、胸口闷、视线模糊）、环境烘托、细节暗示来传递情绪。至少3处用细节表达情绪的句子。",
            "temperature_delta": 0.08
        },
        "情节反转密度": {
            "instruction": "增加情节起伏：在发展段加一个小反转或意外，在高潮段加一个更有冲击力的转折。不要平铺直叙，要让读者猜不到下一步。",
            "temperature_delta": 0.1
        },
        "主题深度": {
            "instruction": "深化主题：通过角色的选择和困境，暗合主题思想。不要说教，让读者从故事中自己体会。加1-2处体现主题的细节或对话。",
            "temperature_delta": 0.0
        },
        "文体魅力": {
            "instruction": "提升文字质感：长短句交错更有节奏，增加感官细节（视觉/听觉/嗅觉/触觉），减少连接词和套话，让文字更有画面感和冲击力。",
            "temperature_delta": 0.05
        },
        "爽点密度": {
            "instruction": "增加爽点密度：每1000字至少要有一个小爽点（打脸/装X/收获/突破/反转）。爽点之前要有压抑铺垫，压得越低弹得越高。结尾留一个强钩子让读者想看下一章。",
            "temperature_delta": 0.08
        },
    }

    def _review_driven_repair(self, content: str, title: str, outline: str, assessment: dict,
                              chapter_index: int, skill_rules: str = "",
                              use_distilled_memory: bool = True) -> Optional[dict]:
        """基于审稿评分的定向修复闭环
        找出评分≤2分的维度，生成针对性润色指令，让AI重写整章
        最多修复1轮，最多同时修2个维度（避免改得面目全非）
        """
        review = assessment.get("editorial_review", {})
        if not review or not review.get("dimensions"):
            return None

        # 找出低分维度（≤2分）
        low_dims = []
        for dim in review["dimensions"]:
            score = dim.get("score", 5)
            if score <= 2:
                low_dims.append(dim)

        if not low_dims:
            return None

        # 最多同时修2个维度（取分数最低的2个）
        low_dims.sort(key=lambda d: d.get("score", 5))
        low_dims = low_dims[:2]

        dim_names = [d["name"] for d in low_dims]
        before_scores = {d["name"]: d["score"] for d in low_dims}

        logger.info(
            f"[审稿修复] 第{chapter_index + 1}章低分维度: {', '.join(dim_names)} "
            f"({', '.join(f'{k}={v}分' for k, v in before_scores.items())})，启动定向修复"
        )

        # 构建修复指令
        repair_instructions = []
        total_temp_delta = 0.0
        for dim in low_dims:
            name = dim.get("name", "")
            repair_info = self.REVIEW_DIMENSION_REPAIR_MAP.get(name, {})
            if repair_info.get("instruction"):
                repair_instructions.append(repair_info["instruction"])
                total_temp_delta += repair_info.get("temperature_delta", 0)

        if not repair_instructions:
            return None

        # 基础 temperature = 当前章节类型的温度 + 修复加成
        chapter_type = self._detect_chapter_type(title, outline)
        base_temp = self._get_adaptive_temperature(chapter_type, 1)
        repair_temp = round(min(0.95, base_temp + total_temp_delta), 2)

        # 构建润色 prompt（在原文基础上改，不改变剧情走向）
        repair_prompt = f"""你是顶尖网文编辑兼金牌写手。下面是一章节小说，请你基于审稿意见进行定向润色和加强。

## 核心要求（必须严格遵守）
1. **剧情大纲绝对不能改**：人物、事件、走向、结局全部保持原样，只加强表达和细节
2. **只加强，不删减**：在现有内容基础上增加细节、情绪、画面感，不要删改已有情节
3. **保持原有风格**：不要改变作者的文风，只是在其基础上提升
4. **字数变化控制在±20%以内**

## 需要重点加强的维度
{chr(10).join(f'{i+1}. {inst}' for i, inst in enumerate(repair_instructions))}

## 原文
{content}

## 章节大纲（确保不偏离）
{outline}

请输出润色加强后的完整章节正文。不要输出任何解释、说明、标记。直接给正文。"""

        # 调用 AI 润色
        try:
            repaired = self.ai.generate_for_task(
                repair_prompt, task_type="writing",
                max_tokens=12288,
                temperature=repair_temp
            )
        except Exception as e:
            logger.warning(f"[审稿修复] AI调用失败: {e}")
            return None

        # 简单校验：内容不能太短
        if not repaired or len(repaired) < len(content) * 0.6:
            logger.warning("[审稿修复] 修复后内容过短，放弃")
            return None

        # 后处理
        repaired = self._post_process(repaired)

        # 复评：跑一次审稿看有没有提升
        after_scores = {}
        try:
            from backend.routers.validate import _do_editorial_review
            after_review = _do_editorial_review(repaired, mode="reader_focus")
            if after_review.get("ok"):
                for dim in after_review.get("dimensions", []):
                    if dim.get("name") in dim_names:
                        after_scores[dim["name"]] = dim["score"]
        except Exception as e:
            logger.warning(f"[审稿修复] 复评失败: {e}")

        # 判断是否有提升（至少有一个维度分数上升，且没有维度下降）
        improved = False
        if after_scores:
            any_up = any(after_scores.get(k, 0) > before_scores.get(k, 0) for k in dim_names)
            none_down = all(after_scores.get(k, 0) >= before_scores.get(k, 0) - 1 for k in dim_names)
            improved = any_up and none_down

        if not improved and after_scores:
            # 如果没有提升甚至下降了，放弃修复
            logger.info(
                f"[审稿修复] 复评无提升（前: {before_scores}, 后: {after_scores}），保留原文"
            )
            return {"repaired": False, "before_scores": before_scores, "after_scores": after_scores}

        logger.info(
            f"[审稿修复] 完成! 修复维度: {dim_names}, "
            f"前: {before_scores}, 后: {after_scores or '未复评'}"
        )

        return {
            "repaired": True,
            "content": repaired,
            "fixed_dimensions": dim_names,
            "before_scores": before_scores,
            "after_scores": after_scores,
            "repair_summary": {
                "dimensions": dim_names,
                "before": before_scores,
                "after": after_scores,
                "temperature": repair_temp,
            }
        }

    def _post_process(self, content: str) -> str:
        """后处理：削减AI味特征"""
        import re as _re

        # 0. 去掉开头的章节标题（AI经常错误输出"# 第X章"或"第X章"）
        # 匹配独立行：第3章\n 或 # 第3章 标题文字\n
        # 不匹配标题和正文同行的情况（如"第3章正文内容"→只删"第3章"，保留正文）
        content = _re.sub(r'^([#\s]*)第\d+章[：:]*[^\n]*\n+', '', content)
        content = _re.sub(r'^([#\s]*)Chapter\s*\d+[：:]*[^\n]*\n+', '', content, flags=_re.IGNORECASE)
        # 处理标题和正文在同一行的情况：第3章正文内容 → 正文内容
        content = _re.sub(r'^第\d+章[：:]*', '', content)
        content = _re.sub(r'^Chapter\s*\d+[：:]*', '', content, flags=_re.IGNORECASE)
        content = content.lstrip('\n').lstrip()

        # 1. 削减"的"字密度：目标 < DE_DENSITY_TARGET/千字
        char_count = len(content)
        de_count = content.count('的')
        de_density = de_count / (char_count / 1000) if char_count > 0 else 0
        if de_density > DE_DENSITY_TARGET:
            # 需要替换的数量
            excess = int(de_count - DE_DENSITY_TARGET * (char_count / 1000))
            replaced = 0
            for old, new in DE_REPLACEMENTS:
                while old in content and replaced < excess:
                    content = content.replace(old, new, 1)
                    replaced += 1
            # 如果还不够，删掉一些"的"：XX的XX → XX之XX（文言替换）
            if replaced < excess:
                # 找到剩余"的"，每隔2个替换1个为"之"
                de_positions = [m.start() for m in _re.finditer('的', content)]
                for i, pos in enumerate(de_positions):
                    if i % 3 == 0 and replaced < excess:
                        # 检查前后字符，避免产生不通顺的"之"
                        before = content[pos-1] if pos > 0 else ''
                        after = content[pos+1] if pos+1 < len(content) else ''
                        if before and after and '\u4e00' <= before <= '\u9fa5' and '\u4e00' <= after <= '\u9fa5':
                            content = content[:pos] + '之' + content[pos+1:]
                            replaced += 1

        # 2. 削减连接词
        for old, new in CONNECTOR_REPLACEMENTS.items():
            content = content.replace(old, new)

        # 3. 削减"突然""忽然"等高频AI词
        for word, limit in AI_WORDS_LIMIT.items():
            count = content.count(word)
            if count > limit:
                # 替换多余的部分
                syns = AI_WORDS_SYNONYMS.get(word, [''])
                idx = 0
                for i in range(limit, count):
                    pos = content.find(word, content.find(word) + 1 if i > 0 else 0)
                    if pos >= 0:
                        syn = syns[idx % len(syns)]
                        content = content[:pos] + syn + content[pos+len(word):]
                        idx += 1

        # 4. 清理连续空行
        content = _re.sub(r'\n{3,}', '\n\n', content)

        # 5. 结构扰动清洗：破坏统计均匀性（纯规则零Token，针对外部ML检测器）
        try:
            from backend.services.text_perturb import perturb_text
            content = perturb_text(content)
        except Exception as _pe:
            print(f"[结构扰动] 跳过: {_pe}")

        # 6. 降熵评分日志
        from backend.services.audit import detect_ai_flavor, compute_ai_score
        quick_ai = detect_ai_flavor(content)
        score_info = compute_ai_score(quick_ai)
        print(f"[降熵评分] 后处理完成: ai_score={score_info['ai_score']}, ai_level={score_info['ai_level']}")

        return content
    def _run_hard_checks(self, content: str, title: str, outline: str, chapter_index: int = 0) -> List[Dict]:
        """跑硬校验 + 扩展审计（纯规则，不消耗Token），返回结构化问题列表
        每个问题格式: {type, description, severity, locations: [{line, offset, matched, context}]}
        """
        from backend.services.audit import _find_word_positions

        issues = []

        # 1. 禁词检查
        found_words = [w for w in FORBIDDEN_WORDS if w in content]
        if found_words:
            all_locs = []
            for w in found_words:
                all_locs.extend(_find_word_positions(content, w))
            issues.append({
                'type': 'forbidden_words',
                'description': f"使用了禁用词汇: {', '.join(found_words)}",
                'severity': 'high',
                'locations': all_locs
            })

        # 2. 长度检查
        if len(content) < 500:
            issues.append({
                'type': 'too_short',
                'description': "内容过短，不足500字",
                'severity': 'high',
                'locations': []
            })

        # 3. 大纲覆盖硬校验：检查大纲中提到的项目人物是否出现在正文中
        outline_names = []
        try:
            _proj = self.project
            if _proj:
                chars = getattr(_proj, 'characters', []) or []
                outline_names = [c['name'] for c in chars if c.get('name') and c['name'] in outline]
        except Exception as e:
            logger.warning("获取大纲角色名失败: %s", e)
        if outline_names:
            missing = [n for n in outline_names if n not in content]
            if missing:
                issues.append({
                    'type': 'outline_deviation',
                    'description': f"大纲中提及但正文未出现的角色: {', '.join(missing[:5])}",
                    'severity': 'medium',
                    'locations': []
                })

        # 4. 角色一致性：检查已死亡角色是否"活跃出场"（区分回忆/提及/闪回）
        if self.ledger:
          for name, cs in self.ledger.character_states.items():
            if name in content and not cs.is_alive and not getattr(cs, 'archived', False):
                locs = _find_word_positions(content, name)
                # 上下文感知：区分"活跃出场"与"回忆/提及/闪回"
                is_active = False
                active_verbs = ['说', '道', '笑', '怒', '走', '来', '看', '想', '做', '拿', '打', '杀', '站', '坐', '转', '挥', '拍', '拉', '推', '踢']
                mention_contexts = ['回忆', '想起', '记得', '记忆中', '当年', '曾经', '往事', '梦中', '闪回', '从前', '那年', '过去', '怀念', '思念', '缅怀', '提到', '说起', '谈起', '听闻', '据说', '传说', '故事中', '历史上', '名字', '墓', '碑', '遗', '画像']

                for loc in locs:
                    # 获取角色名前后各30字的上下文
                    start = max(0, loc - 30)
                    end = min(len(content), loc + len(name) + 30)
                    context = content[start:end]

                    # 检查是否在回忆/提及/闪回语境中
                    in_mention = any(mc in context for mc in mention_contexts)
                    if in_mention:
                        continue  # 回忆/提及，不拦截

                    # 检查是否有活跃动作（角色名后5字内有动作动词）
                    after = content[loc:loc + len(name) + 5]
                    has_action = any(av in after for av in active_verbs)
                    if has_action:
                        is_active = True
                        break

                if is_active:
                    issues.append({
                        'type': 'dead_character',
                        'description': f"已死亡角色 {name} 活跃出场（有动作描写），请确认是否为回忆/闪回；若需复活请在角色管理中修改状态",
                        'severity': 'high',
                        'locations': locs
                    })

        # 4.5. 逾期伏笔拦截：检查未回收伏笔是否严重逾期
        try:
            overdue = self.ledger.get_overdue_hooks(chapter_index + 1)
        except Exception:
            overdue = []
        if overdue:
            desc = f"有{len(overdue)}处逾期伏笔未回收：{', '.join(h.content[:20] for h in overdue[:5])}"
            severity = 'high' if len(overdue) >= 5 else 'medium'
            if len(overdue) >= 5:
                desc += " — 建议先去伏笔面板回收或放弃后再继续生成"
            issues.append({
                'type': 'overdue_foreshadowing',
                'description': desc,
                'severity': severity,
                'locations': []
            })

        # 5. 扩展审计：AI味检测 + 战力崩坏检测（纯规则）
        try:
            from backend.services.audit import run_extended_audit
            # 构建角色状态列表
            char_list = []
            if self.ledger:
              for name, cs in self.ledger.character_states.items():
                char_list.append({
                    "name": name,
                    "realm": getattr(cs, 'realm', ''),
                    "prev_realm": getattr(cs, 'prev_realm', ''),
                    "status": "alive" if cs.is_alive else "dead",
                    "archived": getattr(cs, 'archived', False),
                })
            # 获取逾期伏笔
            overdue_hooks = []
            try:
                overdue = self.ledger.get_overdue_hooks(chapter_index + 1)
                if overdue:
                    overdue_hooks = [{"content": h.content, "chapter": h.chapter} for h in overdue]
            except Exception as e:
                logger.warning("扩展审计获取逾期伏笔失败: %s", e)

            audit_result = run_extended_audit(content, characters=char_list, overdue_hooks=overdue_hooks)

            # 如果审计未通过，将关键问题加入 issues（记录 warning）
            if audit_result["overall_level"] == "fail":
                for issue in audit_result["all_issues"][:3]:
                    issues.append({
                        'type': f"audit_{issue.get('type', 'unknown')}",
                        'description': issue.get('message', str(issue)),
                        'severity': 'high',
                        'locations': issue.get('locations', [])
                    })
            elif audit_result["overall_level"] == "review":
                # review级别报告所有严重问题（含新维度）
                severe_types = ("buzzword_forbidden", "dead_revival", "realm_jump",
                                "logic_gaps", "character_break", "pov_drift",
                                "setting_conflict", "spatial_consistency", "climax_missing")
                severe = [i for i in audit_result["all_issues"] if i["type"] in severe_types]
                for issue in severe[:3]:
                    issues.append({
                        'type': f"audit_{issue.get('type', 'unknown')}",
                        'description': issue.get('message', str(issue)),
                        'severity': 'medium',
                        'locations': issue.get('locations', [])
                    })
        except ImportError as e:
            logger.debug("audit模块不可用，跳过: %s", e)
        except Exception as e:
            logger.debug(f"扩展审计异常: {e}")

        # 6. 统一 Guard 管线（P1-1~P1-6：CJK复读/段首重复/必含线索/字数门禁/连续总结结尾）
        try:
            guard_ctx = {"min_words": 500}  # 与现有长度阈值对齐
            if outline_names:
                guard_ctx["required_clues"] = outline_names
            report = self._get_guard_pipeline().run(content, guard_ctx)
            for gi in report.issues:
                issues.append({
                    "type": f"guard_{gi.guard_name}",
                    "description": gi.message,
                    "severity": _GUARD_SEVERITY_MAP.get(gi.severity, "medium"),
                    "locations": gi.locations,
                })
        except Exception as e:
            logger.debug(f"Guard管线异常: {e}")

        # 7. 防幻觉检查（P3-2：实体名近似/规范字段失配，OPEN 幂等）
        try:
            from backend.services.hallucination_guard import get_default_guard
            h_report = get_default_guard().check(
                content,
                ledger=getattr(self, "ledger", None),
                world=getattr(self, "world", None),
                chapter_index=chapter_index,
            )
            for hi in h_report.get("new_issues", []):
                issues.append({
                    "type": f"hallucination_{hi.get('issue_type', 'unknown')}",
                    "description": hi.get("detail", ""),
                    "severity": "medium",
                    "locations": [hi.get("entity", "")],
                })
        except Exception as e:
            logger.debug(f"防幻觉检查异常: {e}")

        return issues

    def _build_repair_instructions(self, issues: List[Dict], title: str, outline: str) -> str:
        """根据 high 级问题构建重试时的修复指令"""
        high_issues = [i for i in issues if i.get('severity') == 'high']
        if not high_issues:
            return ""
        lines = []
        for idx, issue in enumerate(high_issues, 1):
            itype = issue.get('type', 'unknown')
            desc = issue.get('description', '')
            if itype == 'forbidden_words':
                lines.append(f"{idx}. 移除所有禁用词汇，确保不再出现违禁表达")
            elif itype == 'too_short':
                lines.append(f"{idx}. 内容过短，请扩写至合理篇幅，保证情节完整")
            elif itype == 'dead_character':
                lines.append(f"{idx}. 已死亡角色不应再次出场或有对话，请修改相关段落")
            elif itype == 'overdue_foreshadowing':
                lines.append(f"{idx}. 本章优先回收至少1-2处逾期伏笔，推进主线")
            elif itype.startswith('audit_'):
                lines.append(f"{idx}. {desc}")
            else:
                lines.append(f"{idx}. {desc}")
