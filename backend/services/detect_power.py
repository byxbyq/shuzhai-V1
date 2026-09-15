# -*- coding: utf-8 -*-
import re
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

"""战力崩坏检测"""

# ═══════════════════════════════════════════
# 战力崩坏检测
# ═══════════════════════════════════════════

REALM_HIERARCHY = [
    '凡人', '觉醒', '入门', '初级', '中级', '高级',
    '超凡', '蜕变', '蜕变期', '入微', '化境', '巅峰',
    '仙', '神', '圣', '至尊', '创世', '归零',
]


def detect_power_collapse(content: str, chapter_index: int = 0,
                          characters: List[Dict] = None) -> Dict:
    """战力崩坏检测 - 基于角色状态和正文内容"""
    if not content:
        return {'score': 0, 'level': 'ok', 'issues': [], 'summary': 'no content'}

    issues = []
    total_deduction = 0

    # 1. Realm jump detection
    if characters:
        for char in characters:
            name = char.get('name', '')
            realm = char.get('realm', '')
            prev_realm = char.get('prev_realm', '')

            if realm and prev_realm:
                try:
                    curr_idx = REALM_HIERARCHY.index(realm) if realm in REALM_HIERARCHY else -1
                    prev_idx = REALM_HIERARCHY.index(prev_realm) if prev_realm in REALM_HIERARCHY else -1
                    if curr_idx >= 0 and prev_idx >= 0:
                        jump = curr_idx - prev_idx
                        if jump > 2:
                            issues.append({
                                'type': 'realm_jump',
                                'character': name,
                                'from': prev_realm,
                                'to': realm,
                                'jump': jump,
                                'message': name + ' realm jumped from ' + prev_realm + ' to ' + realm + ' (' + str(jump) + ' levels)'
                            })
                            total_deduction += min(20, jump * 5)
                except (ValueError, IndexError):
                    pass

            # 2. Dead character revival (skip archived characters)
            status = char.get('status', '')
            archived = char.get('archived', False)
            if status == 'dead' and not archived and name and name in content:
                revival_keywords = ['复活', '重生', '苏醒', '诈尸', '未死', '还活着']
                has_revival = any(kw in content for kw in revival_keywords)
                if not has_revival:
                    # 上下文感知：检查是否在回忆/提及语境中
                    mention_contexts = ['回忆', '想起', '记得', '记忆中', '当年', '曾经', '往事', '梦中', '闪回', '提到', '说起', '墓', '碑', '遗', '画像', '缅怀']
                    loc = content.find(name)
                    context = content[max(0, loc-30):loc+len(name)+30] if loc >= 0 else ''
                    in_mention = any(mc in context for mc in mention_contexts)
                    if not in_mention:
                        issues.append({
                            'type': 'dead_revival',
                            'character': name,
                            'message': 'dead character ' + name + ' appears without revival description'
                        })
                        total_deduction += 15

    # 3. Realm mentions in content
    realm_mentions = {}
    for realm in REALM_HIERARCHY:
        if realm in content:
            count = content.count(realm)
            realm_mentions[realm] = count

    # 4. Victory mismatch detection
    victory_patterns = [
        r'(.{1,8})击败了(.{1,8})',
        r'(.{1,8})战胜了(.{1,8})',
        r'(.{1,8})杀了(.{1,8})',
    ]
    for pattern in victory_patterns:
        matches = re.findall(pattern, content)
        for winner, loser in matches:
            winner_realm = None
            loser_realm = None
            for realm in REALM_HIERARCHY:
                if realm in winner:
                    winner_realm = realm
                if realm in loser:
                    loser_realm = realm
            if winner_realm and loser_realm:
                w_idx = REALM_HIERARCHY.index(winner_realm)
                l_idx = REALM_HIERARCHY.index(loser_realm)
                if l_idx - w_idx > 2:
                    issues.append({
                        'type': 'power_mismatch',
                        'winner': winner.strip(),
                        'loser': loser.strip(),
                        'winner_realm': winner_realm,
                        'loser_realm': loser_realm,
                        'message': winner.strip() + '(' + winner_realm + ') defeated ' + loser.strip() + '(' + loser_realm + ') - cross-level victory'
                    })
                    total_deduction += 10

    score = min(100, total_deduction)
    if score == 0:
        level = 'ok'
    elif score <= 20:
        level = 'warning'
    else:
        level = 'serious'

    summary = 'Power consistency: ' + str(100 - score) + '/100 (' + level + ')'
    if issues:
        top = [i['message'] for i in issues[:3]]
        summary += '. Issues: ' + '; '.join(top)

    return {
        'score': score,
        'level': level,
        'issues': issues,
        'summary': summary,
        'realm_mentions': realm_mentions
    }

