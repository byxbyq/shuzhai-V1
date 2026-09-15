# -*- coding: utf-8 -*-
import re
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

"""逻辑断层检测"""

from backend.services.audit_utils import _line_number
# ═══════════════════════════════════════════
# 6 项扩展审计实现（纯规则，不消耗Token）
# ═══════════════════════════════════════════

def detect_logic_gaps(content: str, chapter_index: int = 0,
                      characters: List[Dict] = None) -> List[Dict]:
    """逻辑断层检测： abrupt scene transitions, missing causal connectors"""
    issues = []
    if not content or len(content) < 200:
        return issues

    paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
    if len(paragraphs) < 3:
        return issues

    # 1. 检测突兀场景转换：连续段落间无过渡，地点/时间跳跃
    location_markers = ['来到', '回到', '抵达', '进入', '走出', '离开', '赶到']
    time_markers = ['第二天', '三天后', '一周后', '半月后', '一个月后', '数月后', '翌日', '当晚', '清晨', '黄昏']
    transition_words = ['然而', '不过', '与此同时', '与此同时', '就在这时', '随后', '接着', '于是', '因此']

    for i in range(1, len(paragraphs)):
        prev_p = paragraphs[i - 1]
        curr_p = paragraphs[i]
        # 两个段落都很短且无过渡词
        if len(prev_p) < 50 and len(curr_p) < 50:
            has_transition = any(tw in prev_p[-10:] or tw in curr_p[:10] for tw in transition_words)
            if not has_transition:
                # 检测地点/时间跳跃
                prev_loc = any(lm in prev_p for lm in location_markers)
                curr_time = any(tm in curr_p[:20] for tm in time_markers)
                if prev_loc and curr_time:
                    issues.append({
                        'type': 'logic_gaps',
                        'location': _line_number(content, content.find(curr_p)),
                        'message': f'段落{i+1}可能存在场景跳跃：前段提及位置变化，后段突然时间跳跃，缺少过渡'
                    })

    # 2. 检测角色突然知晓不该知道的信息
    if characters:
        knowledge_keywords = ['早已知道', '心中了然', '早就料到', '分明是', '显然是']
        for char in characters:
            name = char.get('name', '')
            if name and name in content:
                for kw in knowledge_keywords:
                    if kw in content:
                        pos = content.find(kw)
                        context_window = content[max(0, pos-30):pos+30]
                        if name in context_window:
                            issues.append({
                                'type': 'logic_gaps',
                                'location': _line_number(content, pos),
                                'message': f'角色{name}可能存在信息来源不明的全知判断（"{kw}"）'
                            })
                            break

    # 3. 检测未解决的悬念突然消失（段落提及某事但后续无跟进）
    suspense_patterns = [
        r'(忽然|突然|蓦地).*?(？|！)',
        r'(是谁|为什么|怎么回事|什么情况)',
    ]
    for pattern in suspense_patterns:
        matches = list(re.finditer(pattern, content))
        for m in matches[:3]:
            # 检查后续500字内是否有回应
            after_text = content[m.end():m.end()+500]
            has_resolution = any(w in after_text for w in ['原来', '是因为', '答案是', '真相', '其实', '事实上'])
            if not has_resolution:
                issues.append({
                    'type': 'logic_gaps',
                    'location': _line_number(content, m.start()),
                    'message': f'此处设置了悬念/疑问，但后续500字内未见回应或解释'
                })

    return issues[:5]  # 限制最多5条


