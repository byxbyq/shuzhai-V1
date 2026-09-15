# -*- coding: utf-8 -*-
"""结构扰动清洗 — 纯规则实现，不消耗任何 Token

外部 ML 类 AI 检测器识别的是文本的统计均匀性：句长分布集中、段落节奏平滑、
过渡自然。本模块用"手术式"的标点级扰动直接破坏这些统计特征：

1. 拆超长句：超长句在接近中点的逗号处改为句号，制造句长极端差异
2. 随机断句：普通句子低概率把逗号改句号，产生短句/残句节奏
3. 段落打散：超长段落在句子边界拆成两段，破坏段落长度均匀性

安全保证：只改动标点（，→。）和换行，正文汉字一个不动，
剧情、对话内容、字数实质不变。
"""
import random
import re

__all__ = ["perturb_text"]

# 超长句阈值（字符）、随机断句的句长区间、段落拆分阈值
_LONG_SENTENCE = 80
_MID_SENTENCE_MIN = 20
_LONG_PARAGRAPH = 220


def _cut_long_sentences(paragraph: str, rng: random.Random, intensity: float) -> str:
    """句级扰动：超长句拦腰切断 + 普通句低概率断句"""
    tokens = re.split(r'([。！？])', paragraph)
    out = []
    for j in range(0, len(tokens), 2):
        seg = tokens[j]
        delim = tokens[j + 1] if j + 1 < len(tokens) else ''
        commas = [m.start() for m in re.finditer('，', seg)]
        if len(seg) > _LONG_SENTENCE and len(commas) >= 3:
            # 在接近中点的逗号处切断（带随机偏移，避免固定模式）
            mid = len(seg) // 2
            cut = min(commas, key=lambda p: abs(p - mid) + rng.randint(-8, 8))
            if cut > 8 and len(seg) - cut > 8 and rng.random() < 0.4 + 0.5 * intensity:
                seg = seg[:cut] + '。' + seg[cut + 1:]
        elif _MID_SENTENCE_MIN < len(seg) <= _LONG_SENTENCE and len(commas) >= 2:
            # 普通句低概率断句：制造节奏突变
            if rng.random() < 0.06 + 0.12 * intensity:
                cut = rng.choice(commas)
                if cut > 5 and len(seg) - cut > 5:
                    seg = seg[:cut] + '。' + seg[cut + 1:]
        out.append(seg + delim)
    return ''.join(out)


def _split_long_paragraph(paragraph: str, rng: random.Random, intensity: float) -> list:
    """段落级扰动：超长段落在句子边界拆成两段（约45%处）"""
    if len(paragraph) < _LONG_PARAGRAPH:
        return [paragraph]
    if rng.random() > 0.35 + 0.45 * intensity:
        return [paragraph]
    sentences = re.findall(r'[^。！？]*[。！？]|[^。！？]+$', paragraph)
    if len(sentences) < 4:
        return [paragraph]
    total = sum(len(s) for s in sentences)
    acc, cut_idx = 0, len(sentences) - 1
    for k, s in enumerate(sentences[:-1], start=1):
        acc += len(s)
        if acc >= total * 0.45:
            cut_idx = k
            break
    head = ''.join(sentences[:cut_idx]).strip()
    tail = ''.join(sentences[cut_idx:]).strip()
    if len(head) < 30 or len(tail) < 30:
        return [paragraph]
    return [head, tail]


def perturb_text(content: str, intensity: float = 0.5, seed=None) -> str:
    """对正文做结构扰动清洗。

    Args:
        content: 原始正文
        intensity: 扰动强度 0~1（默认0.5）
        seed: 随机种子（传入相同种子结果可复现，测试用）

    Returns:
        扰动后的正文；短文本（<200字）原样返回
    """
    if not content or len(content) < 200:
        return content
    rng = random.Random(seed)
    intensity = max(0.0, min(1.0, intensity))

    result_paragraphs = []
    for para in content.split('\n'):
        para = para.strip()
        if not para:
            continue
        para = _cut_long_sentences(para, rng, intensity)
        for piece in _split_long_paragraph(para, rng, intensity):
            result_paragraphs.append(piece)
    return '\n'.join(result_paragraphs)
