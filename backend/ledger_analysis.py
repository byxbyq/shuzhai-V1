# -*- coding: utf-8 -*-
"""TruthLedger 阅读分析方法（从 ledger.py 拆分）"""
import logging

logger = logging.getLogger(__name__)


class LedgerAnalysisMixin:
    """提供阅读吸引力分析和情节线统计"""

    def get_read_pull(self, current_chapter: int = 0) -> dict:
        """计算追读力评分（0-100），基于开放悬念的数量、强度和弧线分布"""
        active = self.get_pending_hooks()
        if not active:
            return {
                "score": 0, "level": "empty",
                "summary": "无开放悬念，追读力为零",
                "active_count": 0
            }

        # 1. 开放悬念数量分（0-30分，每个悬念+5分，上限30）
        count_score = min(30, len(active) * 5)

        # 2. 强度加权分（0-30分，按strength 1-5加权）
        total_strength = sum(h.strength for h in active)
        max_strength = len(active) * 5
        strength_ratio = total_strength / max_strength if max_strength > 0 else 0
        strength_score = round(strength_ratio * 30)

        # 3. 弧线覆盖分（0-20分，short+medium+long三种弧线同时运行得满分）
        arc_types = set(h.arc_type for h in active if h.arc_type)
        arc_score = len(arc_types) * 7  # 每种弧线7分，三种共21分上限

        # 4. 即将到期悬念分（0-20分，expected_recovery_chapter临近当前章节的悬念加分）
        imminent_score = 0
        for h in active:
            if h.expected_recovery_chapter and h.expected_recovery_chapter > 0:
                gap = h.expected_recovery_chapter - current_chapter
                if gap <= 0:
                    imminent_score += 8  # 已逾期，追读力极高
                elif gap <= 2:
                    imminent_score += 6  # 即将到期
                elif gap <= 5:
                    imminent_score += 3  # 中期
        imminent_score = min(20, imminent_score)

        total = count_score + strength_score + arc_score + imminent_score
        total = min(100, total)

        # 等级
        if total >= 70:
            level = "strong"
            desc = "追读力强劲"
        elif total >= 40:
            level = "moderate"
            desc = "追读力适中"
        elif total >= 20:
            level = "weak"
            desc = "追读力偏弱"
        else:
            level = "empty"
            desc = "追读力不足"

        # 分布统计
        arc_distribution = {"short": 0, "medium": 0, "long": 0, "untyped": 0}
        strength_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for h in active:
            arc_distribution[h.arc_type or "untyped"] = arc_distribution.get(h.arc_type or "untyped", 0) + 1
            s = max(1, min(5, h.strength))
            strength_distribution[s] = strength_distribution.get(s, 0) + 1

        # 警告：弧线缺失
        warnings = []
        if not arc_types:
            warnings.append("未设置悬念弧线类型，建议为伏笔标注 short/medium/long")
        if len(arc_types) == 1:
            warnings.append(f"仅{list(arc_types)[0]}弧线在运行，建议同时运行三种弧线维持追读力")
        if len(active) > 0 and total_strength / len(active) < 2:
            warnings.append("悬念强度偏低（平均<2级），建议增加高强度悬念")

        summary = f"追读力: {total}/100 ({desc}) | 开放悬念{len(active)}个 | 强度分{strength_score}/30 | 弧线分{arc_score}/21"

        return {
            "score": total,
            "level": level,
            "summary": summary,
            "active_count": len(active),
            "count_score": count_score,
            "strength_score": strength_score,
            "arc_score": min(21, arc_score),
            "imminent_score": imminent_score,
            "arc_distribution": arc_distribution,
            "strength_distribution": strength_distribution,
            "warnings": warnings,
        }

    # ═══════════════════════════════════════════
    # H1: Strand Weave 节奏系统 — 三线比例监控
    # ═══════════════════════════════════════════

    def get_strand_stats(self, current_chapter: int = 0) -> dict:
        """统计Strand分布并检查红线规则"""
        if not self.chapter_logs:
            return {
                "total": 0,
                "distribution": {"Q": 0, "F": 0, "C": 0, "untyped": 0},
                "percentages": {},
                "red_lines": [],
                "summary": "无章节记录"
            }

        # 统计各线型数量
        distribution = {"Q": 0, "F": 0, "C": 0, "untyped": 0}
        strand_sequence = []
        for log in self.chapter_logs:
            st = log.strand_type.upper() if log.strand_type else ""
            if st in ("Q", "F", "C"):
                distribution[st] += 1
                strand_sequence.append(st)
            else:
                distribution["untyped"] += 1
                strand_sequence.append("")

        total = len(self.chapter_logs)
        typed = total - distribution["untyped"]
        percentages = {}
        if typed > 0:
            percentages = {
                "Q": round(distribution["Q"] / typed * 100),
                "F": round(distribution["F"] / typed * 100),
                "C": round(distribution["C"] / typed * 100),
            }

        # 红线规则检查
        red_lines = []

        # Rule 1: Quest连续不超过5章
        consecutive_q = 0
        max_consecutive_q = 0
        for s in strand_sequence:
            if s == "Q":
                consecutive_q += 1
                max_consecutive_q = max(max_consecutive_q, consecutive_q)
            else:
                consecutive_q = 0
        if max_consecutive_q > 5:
            red_lines.append(f"Quest线连续{max_consecutive_q}章，超过5章红线，建议插入Fire或Constellation章")

        # Rule 2: Fire断档不超过10章
        last_fire_idx = -1
        max_fire_gap = 0
        for i, s in enumerate(strand_sequence):
            if s == "F":
                if last_fire_idx >= 0:
                    gap = i - last_fire_idx - 1
                    max_fire_gap = max(max_fire_gap, gap)
                last_fire_idx = i
        if last_fire_idx >= 0:
            gap_to_current = len(strand_sequence) - 1 - last_fire_idx
            max_fire_gap = max(max_fire_gap, gap_to_current)
        if max_fire_gap > 10:
            red_lines.append(f"Fire线断档{max_fire_gap}章，超过10章红线，读者可能流失，建议安排爽点")

        # Rule 3: Constellation断档不超过15章
        last_c_idx = -1
        max_c_gap = 0
        for i, s in enumerate(strand_sequence):
            if s == "C":
                if last_c_idx >= 0:
                    gap = i - last_c_idx - 1
                    max_c_gap = max(max_c_gap, gap)
                last_c_idx = i
        if last_c_idx >= 0:
            gap_to_current = len(strand_sequence) - 1 - last_c_idx
            max_c_gap = max(max_c_gap, gap_to_current)
        if max_c_gap > 15:
            red_lines.append(f"Constellation线断档{max_c_gap}章，超过15章红线，世界观可能单薄")

        # 比例偏离检查
        target = {"Q": 60, "F": 20, "C": 20}
        deviations = {}
        for k in ("Q", "F", "C"):
            if k in percentages:
                dev = percentages[k] - target[k]
                if abs(dev) > 15:
                    deviations[k] = dev

        summary_parts = [f"Strand分布: Q={percentages.get('Q',0)}% F={percentages.get('F',0)}% C={percentages.get('C',0)}%"]
        if red_lines:
            summary_parts.append(f"红线告警{len(red_lines)}条")
        if deviations:
            summary_parts.append(f"比例偏离: {', '.join(k + ('+' if v>0 else '') + str(v) + '%' for k,v in deviations.items())}")

        return {
            "total": total,
            "typed": typed,
            "distribution": distribution,
            "percentages": percentages,
            "target": target,
            "deviations": deviations,
            "red_lines": red_lines,
            "strand_sequence": strand_sequence,
            "max_consecutive_q": max_consecutive_q,
            "max_fire_gap": max_fire_gap,
            "max_c_gap": max_c_gap,
            "summary": " | ".join(summary_parts),
        }
