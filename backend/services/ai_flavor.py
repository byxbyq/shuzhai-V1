# -*- coding: utf-8 -*-
import re
import math
import logging
from typing import Dict
from collections import Counter

logger = logging.getLogger(__name__)

"""AI味检测 + 评分"""

from backend.services.audit_utils import (
    _line_number, _context_snippet,
    _find_all_positions, _find_word_positions,
)
from backend.services.audit_vocab import (
    AI_BUZZWORDS, FORMULAIC_TRANSITIONS, NARRATOR_OVERREACH, PLASTIC_PATTERNS,
    NEGATIVE_PIVOT_PATTERNS, FORMULAIC_MODIFIER_PATTERNS, DIALOGUE_TAGS,
    SUBLIMATION_PATTERNS, GOD_VIEW_PATTERNS, ENGINEERING_WORDS,
)

def detect_ai_flavor(content: str) -> Dict:
    """AI味检测 - 统计特征分析 + 规则检测"""
    if not content or len(content) < 100:
        return {'score': 0, 'level': 'clean', 'issues': [], 'summary': 'content too short',
                'stats': {}, 'ai_probability': 0}

    char_count = len(content)
    scale = max(char_count / 3000.0, 1.0)
    issues = []
    total_deduction = 0

    # ═══════════════════════════════════════
    # Part A: 统计特征分析（模拟真实AI检测器）
    # ═══════════════════════════════════════

    # 按句号、感叹号、问号、换行分句
    raw_sentences = re.split(r'[。！？\n]+', content)
    sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 2]

    sentence_lengths = [len(s) for s in sentences]
    n_sentences = len(sentence_lengths)

    # A1. 突发性(Burstiness)：人类写作句子长短差异大，AI趋于均匀
    burstiness_score = 0
    mean_len = 0
    cv = 0
    if n_sentences > 10:
        mean_len = sum(sentence_lengths) / n_sentences
        variance = sum((l - mean_len) ** 2 for l in sentence_lengths) / n_sentences
        std_dev = math.sqrt(variance)
        cv = std_dev / mean_len if mean_len > 0 else 0  # 变异系数

        # 人类写作CV通常 > 0.6, AI通常 < 0.4
        if cv < 0.3:
            burstiness_score = 25
            issues.append({
                'type': 'low_burstiness',
                'cv': round(cv, 3),
                'scope': 'global',
                'message': '句子长度过于均匀(变异系数%.2f)，AI特征明显' % cv
            })
        elif cv < 0.45:
            burstiness_score = 15
            issues.append({
                'type': 'low_burstiness',
                'cv': round(cv, 3),
                'scope': 'global',
                'message': '句子长度较均匀(变异系数%.2f)，偏AI风格' % cv
            })
        elif cv < 0.6:
            burstiness_score = 7
        # cv >= 0.6 人类风格，不扣分
    total_deduction += burstiness_score

    # A2. 词汇多样性(Type-Token Ratio)：AI用词重复率高
    # 用2-gram字符级计算
    chars_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z]', '', content)
    if len(chars_clean) > 200:
        # 字符级2-gram
        bigrams = [chars_clean[i:i+2] for i in range(len(chars_clean) - 1)]
        unique_bigrams = len(set(bigrams))
        total_bigrams = len(bigrams)
        ttr = unique_bigrams / total_bigrams if total_bigrams > 0 else 0

        # 中文文本2-gram TTR通常 0.55-0.75，AI偏低
        if ttr < 0.45:
            total_deduction += 15
            issues.append({
                'type': 'low_ttr',
                'ttr': round(ttr, 3),
                'scope': 'global',
                'message': '词汇多样性低(2-gram TTR=%.2f)，用词重复率高' % ttr
            })
        elif ttr < 0.50:
            total_deduction += 8
            issues.append({
                'type': 'low_ttr',
                'ttr': round(ttr, 3),
                'scope': 'global',
                'message': '词汇多样性偏低(2-gram TTR=%.2f)' % ttr
            })

    # A3. 段落长度均匀性：AI段落长度趋同
    paragraphs = [p.strip() for p in content.split('\n') if len(p.strip()) > 20]
    para_uniformity_score = 0
    if len(paragraphs) > 5:
        para_lens = [len(p) for p in paragraphs]
        para_mean = sum(para_lens) / len(para_lens)
        para_cv = math.sqrt(sum((l - para_mean) ** 2 for l in para_lens) / len(para_lens)) / para_mean if para_mean > 0 else 0

        if para_cv < 0.25:
            para_uniformity_score = 12
            issues.append({
                'type': 'uniform_paragraphs',
                'cv': round(para_cv, 3),
                'scope': 'global',
                'message': '段落长度过于均匀(变异系数%.2f)，AI排版特征' % para_cv
            })
        elif para_cv < 0.40:
            para_uniformity_score = 6
    total_deduction += para_uniformity_score

    # A4. 句式重复度：AI倾向使用相似句式结构
    pattern_repetition_score = 0
    if n_sentences > 15:
        # 检测句首模式重复
        sentence_starts = [s[:3] for s in sentences if len(s) >= 3]
        start_counter = Counter(sentence_starts)
        repeated_starts = sum(1 for v in start_counter.values() if v >= 3)
        if repeated_starts >= 3:
            pattern_repetition_score = 10
            top_pattern = start_counter.most_common(1)[0]
            issues.append({
                'type': 'pattern_repetition',
                'scope': 'global',
                'message': '句首模式重复过多，"%s…"出现%d次' % (top_pattern[0], top_pattern[1])
            })
        elif repeated_starts >= 2:
            pattern_repetition_score = 5
    total_deduction += pattern_repetition_score

    # A5. 连接词密度：AI过度使用连接词
    connectors = ['然而', '因此', '但是', '不过', '于是', '随后', '紧接着',
                  '与此同时', '不仅如此', '事实上', '实际上', '换句话说',
                  '总而言之', '综上所述', '由此可见']
    connector_count = sum(content.count(c) for c in connectors)
    connector_density = connector_count / (char_count / 1000)
    connector_score = 0
    if connector_density > 5:
        connector_score = min(12, int((connector_density - 5) * 3))
        issues.append({
            'type': 'connector_overuse',
            'count': connector_count,
            'density': round(connector_density, 1),
            'scope': 'global',
            'message': '连接词密度过高(%.1f/千字)，AI行文特征' % connector_density
        })
    total_deduction += connector_score

    # A6. "的"字密度：AI生成中文"的"字频率偏高
    de_count = content.count('的')
    de_density = de_count / (char_count / 1000)
    de_score = 0
    if de_density > 35:
        de_score = min(10, int((de_density - 35) * 1.5))
        issues.append({
            'type': 'high_de_density',
            'density': round(de_density, 1),
            'scope': 'global',
            'message': '"的"字密度过高(%.1f/千字)，AI行文特征' % de_density
        })
    total_deduction += de_score

    # ═══════════════════════════════════════
    # Part B: 规则检测（原有逻辑）
    # ═══════════════════════════════════════

    # B1. Buzzword density
    for word, max_per_3k in AI_BUZZWORDS.items():
        count = content.count(word)
        if count == 0:
            continue
        allowed = max_per_3k * scale
        locations = _find_word_positions(content, word)
        if max_per_3k == 0 and count > 0:
            deduction = min(15, 5 + count * 3)
            issues.append({
                'type': 'buzzword_forbidden',
                'word': word,
                'count': count,
                'locations': locations,
                'message': '[forbidden] word "' + word + '" appears ' + str(count) + ' times'
            })
            total_deduction += deduction
        elif count > allowed:
            excess = int(count - allowed)
            deduction = min(10, excess * 2)
            issues.append({
                'type': 'buzzword_density',
                'word': word,
                'count': count,
                'limit': int(allowed),
                'locations': locations,
                'message': 'word "' + word + '" appears ' + str(count) + ' times (limit ' + str(int(allowed)) + ' per 3k chars)'
            })
            total_deduction += deduction

    # B2. Formulaic transitions
    transition_count = 0
    all_transition_locs = []
    for pattern in FORMULAIC_TRANSITIONS:
        locs = _find_all_positions(content, pattern)
        if locs:
            transition_count += len(locs)
            all_transition_locs.extend(locs)
            if len(locs) > 1:
                issues.append({
                    'type': 'formulaic_transition',
                    'pattern': pattern,
                    'count': len(locs),
                    'locations': locs,
                    'message': 'formulaic transition repeated ' + str(len(locs)) + ' times'
                })
                total_deduction += min(5, len(locs) * 2)

    if transition_count > 3 * scale:
        issues.append({
            'type': 'transition_overuse',
            'count': transition_count,
            'locations': all_transition_locs,
            'message': 'total formulaic transitions: ' + str(transition_count) + ', density too high'
        })
        total_deduction += 5

    # B3. Narrator overreach
    overreach_count = 0
    all_overreach_locs = []
    for pattern in NARRATOR_OVERREACH:
        locs = _find_all_positions(content, pattern)
        if locs:
            overreach_count += len(locs)
            all_overreach_locs.extend(locs)
            issues.append({
                'type': 'narrator_overreach',
                'pattern': locs[0]['matched'] if locs else pattern,
                'count': len(locs),
                'locations': locs,
                'message': 'narrator overreach: "' + (locs[0]['matched'] if locs else pattern) + '" draws conclusion for reader'
            })
            total_deduction += min(8, len(locs) * 3)

    # B4. Plastic prose
    plastic_count = 0
    all_plastic_locs = []
    for pattern in PLASTIC_PATTERNS:
        locs = _find_all_positions(content, pattern)
        if locs:
            plastic_count += len(locs)
            all_plastic_locs.extend(locs)
    if plastic_count > 5 * scale:
        issues.append({
            'type': 'plastic_prose',
            'count': plastic_count,
            'locations': all_plastic_locs,
            'message': 'parallel/antithesis patterns: ' + str(plastic_count) + ', too uniform'
        })
        total_deduction += 5

    # B5. Monotonous sentence starts
    if n_sentences > 10:
        same_start = 0
        for i in range(1, n_sentences):
            if sentences[i][:2] == sentences[i-1][:2]:
                same_start += 1
        if same_start > n_sentences * 0.2:
            ratio = round(same_start / n_sentences, 2)
            issues.append({
                'type': 'monotonous_sentence',
                'count': same_start,
                'ratio': ratio,
                'scope': 'global',
                'message': str(same_start) + ' consecutive sentences with same start (' + str(int(ratio * 100)) + '%)'
            })
            total_deduction += 5

    # ═══════════════════════════════════════
    # Part B2: oh-story 7Gate 确定性预检（零Token）
    # ═══════════════════════════════════════

    # Gate B: 否定铺垫句式（最毒AI句式）
    negative_pivot_count = 0
    all_neg_pivot_locs = []
    for pattern in NEGATIVE_PIVOT_PATTERNS:
        locs = _find_all_positions(content, pattern)
        if locs:
            negative_pivot_count += len(locs)
            all_neg_pivot_locs.extend(locs)
            issues.append({
                'type': 'negative_pivot',
                'gate': 'B',
                'pattern': locs[0]['matched'][:20] if locs else pattern,
                'count': len(locs),
                'locations': locs,
                'message': 'Gate B 否定铺垫句式: "' + (locs[0]['matched'][:20] if locs else pattern) + '..." 出现' + str(len(locs)) + '次，建议直接写后项'
            })
            total_deduction += min(10, len(locs) * 4)

    # Gate B: 万能状语句式
    for pattern in FORMULAIC_MODIFIER_PATTERNS:
        locs = _find_all_positions(content, pattern)
        if len(locs) > 2:
            issues.append({
                'type': 'formulaic_modifier',
                'gate': 'B',
                'pattern': pattern,
                'count': len(locs),
                'locations': locs,
                'message': 'Gate B 万能状语句式: 出现' + str(len(locs)) + '次，建议用独立短句或动作描写'
            })
            total_deduction += min(6, len(locs) * 2)

    # Gate E: 对话标签密度
    dialogue_sentences = re.findall(r'[""「」『』].*?[""「」『』]', content)
    dialogue_tag_count = 0
    all_tag_locs = []
    for tag in DIALOGUE_TAGS:
        locs = _find_word_positions(content, tag)
        if locs:
            dialogue_tag_count += len(locs)
            all_tag_locs.extend(locs)
    if dialogue_sentences and len(dialogue_sentences) > 5:
        dialogue_tag_ratio = dialogue_tag_count / len(dialogue_sentences)
        if dialogue_tag_ratio > 0.5:
            issues.append({
                'type': 'dialogue_tag_density',
                'gate': 'E',
                'count': dialogue_tag_count,
                'ratio': round(dialogue_tag_ratio, 2),
                'locations': all_tag_locs,
                'message': 'Gate E 对话标签密度过高(' + str(round(dialogue_tag_ratio * 100)) + '%)，建议用动作替代"说道/问道"'
            })
            total_deduction += min(10, int((dialogue_tag_ratio - 0.5) * 20))

    # Gate F: 结尾升华
    sublimation_count = 0
    all_sublim_locs = []
    for pattern in SUBLIMATION_PATTERNS:
        locs = _find_all_positions(content, pattern)
        if locs:
            sublimation_count += len(locs)
            all_sublim_locs.extend(locs)
    if sublimation_count > 0:
        issues.append({
            'type': 'sublimation_ending',
            'gate': 'F',
            'count': sublimation_count,
            'locations': all_sublim_locs,
            'message': 'Gate F 结尾升华句式: 检测到' + str(sublimation_count) + '处总结/升华/点题，建议用动作/场景收尾'
        })
        total_deduction += min(8, sublimation_count * 3)

    # Gate G: 解释腔/上帝感/安排感
    god_view_count = 0
    all_god_locs = []
    for pattern in GOD_VIEW_PATTERNS:
        locs = _find_all_positions(content, pattern)
        if locs:
            god_view_count += len(locs)
            all_god_locs.extend(locs)
            issues.append({
                'type': 'god_view',
                'gate': 'G',
                'pattern': locs[0]['matched'][:20] if locs else pattern,
                'count': len(locs),
                'locations': locs,
                'message': 'Gate G 解释腔/上帝感: "' + (locs[0]['matched'][:20] if locs else pattern) + '..." 叙述者越权解释/剧透/定性'
            })
            total_deduction += min(12, len(locs) * 4)

    # 退化检测：工程词泄漏
    engineering_hits = []
    all_eng_locs = []
    for word in ENGINEERING_WORDS:
        locs = _find_word_positions(content, word)
        if locs:
            engineering_hits.append(word)
            all_eng_locs.extend(locs)
    if engineering_hits:
        issues.append({
            'type': 'engineering_word_leak',
            'gate': 'degeneration',
            'words': engineering_hits,
            'count': len(engineering_hits),
            'locations': all_eng_locs,
            'message': '退化检测: 工程词泄漏 ' + ', '.join(engineering_hits[:3])
        })
        total_deduction += min(20, len(engineering_hits) * 8)

    # 退化检测：重复段落（逐字复读）
    if len(paragraphs) > 3:
        seen_paras = set()
        duplicate_paras = []
        dup_locations = []
        para_idx = 0
        for p in paragraphs:
            p_key = p[:50]  # 取前50字作为指纹
            if p_key in seen_paras and len(p) > 30:
                duplicate_paras.append(p[:30])
                # 查找该段落在原文中的位置
                idx = content.find(p[:30])
                if idx >= 0:
                    dup_locations.append({
                        'line': _line_number(content, idx),
                        'offset': idx,
                        'matched': p[:30],
                        'context': _context_snippet(content, idx)
                    })
            seen_paras.add(p_key)
            para_idx += 1
        if duplicate_paras:
            issues.append({
                'type': 'duplicate_paragraph',
                'gate': 'degeneration',
                'count': len(duplicate_paras),
                'locations': dup_locations,
                'message': '退化检测: 逐字复读段落 ' + str(len(duplicate_paras)) + '处'
            })
            total_deduction += min(15, len(duplicate_paras) * 5)

    # ═══════════════════════════════════════
    # Part C: 综合评分
    # ═══════════════════════════════════════

    score = min(100, total_deduction)

    # 估算AI概率（基于统计特征）
    ai_prob = 0
    mean_len = 0
    cv = 0
    if n_sentences > 10:
        mean_len = sum(sentence_lengths) / n_sentences
        variance = sum((l - mean_len) ** 2 for l in sentence_lengths) / n_sentences
        cv = math.sqrt(variance) / mean_len if mean_len > 0 else 0
        # CV越低AI概率越高
        if cv < 0.3: ai_prob += 40
        elif cv < 0.4: ai_prob += 25
        elif cv < 0.5: ai_prob += 15
        elif cv < 0.6: ai_prob += 5

    # TTR
    chars_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z]', '', content)
    if len(chars_clean) > 200:
        bigrams = [chars_clean[i:i+2] for i in range(len(chars_clean) - 1)]
        ttr = len(set(bigrams)) / len(bigrams) if bigrams else 0
        if ttr < 0.45: ai_prob += 25
        elif ttr < 0.50: ai_prob += 15
        elif ttr < 0.55: ai_prob += 8

    # 段落均匀性
    if len(paragraphs) > 5:
        para_lens = [len(p) for p in paragraphs]
        para_mean = sum(para_lens) / len(para_lens)
        para_cv = math.sqrt(sum((l - para_mean) ** 2 for l in para_lens) / len(para_lens)) / para_mean if para_mean > 0 else 0
        if para_cv < 0.25: ai_prob += 15
        elif para_cv < 0.35: ai_prob += 8

    # 连接词
    if connector_density > 5: ai_prob += 10
    # "的"字密度
    if de_density > 35: ai_prob += 8

    ai_prob = min(99, ai_prob)

    if score == 0:
        level = 'clean'
    elif score <= 15:
        level = 'minor'
    elif score <= 35:
        level = 'moderate'
    else:
        level = 'heavy'

    # AI概率等级
    if ai_prob >= 70:
        ai_level = 'high'
    elif ai_prob >= 40:
        ai_level = 'medium'
    elif ai_prob >= 20:
        ai_level = 'low'
    else:
        ai_level = 'minimal'

    summary = 'AI味评分: ' + str(score) + '/100 (' + level + ')'
    summary += ' | 预估AI概率: ' + str(ai_prob) + '% (' + ai_level + ')'
    if issues:
        top_issues = [i['message'] for i in issues[:3]]
        summary += '. 主要问题: ' + '; '.join(top_issues)

    return {
        'score': score,
        'level': level,
        'ai_probability': ai_prob,
        'ai_level': ai_level,
        'issues': issues,
        'summary': summary,
        'stats': {
            'burstiness_cv': round(cv, 3) if n_sentences > 10 else 0,
            'ttr': round(ttr, 3) if len(chars_clean) > 200 else 0,
            'para_cv': round(para_cv, 3) if len(paragraphs) > 5 else 0,
            'connector_density': round(connector_density, 1),
            'de_density': round(de_density, 1),
            'sentence_count': n_sentences,
            'avg_sentence_len': round(mean_len, 1) if n_sentences > 0 else 0,
            'buzzword_total': sum(1 for i in issues if 'buzzword' in i['type']),
            'transition_total': transition_count,
            'overreach_total': overreach_count,
            'plastic_total': plastic_count,
            'negative_pivot_total': negative_pivot_count,
            'dialogue_tag_ratio': round(dialogue_tag_count / len(dialogue_sentences), 2) if dialogue_sentences and len(dialogue_sentences) > 5 else 0,
            'sublimation_total': sublimation_count,
            'god_view_total': god_view_count,
            'gate_b_hits': negative_pivot_count + sum(1 for i in issues if i.get('type') == 'formulaic_modifier'),
            'gate_e_hits': sum(1 for i in issues if i.get('gate') == 'E'),
            'gate_f_hits': sublimation_count,
            'gate_g_hits': god_view_count,
        }
    }


def compute_ai_score(ai_result: Dict) -> Dict:
    """聚合降熵评分：基于7个Gate检测结果计算加权综合AI概率

    权重分配：TTR×0.3 + 禁用词×0.25 + 公式化句式×0.2 + 工程词×0.1
            + 上帝视角×0.05 + 结尾升华×0.05 + 否定铺垫×0.05
    """
    stats = ai_result.get('stats', {})
    issues = ai_result.get('issues', [])

    # Gate scores (0-100, higher = more AI-like)
    # A1: TTR (词汇多样性) — 反向映射，TTR越低AI概率越高
    ttr = stats.get('ttr', 0.5)
    ttr_score = max(0, min(100, int((0.6 - ttr) * 250)))

    # B1: Buzzword/禁用词密度
    buzzword_total = stats.get('buzzword_total', 0)
    buzzword_score = min(100, buzzword_total * 12)

    # B2: 公式化句式
    transition_total = stats.get('transition_total', 0)
    formulaic_score = min(100, transition_total * 8)

    # 退化: 工程词泄漏
    gate_degen = stats.get('gate_degen_hits', 0)
    eng_score = min(100, gate_degen * 25)

    # Gate G: 上帝视角
    gate_g = stats.get('gate_g_hits', 0)
    god_score = min(100, gate_g * 20)

    # Gate F: 结尾升华
    gate_f = stats.get('gate_f_hits', 0)
    sublim_score = min(100, gate_f * 25)

    # Gate B: 否定铺垫
    gate_b = stats.get('gate_b_hits', 0)
    neg_score = min(100, gate_b * 15)

    score = int(
        ttr_score * 0.30 +
        buzzword_score * 0.25 +
        formulaic_score * 0.20 +
        eng_score * 0.10 +
        god_score * 0.05 +
        sublim_score * 0.05 +
        neg_score * 0.05
    )
    score = min(100, score)

    if score <= 20:
        level = 'low'
    elif score <= 50:
        level = 'medium'
    else:
        level = 'high'

    return {'ai_score': score, 'ai_level': level}

