# -*- coding: utf-8 -*-
"""
书斋 V66 — JSON 校验修复模块

当 JSON 解析失败时自动尝试修复，按顺序应用 4 种修复策略，
最多重试 4 次（每种策略一次），每次记录使用的修复策略。

公开函数:
    repair_json(json_str: str) -> tuple[dict|list|None, list[str]]
        - 返回 (修复后的对象, 修复步骤列表)
        - 修复成功返回解析后的 dict 或 list，全部失败返回 (None, 步骤列表)
"""

import json
import re
from typing import Union, Optional, Tuple, List


def _remove_trailing_commas(s: str) -> str:
    """策略①：去掉尾部多余逗号（对象和数组中的尾逗号）"""
    # 去掉 }, ] 之前的逗号，如 {"a":1,} -> {"a":1}
    s = re.sub(r',\s*([]}])', r'\1', s)
    return s


def _close_brackets(s: str) -> str:
    """策略②：补全缺失的右括号/右花括号/右引号"""
    # 统计未闭合的括号
    stack: List[str] = []
    in_string = False
    escape = False
    for ch in s:
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ('{', '['):
            stack.append(ch)
        elif ch == '}':
            if stack and stack[-1] == '{':
                stack.pop()
            else:
                # 不匹配，不做处理
                pass
        elif ch == ']':
            if stack and stack[-1] == '[':
                stack.pop()
    # 补全缺失的闭合符号
    closing = ''
    for opener in reversed(stack):
        if opener == '{':
            closing += '}'
        elif opener == '[':
            closing += ']'
    return s + closing


def _truncate_to_last_valid(s: str) -> str:
    """策略③：截断到最后一个合法值再补闭合"""
    # 尝试找到最后一个完整的 JSON 值位置
    # 从后往前找最后一个 }, ], ", 数字或关键字
    # 简单策略：移除最后不完整的内容，然后尝试补闭合

    # 先找最后一个完整的结构结束位置
    # 尝试从末尾向前搜索最后一个 } 或 ] 或 " 或数字/字母
    stripped = s.rstrip()
    if not stripped:
        return s

    # 如果以逗号结尾，去掉逗号
    if stripped.endswith(','):
        stripped = stripped[:-1].rstrip()

    # 尝试找到最后一个完整的 token
    # 在 } 或 ] 之后，或者最后一个引号/数字之后
    last_valid = len(stripped)
    depth = 0
    in_str = False
    esc = False

    for i in range(len(stripped) - 1, -1, -1):
        ch = stripped[i]
        if esc:
            esc = False
            continue
        if ch == '\\':
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in ('}', ']'):
            depth += 1
        elif ch in ('{', '['):
            depth -= 1
            if depth < 0:
                # 这里有一个未闭合的开括号，从这里截断
                last_valid = i
                break

    truncated = stripped[:last_valid]
    # 补闭合
    return _close_brackets(truncated)


def _extract_last_json_block(s: str) -> Optional[str]:
    """策略④：尝试提取最后一个完整的 JSON 对象或数组"""
    # 找最后一个 { 或 [
    last_brace = s.rfind('{')
    last_bracket = s.rfind('[')
    start = max(last_brace, last_bracket)
    if start == -1:
        return None

    # 从 start 开始尝试解析到末尾
    candidate = s[start:]
    # 尝试逐步截断来找到有效的 JSON 块
    for end in range(len(candidate), 0, -1):
        sub = candidate[:end]
        # 补闭合
        sub = _close_brackets(sub)
        try:
            json.loads(sub)
            return sub
        except json.JSONDecodeError:
            continue
    return None


def repair_json(json_str: str) -> Tuple[Union[dict, list, None], List[str]]:
    """尝试修复损坏的 JSON 字符串。

    按顺序应用 4 种修复策略，每种策略只尝试一次（共最多 4 次）。
    每次修复后立即解析验证，成功则返回结果。

    Args:
        json_str: 可能损坏的 JSON 字符串

    Returns:
        (修复后的对象, 修复步骤列表)
        - 成功: (dict 或 list, ["策略①：去掉尾部逗号"])
        - 全部失败: (None, ["策略①失败", "策略②失败", ...])
    """
    steps: List[str] = []

    # 先尝试直接解析
    try:
        obj = json.loads(json_str)
        return obj, ["直接解析成功"]
    except json.JSONDecodeError:
        pass

    strategies = [
        ("去掉尾部多余逗号", _remove_trailing_commas),
        ("补全缺失的右括号/右花括号", _close_brackets),
        ("截断到最后一个合法值再补闭合", _truncate_to_last_valid),
        ("提取最后一个完整的JSON对象/数组", _extract_last_json_block),
    ]

    current = json_str

    for i, (name, func) in enumerate(strategies):
        try:
            if i < 3:
                # 策略①②③：对当前字符串应用修复函数
                repaired = func(current)
                if repaired == current:
                    # 修复函数没有改变字符串，跳过
                    steps.append(f"策略{i+1}「{name}」未产生变化，跳过")
                    continue
                obj = json.loads(repaired)
                steps.append(f"策略{i+1}「{name}」修复成功")
                return obj, steps
            else:
                # 策略④：提取最后完整 JSON 块
                extracted = func(current)
                if extracted is not None:
                    obj = json.loads(extracted)
                    steps.append(f"策略{i+1}「{name}」提取成功")
                    return obj, steps
                else:
                    steps.append(f"策略{i+1}「{name}」未找到可提取的JSON块")
        except json.JSONDecodeError:
            steps.append(f"策略{i+1}「{name}」失败")
        except Exception as e:
            steps.append(f"策略{i+1}「{name}」异常: {e}")

    return None, steps
