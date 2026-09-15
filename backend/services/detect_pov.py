# -*- coding: utf-8 -*-
import re
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

"""POV漂移检测"""

from backend.services.audit_utils import _line_number
def detect_pov_drift(content: str, chapter_index: int = 0) -> List[Dict]:
    """POV 漂移检测：叙事视角不一致"""
    issues = []
    if not content or len(content) < 500:
        return issues

    paragraphs = [p.strip() for p in content.split('\n') if p.strip() and len(p.strip()) > 30]
    if len(paragraphs) < 3:
        return issues

    # 检测第一人称和第三人称混用
    first_person = ['我', '我们', '我的']
    third_person = ['他', '她', '它', '他们', '她们']

    first_count = 0
    third_count = 0
    first_paras = []
    third_paras = []

    for i, p in enumerate(paragraphs):
        fc = sum(p.count(fp) for fp in first_person)
        tc = sum(p.count(tp) for tp in third_person)
        if fc > tc and fc > 2:
            first_count += 1
            first_paras.append(i)
        elif tc > fc and tc > 2:
            third_count += 1
            third_paras.append(i)

    # 如果同时有大量第一人称和第三人称段落，可能存在POV漂移
    if first_count > 2 and third_count > 2:
        # 找到切换点
        for i in range(1, len(paragraphs)):
            if i in first_paras and (i-1) in third_paras:
                pos = content.find(paragraphs[i])
                if pos >= 0:
                    issues.append({
                        'type': 'pov_drift',
                        'location': _line_number(content, pos),
                        'message': f'叙事视角可能从第三人称切换到第一人称（段落{i+1}），检查是否有意为之'
                    })
                    break
            elif i in third_paras and (i-1) in first_paras:
                pos = content.find(paragraphs[i])
                if pos >= 0:
                    issues.append({
                        'type': 'pov_drift',
                        'location': _line_number(content, pos),
                        'message': f'叙事视角可能从第一人称切换到第三人称（段落{i+1}），检查是否有意为之'
                    })
                    break

    # 检测全知视角侵入（在限制视角叙事中出现其他角色内心活动）
    omniscient_patterns = [
        r'(他|她)心想.{0,50}(另一|旁边|远处)(?:的人|的角色).{0,30}心想',
        r'(他|她)不知道.{0,30}(其实|实际上|殊不知).{0,50}(另一个人|对方)',
    ]
    for pattern in omniscient_patterns:
        for m in re.finditer(pattern, content):
            issues.append({
                'type': 'pov_drift',
                'location': _line_number(content, m.start()),
                'message': '可能存在全知视角侵入：在描述一个角色内心后，又描述了另一角色的内心'
            })

    return issues[:3]


