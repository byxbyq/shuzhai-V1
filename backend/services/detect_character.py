# -*- coding: utf-8 -*-
import re
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

"""人设崩坏检测"""

from backend.services.audit_utils import _line_number
def detect_character_break(content: str, chapter_index: int = 0,
                           characters: List[Dict] = None) -> List[Dict]:
    """人设崩坏检测：角色行为与设定矛盾"""
    issues = []
    if not content or not characters:
        return issues

    # 角色性格特征映射（基于常见设定）
    personality_map = {
        '冷静': ['暴怒', '歇斯底里', '疯狂', '失控', '气急败坏'],
        '冷酷': ['温柔', '心疼', '不舍', '柔情', '暖意'],
        '善良': ['残忍', '狠毒', '冷血', '无动于衷'],
        '胆小': ['挺身而出', '毫不畏惧', '勇往直前', '正面迎击'],
        '高傲': ['卑微', '恳求', '低声下气', '屈服'],
        '沉稳': ['慌张', '手足无措', '惊慌失措', '六神无主'],
    }

    for char in characters:
        name = char.get('name', '')
        if not name or name not in content:
            continue

        # 检查角色描述中的性格关键词
        char_desc = str(char.get('realm', '')) + str(char.get('status', ''))
        for personality, break_words in personality_map.items():
            if personality in char_desc or personality in name:
                for bw in break_words:
                    if bw in content:
                        pos = content.find(bw)
                        # 检查是否在角色名附近（100字内）
                        context = content[max(0, pos-100):pos+100]
                        if name in context:
                            issues.append({
                                'type': 'character_break',
                                'character': name,
                                'location': _line_number(content, pos),
                                'message': f'角色{name}设定为"{personality}"，但出现了"{bw}"的描写，可能存在人设崩坏'
                            })
                            break

    # 检测情绪突变（无铺垫的极端情绪转换）
    emotion_shift_pattern = r'(愤怒|暴怒|狂怒|悲愤).{0,20}(开心|大笑|愉悦|欣喜)'
    for m in re.finditer(emotion_shift_pattern, content):
        issues.append({
            'type': 'character_break',
            'location': _line_number(content, m.start()),
            'message': f'情绪转换过于突兀（{m.group()[:20]}），缺少心理过渡'
        })

    return issues[:3]


