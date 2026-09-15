# -*- coding: utf-8 -*-
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

"""设定冲突检测"""

from backend.services.audit_utils import _line_number
def detect_setting_conflict(content: str, chapter_index: int = 0,
                            world_settings: Dict = None) -> List[Dict]:
    """设定冲突检测：正文与世界观设定矛盾"""
    issues = []
    if not content:
        return issues

    # 通用时代/科技冲突检测
    ancient_markers = ['马车', '客栈', '镖局', '科举', '皇帝', '宫中', '城门', '骑马']
    modern_markers = ['手机', '电脑', '电视', '汽车', '飞机', '网络', 'APP', '微信', '电梯', '空调']
    scifi_markers = ['飞船', '星舰', '量子', '光年', '银河', '星际', '机甲', '人工智能']

    ancient_count = sum(content.count(m) for m in ancient_markers)
    modern_count = sum(content.count(m) for m in modern_markers)
    scifi_count = sum(content.count(m) for m in scifi_markers)

    # 如果古代和现代标记同时出现较多，可能存在设定冲突
    if ancient_count > 3 and modern_count > 2:
        # 找到第一个现代标记
        for mm in modern_markers:
            pos = content.find(mm)
            if pos >= 0:
                issues.append({
                    'type': 'setting_conflict',
                    'location': _line_number(content, pos),
                    'message': f'检测到古代设定中出现了现代物品"{mm}"，可能存在时代设定冲突'
                })
                break

    if ancient_count > 3 and scifi_count > 2:
        for sm in scifi_markers:
            pos = content.find(sm)
            if pos >= 0:
                issues.append({
                    'type': 'setting_conflict',
                    'location': _line_number(content, pos),
                    'message': f'检测到古代设定中出现了科幻元素"{sm}"，可能存在设定冲突'
                })
                break

    # 如果传入了世界设定，检查特定冲突
    if world_settings:
        era = world_settings.get('era', '')
        if '古代' in era or '修仙' in era or '仙侠' in era:
            for mm in modern_markers:
                if mm in content:
                    pos = content.find(mm)
                    issues.append({
                        'type': 'setting_conflict',
                        'location': _line_number(content, pos),
                        'message': f'世界观设定为{era}，但出现了"{mm}"'
                    })
                    break

    return issues[:3]


