# -*- coding: utf-8 -*-
"""结构扰动清洗（text_perturb）单元测试"""
import re

from backend.services.text_perturb import perturb_text


def _strip_punct(text: str) -> str:
    """去掉所有标点和空白，只留文字（用于内容不变性比对）"""
    return re.sub(r'[，。！？；、：:""''（）《》…—\s\-,.!?;:\'"]', '', text)


# 构造一段典型的"AI味"长文本：句式均匀、段落工整
_SAMPLE = '\n'.join([
    '林凡缓缓地抬起头，望着眼前这座巍峨的山门，心中不禁涌起一阵复杂的情绪，他知道从这一刻起，自己的命运将彻底改变，再也没有回头路可走了。',
    '他深吸一口气，迈步走上了石阶，每一级石阶都仿佛在诉说着千年的沧桑，阳光洒在他的身上，拉出一道长长的影子，宛如一柄出鞘的利剑。',
    '山门之内，一名白衣老者负手而立，他的目光深邃而悠远，仿佛能看透人心，见到林凡走来，老者微微颔首，嘴角浮现出一抹淡淡的微笑，似乎对这位年轻人的到来早有预料。',
    '“你来了。”老者的声音平淡而温和，却带着一股不容置疑的威严，“从今日起，你便是我青云宗的弟子，望你勤勉修行，莫要堕了宗门的名头。”',
])


def test_content_preserved():
    """扰动只动标点和换行，文字内容一个不少"""
    out = perturb_text(_SAMPLE, seed=42)
    assert _strip_punct(out) == _strip_punct(_SAMPLE)


def test_perturbation_applied():
    """对足够长的文本，扰动必须产生实际变化（句号增多或段落变多）"""
    out = perturb_text(_SAMPLE, intensity=1.0, seed=7)
    changed = (out.count('。') > _SAMPLE.count('。')) or (len(out.split('\n')) > len(_SAMPLE.split('\n')))
    assert changed, "扰动未产生任何结构变化"


def test_deterministic_with_seed():
    """相同种子结果可复现"""
    a = perturb_text(_SAMPLE, seed=123)
    b = perturb_text(_SAMPLE, seed=123)
    assert a == b


def test_short_text_untouched():
    """短文本（<200字）原样返回"""
    short = '他抬起头，望向远方。'
    assert perturb_text(short) == short


def test_empty_input():
    assert perturb_text('') == ''
    assert perturb_text(None) is None
