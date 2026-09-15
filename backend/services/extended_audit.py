# -*- coding: utf-8 -*-
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

"""综合审计 — 汇总执行所有检测器"""

from backend.services.ai_flavor import detect_ai_flavor, compute_ai_score
from backend.services.detect_power import detect_power_collapse
from backend.services.detect_logic import detect_logic_gaps
from backend.services.detect_character import detect_character_break
from backend.services.detect_pov import detect_pov_drift
from backend.services.detect_setting import detect_setting_conflict
from backend.services.detect_spatial import detect_spatial_consistency
from backend.services.detect_climax import detect_climax_missing

# ═══════════════════════════════════════════
# 综合审计
# ═══════════════════════════════════════════

def run_extended_audit(content: str, chapter_index: int = 0,
                       characters: List[Dict] = None,
                       overdue_hooks: List[Dict] = None) -> Dict:
    """运行扩展审计（纯规则，不消耗Token）"""
    ai_result = detect_ai_flavor(content)
    power_result = detect_power_collapse(content, chapter_index, characters)
    ai_score_info = compute_ai_score(ai_result)

    all_issues = ai_result['issues'] + power_result['issues']

    # 6 项扩展审计检测
    logic_issues = detect_logic_gaps(content, chapter_index, characters)
    character_issues = detect_character_break(content, chapter_index, characters)
    pov_issues = detect_pov_drift(content, chapter_index)
    setting_issues = detect_setting_conflict(content, chapter_index)
    spatial_issues = detect_spatial_consistency(content, chapter_index, characters)
    climax_issues = detect_climax_missing(content, chapter_index)

    all_issues.extend(logic_issues)
    all_issues.extend(character_issues)
    all_issues.extend(pov_issues)
    all_issues.extend(setting_issues)
    all_issues.extend(spatial_issues)
    all_issues.extend(climax_issues)

    # Overdue hooks
    hook_issues = []
    if overdue_hooks:
        for hook in overdue_hooks:
            hook_text = hook.get('content', '')[:30]
            hook_ch = hook.get('chapter', '?')
            hook_issues.append({
                'type': 'overdue_foreshadowing',
                'hook': hook_text,
                'set_at': hook_ch,
                'message': 'overdue foreshadowing from chapter ' + str(hook_ch) + ': ' + hook_text + '...'
            })
    all_issues.extend(hook_issues)

    # Overall score
    ai_score = ai_result['score']
    power_score = power_result['score']
    hook_penalty = len(hook_issues) * 5
    # 6 项扩展审计扣分
    ext_audit_penalty = (len(logic_issues) * 8 + len(character_issues) * 6 +
                         len(pov_issues) * 5 + len(setting_issues) * 7 +
                         len(spatial_issues) * 5 + len(climax_issues) * 4)
    overall = min(100, ai_score * 0.4 + power_score * 0.25 + hook_penalty * 0.15 + ext_audit_penalty * 0.2)

    if overall <= 15:
        level = 'pass'
    elif overall <= 40:
        level = 'review'
    else:
        level = 'fail'

    summary = 'Extended audit: ' + str(round(overall, 1)) + '/100 (' + level + ')'
    summary += ' | AI flavor: ' + str(ai_result['score'])
    summary += ' | Power: ' + str(power_result['score'])
    summary += ' | Hooks: ' + str(len(hook_issues))
    summary += ' | Logic/Char/POV/Setting/Spatial/Climax: '
    summary += f'{len(logic_issues)}/{len(character_issues)}/{len(pov_issues)}/{len(setting_issues)}/{len(spatial_issues)}/{len(climax_issues)}'

    return {
        'ai_flavor': ai_result,
        'power_collapse': power_result,
        'overdue_hooks': hook_issues,
        'logic_gaps': logic_issues,
        'character_break': character_issues,
        'pov_drift': pov_issues,
        'setting_conflict': setting_issues,
        'spatial_consistency': spatial_issues,
        'climax_missing': climax_issues,
        'overall_score': round(overall, 1),
        'overall_level': level,
        'all_issues': all_issues,
        'summary': summary,
        'ai_score': ai_score_info['ai_score'],
        'ai_level': ai_score_info['ai_level']
    }


