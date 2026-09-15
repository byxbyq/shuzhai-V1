# -*- coding: utf-8 -*-
"""书斋 V65 - AI 生成器 + Gate 闭环"""
import logging
from typing import Callable
from .ai_client import AIClient
from .ledger import TruthLedger
from .world_settings import WorldSettings
from .services.vector_memory import VectorMemory
from backend.generator_prompts import GeneratorPromptsMixin
from backend.services.audit import run_extended_audit
from backend.services.rewrite_loop import (
    RewriteLoop, RewriteConfig, ContextLayer,
)
from backend.services.commitment_tracker import CommitmentTracker, scan_commitments
from backend.services.scene_d_discipline import SceneDChecker

logger = logging.getLogger(__name__)


from backend.generator_quality import ChapterQualityMixin
from backend.generator_blueprint import ChapterBlueprintMixin

class ChapterGenerator(GeneratorPromptsMixin, ChapterQualityMixin, ChapterBlueprintMixin):
    """章节生成 + 校验 Gate"""

    def __init__(self, project_dir: str, project=None):
        self.ai = AIClient()
        try:
            self.ledger = TruthLedger(project_dir)
        except Exception as e:
            logger.warning("TruthLedger初始化失败: %s, ledger设为None", e)
            self.ledger = None
        try:
            self.world = WorldSettings(project_dir)
        except Exception as e:
            logger.warning("WorldSettings初始化失败: %s", e)
            self.world = WorldSettings("")
        try:
            self.vector_memory = VectorMemory(project_dir)
        except Exception as e:
            logger.warning("VectorMemory初始化失败: %s", e)
            self.vector_memory = None
        self.project_dir = project_dir
        self._project = project  # 注入的NovelProject引用，消除反向依赖
        self._distilled_cache = None  # 蒸馏记忆临时缓存，供内部方法间传递

    @property
    def project(self):
        """获取project引用，优先使用注入的，否则从state获取（兼容）"""
        if self._project is not None:
            return self._project
        try:
            from backend.services.project_service import state
            return state.project
        except Exception:
            return None

    def reload_world(self):
        """重新加载世界观设定（在设定被更新后调用）"""
        self.world = WorldSettings(self.project_dir)

    def set_genre(self, genre: str):
        self.genre = genre

    # ═══════════════════════════════════════════
    # Gate: 生成 → 校验 → 修订循环
    # ═══════════════════════════════════════════


    def _get_adaptive_temperature(self, chapter_type: str, attempt: int = 1) -> float:
        """根据章节类型和重试次数自适应温度
        第一次生成用较高温度（有创意），重试时逐渐降温（求稳）
        """
        base_temp = {
            "battle": 0.95,      # 战斗：高能有张力（+0.1，增加不可预测性以降低AI味）
            "climax": 0.92,      # 高潮转折：惊喜但不跑偏
            "emotion": 0.88,     # 情感：细腻有温度
            "mystery": 0.85,     # 悬疑：精准但有留白
            "transition": 0.82,  # 过渡：自然流畅
            "setup": 0.75,       # 铺垫设定：严谨准确
            "daily": 0.80,       # 日常：轻松自然
        }.get(chapter_type, 0.85)

        # 重试时降温，每次降 0.08
        decay = 0.08 * (attempt - 1)
        return round(max(0.5, base_temp - decay), 2)

    def generate_and_validate(
        self, title: str, outline: str, context: str = "",
        chapter_index: int = 0, max_retries: int = 3, on_chunk: Callable = None,
        skill_rules: str = "", use_distilled_memory: bool = True,
        enable_auto_review: bool = True
    ) -> dict:
        """
        生成草稿 → 硬校验 → （high问题触发重试）→ 后处理 → 大纲覆盖 → 返回
        返回 {"ok": bool, "content": str, "validation_log": [...], "attempts": int}

        重试策略：high 严重度问题触发重试，重试时 prompt 追加修复指令；
        达到 max_retries 次后即使仍有 high 问题也返回（避免无限循环）。
        """
        validation_log = []
        # 自适应温度：先判断章节类型
        chapter_type = self._detect_chapter_type(title, outline)
        base_prompt = self._build_generation_prompt(title, outline, context, chapter_index, [],
                                                    skill_rules=skill_rules, use_distilled_memory=use_distilled_memory)

        # --- 有界改写循环 (P2-1) ---
        initial_temp = self._get_adaptive_temperature(chapter_type, 1)
        cfg = RewriteConfig(
            max_rounds=max_retries,
            temperature_base=initial_temp,
            temperature_decay=0.08,
            temperature_floor=0.5,
            stagnation_limit=2,
        )
        loop = RewriteLoop(config=cfg)

        # 注入上下文层（当前全量 prompt 放入 DYNAMIC，后续可按 STATIC/REPAIR 分层优化）
        loop.inject_layer(ContextLayer.DYNAMIC, base_prompt)

        def _generate(prompt: str, temperature: float) -> str:
            return self.ai.generate_for_task(
                prompt, task_type="writing",
                max_tokens=8192,
                temperature=temperature,
            )

        def _validate(content: str):
            return self._run_hard_checks(content, title, outline, chapter_index)

        def _build_repair(issues):
            return self._build_repair_instructions(issues, title, outline)

        rewrite_result = loop.run(_generate, _validate, build_repair=_build_repair)

        content = rewrite_result.content
        attempts = rewrite_result.round_count
        current_issues = rewrite_result.final_issues

        # 校验日志
        for ri, rnd in enumerate(rewrite_result.rounds):
            if ri == 0:
                validation_log.extend(rnd.issues)
            else:
                for issue in rnd.issues:
                    issue = dict(issue)
                    issue['description'] = f"[第{ri + 1}次重试] {issue['description']}"
                    validation_log.append(issue)

        # --- 承诺台账 (P2-4) ---
        self._commitment_tracker = getattr(self, '_commitment_tracker', None)
        if self._commitment_tracker is None:
            self._commitment_tracker = CommitmentTracker()
        # 生成后扫描新承诺
        new_cmts = scan_commitments(content, chapter_index)
        self._commitment_tracker.register_batch(new_cmts, chapter_index)
        # 检查旧承诺是否已兑现
        self._commitment_tracker.check_fulfillment(content, chapter_index)
        # 将待兑现承诺注入下次生成（通过实例属性在 _build_generation_prompt 中引用）
        self._pending_commitments_context = self._commitment_tracker.get_context_for_chapter(chapter_index)

        # --- scene_d 运行时检测 ---
        scene_d_checker = SceneDChecker()
        scene_d_result = scene_d_checker.check(content)
        if scene_d_result.get("violations"):
            for v in scene_d_result["violations"]:
                if v.get("severity") == "high":
                    validation_log.append({
                        "type": f"scene_d_{v['rule_id']}",
                        "description": f"[scene_d纪律] {v['message']}",
                        "severity": "medium",
                        "locations": v.get("evidence", []),
                    })

        # 后处理 + 大纲覆盖
        content = self._post_process(content)
        content = self._ensure_outline_coverage(content, outline, title, chapter_index, context)

        warning = ""
        remaining_high = [i for i in current_issues if i.get('severity') == 'high']
        if remaining_high:
            issue_summary = ", ".join(f"{i['type']}: {i['description'][:40]}" for i in remaining_high[:3])
            warning = f"经过{attempts}次生成仍有{len(remaining_high)}条high级问题: {issue_summary}"
        elif current_issues:
            issue_summary = ", ".join(f"{i['type']}: {i['description'][:40]}" for i in current_issues[:3])
            warning = f"硬校验发现{len(current_issues)}条问题(均为medium及以下): {issue_summary}"

        if content and len(content) >= 200:
            result = {"ok": True, "content": content, "validation_log": validation_log,
                      "attempts": attempts, "warning": warning,
                      "chapter_type": chapter_type,
                      "temperature": self._get_adaptive_temperature(chapter_type, 1)}

            # 自动分析（章级多维评估）
            if enable_auto_review:
                assessment = {}

                # 1. editorial-review（6维读者评分）
                try:
                    from backend.routers.validate import _do_editorial_review
                    review = _do_editorial_review(content, mode="reader_focus")
                    if review.get("ok"):
                        assessment["editorial_review"] = {
                            "dimensions": review.get("dimensions", []),
                            "strengths": review.get("strengths", []),
                            "improvements": review.get("improvements", []),
                            "overall_comment": review.get("overall_comment", ""),
                        }
                        logger.info(f"[自动评分] 第{chapter_index + 1}章评分完成，模式=reader_focus")
                except Exception as e:
                    logger.warning(f"[自动评分] 第{chapter_index + 1}章评分失败: {e}")

                # 2. extended-audit（AI味+战力崩坏+逾期伏笔）
                try:
                    characters = []
                    overdue_hooks = []
                    if self.ledger:
                        for name, cs in self.ledger.character_states.items():
                            characters.append({
                                "name": name,
                                "realm": getattr(cs, 'realm', ''),
                                "prev_realm": getattr(cs, 'prev_realm', ''),
                                "status": "alive" if cs.is_alive else "dead",
                            })
                        try:
                            overdue = self.ledger.get_overdue_hooks(chapter_index + 1)
                            if overdue:
                                overdue_hooks = [{"content": h.content, "chapter": h.planted_chapter} for h in overdue]
                        except Exception as e:
                            logger.warning("获取逾期伏笔失败: %s", e)
                    audit_result = run_extended_audit(content, chapter_index, characters, overdue_hooks)
                    assessment["extended_audit"] = audit_result
                    logger.info(f"[扩展审计] 第{chapter_index + 1}章审计完成，总分={audit_result.get('overall_score')}")
                    # 存储审计反馈到 ledger，用于下一章的动态去AI味引导
                    if self.ledger and audit_result.get("all_issues"):
                        try:
                            self.ledger.store_audit_feedback(chapter_index + 1, audit_result["all_issues"])
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning(f"[扩展审计] 第{chapter_index + 1}章审计失败: {e}")

                # 3. validate_all（10维质量检查：偏差/转折/重复/时间线/冲突/风格/字数/完整性/连贯性/一致性）
                try:
                    from backend.routers.validate import validate_all, ValidateRequest
                    ctx = {
                        "stage": "content",
                        "chapterIndex": chapter_index,
                        "chapterOutline": outline,
                    }
                    all_result = validate_all(
                        ValidateRequest(content=content, context=ctx)
                    )
                    assessment["quality_checks"] = all_result
                    if all_result.get("ok"):
                        logger.info(f"[质量检查] 第{chapter_index + 1}章检查完成，{all_result.get('parsed_count', 0)}/{all_result.get('total', 0)}项")
                except Exception as e:
                    logger.warning(f"[质量检查] 第{chapter_index + 1}章检查失败: {e}")

                result["assessment"] = assessment

                # 4. 审稿驱动自动修复：有低分维度时，追加一轮定向润色
                try:
                    repair_result = self._review_driven_repair(
                        content, title, outline, assessment, chapter_index,
                        skill_rules=skill_rules, use_distilled_memory=use_distilled_memory
                    )
                    if repair_result and repair_result.get("repaired"):
                        content = repair_result["content"]
                        result["content"] = content
                        result["review_repair"] = {
                            "repaired": True,
                            "fixed_dimensions": repair_result.get("fixed_dimensions", []),
                            "before_scores": repair_result.get("before_scores", {}),
                            "after_scores": repair_result.get("after_scores", {}),
                        }
                        assessment["review_repair"] = repair_result.get("repair_summary", {})
                except Exception as e:
                    logger.warning(f"[审稿修复] 第{chapter_index + 1}章修复失败: {e}")

                # 回写到章节对象
                if self.project and chapter_index < len(self.project.chapters):
                    ch = self.project.chapters[chapter_index]
                    if isinstance(ch, dict):
                        ch["assessment"] = assessment
                        self.project.save_all()

            return result
        return {"ok": False, "content": content, "validation_log": validation_log, "attempts": 1, "warning": warning or "内容过短，生成失败"}

    def _ensure_outline_coverage(self, content: str, outline: str,
                                  title: str, chapter_index: int, context: str) -> str:
        """大纲覆盖率检查：调用 evaluate_outline_coverage 进行纯关键词检测，不再使用 AI 验证。

        对未覆盖的段落记录日志，不阻塞流程，直接返回原内容。
        用户可在生成后手动查看覆盖率报告。
        """
        result = self.evaluate_outline_coverage(content, outline)
        if result.get("ok"):
            missing = result.get("missing_summary", "")
            coverage = result.get("coverage_percent", 100)
            if missing != "全覆盖":
                print(f"[大纲覆盖] 第{chapter_index + 1}章 覆盖率 {coverage}%，{missing}")
        return content

    def evaluate_outline_coverage(self, content: str, outline: str) -> dict:
        """大纲覆盖评估：纯关键词匹配检测，不再调用 AI 验证不确定段落"""
        import re as _re

        # 策略1：从outline文本中按【起】【承】【转】【合】分段，提取每段的关键词
        segments_raw = _re.split(r'(【[起承转合].*?】)', outline)
        # 重组为 [(tag, content), ...]
        segments = []
        current_tag = ""
        for i, part in enumerate(segments_raw):
            tag_match = _re.match(r'【([起承转合].*?)】', part)
            if tag_match:
                current_tag = tag_match.group(1)
            elif current_tag and part.strip():
                segments.append((current_tag, part.strip()))

        if not segments:
            return {"ok": False, "error": "大纲中未找到【起】【承】【转】【合】段落标记"}

        results = []
        uncertain_indices = []
        for i, (tag, text) in enumerate(segments):
            # 提取关键词：优先匹配专有名词（2-4字的人名/地名），然后取核心动词/名词
            keywords = []
            seen = set()
            # 提取2-4字中文词（专有名词更可能是2-4字）
            for w in _re.findall(r'[\u4e00-\u9fa5]{2,4}', text):
                if w not in seen:
                    seen.add(w)
                    keywords.append(w)
            # 去掉常见虚词
            stop_words = {'但是', '因为', '所以', '虽然', '如果', '可以', '已经', '然后', '接着',
                          '开始', '进行', '通过', '之后', '之前', '这时', '同时', '最后',
                          '一个', '没有', '不是', '这个', '那个', '什么', '怎么', '自己',
                          '他们', '她们', '他们', '我们', '你们', '但是', '然而'}
            keywords = [k for k in keywords if k not in stop_words]
            # 优先保留名词性关键词（匹配项目角色名的词优先）
            char_names = set()
            try:
                _proj = self.project
                if _proj:
                    _chars = getattr(_proj, 'characters', []) or []
                    for _c in _chars:
                        _n = _c.get('name', '')
                        if _n and len(_n) >= 2 and _n not in stop_words:
                            char_names.add(_n)
            except Exception as e:
                logger.warning("获取项目角色列表失败: %s", e)
            important = [k for k in keywords if k in char_names]
            other = [k for k in keywords if k not in important]
            keywords = (important + other)[:12]  # 最多12个关键词

            # 检查关键词命中：用包含匹配（而非精确匹配）
            hits = []
            for k in keywords:
                if k in content:
                    hits.append(k)
                    continue
                # 尝试子串匹配：如果关键词是"白墨刚把"，检查"白墨"是否在正文中
                for sub_len in range(len(k), 1, -1):
                    sub = k[:sub_len]
                    if len(sub) >= 2 and sub in content:
                        hits.append(f"{k}({sub})")
                        break

            hit_ratio = len(hits) / max(len(keywords), 1)

            if hit_ratio >= 0.5:  # 降为50%阈值
                results.append({"tag": tag, "covered": True, "reason": f"命中{len(hits)}/{len(keywords)}: {', '.join(hits[:3])}"})
            elif hit_ratio >= 0.25:
                results.append({"tag": tag, "covered": None, "reason": f"命中{len(hits)}/{len(keywords)}，不确定"})
                uncertain_indices.append(i)
            else:
                results.append({"tag": tag, "covered": False, "reason": f"命中{len(hits)}/{len(keywords)}: 缺少{keywords[:4]}"})

        # 计算覆盖率
        covered_count = sum(1 for r in results if r.get("covered") is True)
        total = len(results)
        coverage = int(covered_count / max(total, 1) * 100)

        missing_tags = [r["tag"] for r in results if r.get("covered") is False]
        missing_summary = f"缺失{', '.join(missing_tags)}" if missing_tags else "全覆盖"

        # 如果没有不确定段落，直接返回关键词结果
        if not uncertain_indices:
            return {
                "ok": True,
                "segments": results,
                "coverage_percent": coverage,
                "missing_summary": missing_summary
            }

        # 不确定的段落直接标记为未覆盖（不再使用AI验证，节省token）
        for idx in uncertain_indices:
            results[idx]["covered"] = False
            results[idx]["reason"] = results[idx].get("reason", "") + " (关键词匹配不充分，标记为未覆盖)"

        # 重新计算覆盖率
        covered_count = sum(1 for r in results if r.get("covered") is True)
        coverage = int(covered_count / max(total, 1) * 100)
        missing_tags = [r["tag"] for r in results if r.get("covered") is False]
        missing_summary = f"缺失{', '.join(missing_tags)}" if missing_tags else "全覆盖"

        return {
            "ok": True,
            "segments": results,
            "coverage_percent": coverage,
            "missing_summary": missing_summary
        }


class WorldBuilder:
    """世界观字典 → 提示词文本构建器。

    历史兼容：routers/generate、routers/project_volumes 等 3 处通过
    `from backend.generator import WorldBuilder` 引用，此前该类从未存在，
    引用被 try/except 静默吞掉导致世界观上下文从未注入。现补齐实现。
    """

    def __init__(self, world_dict: dict):
        self.data = world_dict if isinstance(world_dict, dict) else {}

    def to_prompt(self) -> str:
        """将世界观字典渲染为紧凑提示词文本（无内容时返回空串）"""
        parts = []
        core = self.data.get("world_settings_core") or self.data.get("world_settings") or {}
        if isinstance(core, dict):
            for k, v in core.items():
                if v:
                    parts.append(f"{k}: {str(v)[:200]}")
        if self.data.get("era"):
            parts.append("时代背景: " + str(self.data["era"])[:200])
        if self.data.get("narrative_style"):
            ns = self.data["narrative_style"]
            if isinstance(ns, dict) and ns:
                parts.append("叙事风格: " + str(ns)[:200])
        if self.data.get("magic_system"):
            parts.append("力量体系: " + str(self.data["magic_system"])[:300])
        for key, label in (("forces", "势力"), ("world_locations", "地点"), ("world_items", "物品")):
            items = self.data.get(key) or []
            if isinstance(items, list) and items:
                names = [it.get("name", "") for it in items if isinstance(it, dict)]
                names = [n for n in names if n][:12]
                if names:
                    parts.append(label + ": " + "、".join(names))
        rules = self.data.get("world_rules") or []
        if isinstance(rules, list) and rules:
            parts.append("世界规则: " + "; ".join(str(r) for r in rules[:8]))
        hc = self.data.get("hard_constraints") or []
        if isinstance(hc, list) and hc:
            parts.append("硬性约束: " + "; ".join(str(r) for r in hc[:5]))
        ff = self.data.get("freeform")
        if isinstance(ff, dict):
            ff = ff.get("text") or ff.get("content") or ""
        if isinstance(ff, str) and ff.strip():
            parts.append(ff.strip()[:300])
        return "\n".join(parts)

