# -*- coding: utf-8 -*-
import re
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

"""位置提取辅助函数"""

def _line_number(content: str, pos: int) -> int:
    """计算字符偏移对应的行号（1-based）"""
    return content[:pos].count('\n') + 1


def _paragraph_index(content: str, pos: int) -> int:
    """计算字符偏移对应的段落索引（0-based）"""
    text_before = content[:pos]
    # 按空白行分段
    paras = [p for p in text_before.split('\n') if p.strip()]
    return len(paras)


def _context_snippet(content: str, pos: int, span: int = 20) -> str:
    """提取位置周围的上下文片段"""
    start = max(0, pos - span)
    end = min(len(content), pos + span)
    snippet = content[start:end].replace('\n', ' ')
    return snippet


def _find_all_positions(content: str, pattern: str) -> List[Dict]:
    """用正则查找所有匹配位置，返回 [{line, offset, matched, context}]"""
    locations = []
    for m in re.finditer(pattern, content):
        pos = m.start()
        locations.append({
            'line': _line_number(content, pos),
            'offset': pos,
            'matched': m.group(),
            'context': _context_snippet(content, pos)
        })
    return locations


def _find_word_positions(content: str, word: str) -> List[Dict]:
    """查找关键词所有出现位置"""
    locations = []
    start = 0
    lw = len(word)
    while True:
        idx = content.find(word, start)
        if idx == -1:
            break
        locations.append({
            'line': _line_number(content, idx),
            'offset': idx,
            'matched': word,
            'context': _context_snippet(content, idx)
        })
        start = idx + lw
    return locations

