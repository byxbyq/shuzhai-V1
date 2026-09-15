# -*- coding: utf-8 -*-
import re
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

"""空间一致性检测"""

from backend.services.audit_utils import _line_number
def detect_spatial_consistency(content: str, chapter_index: int = 0,
                               characters: List[Dict] = None) -> List[Dict]:
    """空间一致性检测：角色位置矛盾"""
    issues = []
    if not content or not characters:
        return issues

    paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
    
    # 跟踪每个角色的位置变化
    char_locations = {}
    location_patterns = [
        r'(?:在|来到|回到|抵达|进入|赶往|离开)([^\s，。！？]{2,8}?)(?:城|山|谷|洞|宫|殿|阁|楼|院|府|门|宗|营|寨|塔|桥|关)',
    ]

    for char in characters:
        name = char.get('name', '')
        if not name or name not in content:
            continue
        
        # 记录角色在每段中的位置
        locations = []
        for i, p in enumerate(paragraphs):
            if name in p:
                for pattern in location_patterns:
                    matches = re.findall(pattern, p)
                    for loc in matches:
                        locations.append((i, loc.strip()))
        
        # 检测位置矛盾：同一时间段内出现在不同地点
        if len(locations) >= 2:
            for i in range(1, len(locations)):
                prev_para, prev_loc = locations[i-1]
                curr_para, curr_loc = locations[i]
                # 如果在相邻段落中出现在完全不同的地点
                if curr_para - prev_para <= 2 and prev_loc and curr_loc and prev_loc != curr_loc:
                    # 检查是否有移动描述
                    movement = any(m in content for m in ['飞', '瞬移', '传送', '赶往', '前往', '奔向'])
                    if not movement:
                        issues.append({
                            'type': 'spatial_consistency',
                            'character': name,
                            'location': _line_number(content, content.find(paragraphs[curr_para])) if curr_para < len(paragraphs) else 0,
                            'message': f'角色{name}可能存在位置矛盾：从"{prev_loc}"到"{curr_loc}"缺少移动描述'
                        })
                        break

    return issues[:3]


