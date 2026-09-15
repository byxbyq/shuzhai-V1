# -*- coding: utf-8 -*-
import re
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

"""高潮缺失检测"""

from backend.services.audit_utils import _line_number
def detect_climax_missing(content: str, chapter_index: int = 0,
                          chapter_info: Dict = None) -> List[Dict]:
    """高潮缺失检测：关键章节缺少高潮"""
    issues = []
    if not content or len(content) < 500:
        return issues

    # 判断是否为关键章节（卷末、大事件章节）
    is_key_chapter = False
    if chapter_info:
        importance = chapter_info.get('importance', '')
        strand_type = chapter_info.get('strand_type', '')
        if importance in ['climax', 'key', 'turning_point'] or strand_type in ['F', 'C']:
            is_key_chapter = True

    # 检测高潮强度指标
    climax_indicators = [
        # 战斗/冲突
        r'(战|斗|杀|攻|防|挡|劈|刺|轰|爆|裂)',
        # 情感爆发
        r'(怒|悲|痛|哭|喊|吼|嘶|咆哮|怒吼)',
        # 转折
        r'(却|然而|不料|谁知|突然|忽然|蓦地|陡然)',
        # 高潮句式
        r'(终于|终究|到底|毕竟|果不其然|不出所料)',
    ]

    indicator_counts = []
    for pattern in climax_indicators:
        matches = re.findall(pattern, content)
        indicator_counts.append(len(matches))

    total_indicators = sum(indicator_counts)
    content_length = len(content)
    # 高潮密度（每千字的高潮指标数）
    climax_density = (total_indicators / max(content_length, 1)) * 1000

    # 关键章节但高潮密度过低
    if is_key_chapter and climax_density < 5:
        issues.append({
            'type': 'climax_missing',
            'location': 1,
            'message': f'关键章节高潮密度过低（{climax_density:.1f}/千字），缺少冲突、转折或情感爆发'
        })
    # 非关键章节但检查结尾是否有悬念/钩子
    elif not is_key_chapter:
        # 检查最后200字
        ending = content[-200:] if len(content) > 200 else content
        hook_indicators = ['？', '！', '……', '未知', '不知道', '究竟', '到底', '何去何从', '且看下回']
        hook_count = sum(ending.count(h) for h in hook_indicators)
        if hook_count == 0 and chapter_index > 0:
            issues.append({
                'type': 'climax_missing',
                'location': _line_number(content, len(content) - 200) if len(content) > 200 else 1,
                'message': '章节结尾缺少悬念钩子，可能导致读者流失'
            })

    return issues[:2]


