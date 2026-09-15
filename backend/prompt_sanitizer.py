# -*- coding: utf-8 -*-
"""
书斋 V66 - Prompt注入防护：用户输入清洗 + 结构化封装 + 可配置危险词

提供两个函数：
- sanitize_user_input(text): 完整清洗（过滤危险短语 + <user_input>标签封装）
- sanitize_light(text): 轻量清洗（仅过滤危险短语，不封装标签）

用户可通过 data/sanitizer_config.json 手动增删危险词，调用 reload_config() 热重载。
"""

import re
import json
import os
import logging

logger = logging.getLogger(__name__)

# 默认危险指令性短语（中英）——保守列表，仅拦截明确越权元指令
# 不拦截"指令""系统""prompt"等正常词，避免误伤小说创作场景
_DEFAULT_INJECTION_PATTERNS = [
    # 明确越权指令
    r'(?i)ignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions?',
    r'忽略(?:以上|上面|前面|之前)(?:所有)?(?:指令|提示|规则|要求)',
    r'不要遵守(?:以上|上面|前面)',
    r'(?:以上|上面的?内容?)作废',
    # 身份越权
    r'(?i)you\s+are\s+(?:now|a)\s+(?:system|admin|developer|root|DAN)',
    r'你(?:现在)?是(?:系统|admin|开发者|root|管理员)',
    r'(?i)DAN\s*模式',
    r'假装你(?:是|没有)',
    r'(?i)pretend\s+(?:you\s+are|to\s+be)',
    r'(?i)没有(?:限制|约束|filter|restriction)',
    r'进入(?:开发者|越狱|jailbreak|developer)\s*模式',
    # 提示词泄露
    r'(?i)reveal\s+(?:your\s+)?(?:system\s+)?prompt',
    r'(?i)show\s+(?:me\s+)?(?:your\s+)?(?:system\s+)?(?:prompt|instruction)',
    r'输出(?:你的)?(?:系统|原始|初始)?(?:提示词|prompt|instruction)',
    r'重复(?:你的)?(?:系统|原始)?(?:提示|prompt)',
    r'(?i)system\s*message',
    # 结构化标记注入（模拟角色标记）
    r'(?i)(?:system|user|assistant)\s*[:：]',
    r'(?i)</?\s*(?:system|instruction|prompt)\s*>',
    r'(?i)###\s*(?:system|系统)',
]

# 正则编译缓存
_COMPILED = None

# 配置文件路径：项目根目录下的 data/sanitizer_config.json
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.path.join(_PROJECT_ROOT, 'data', 'sanitizer_config.json')

# 结构化封装标签（声明为数据非指令）
_DATA_TAG = "user_input"


def _load_patterns():
    """加载默认+用户配置的危险词列表，编译为正则"""
    global _COMPILED
    if _COMPILED is not None:
        return _COMPILED
    patterns = list(_DEFAULT_INJECTION_PATTERNS)
    # 加载用户自定义配置
    try:
        if os.path.exists(_CONFIG_PATH):
            with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                # 用户追加的自定义规则
                extra = cfg.get('extra_patterns', [])
                if isinstance(extra, list):
                    patterns.extend(extra)
                # 用户禁用的某些默认规则（按完整正则字符串匹配）
                disabled = set(cfg.get('disabled_patterns', []))
                if disabled:
                    patterns = [p for p in patterns if p not in disabled]
    except Exception as e:
        logger.warning("[sanitizer] 配置加载失败，使用默认列表: %s", e)

    _COMPILED = []
    for p in patterns:
        try:
            _COMPILED.append(re.compile(p))
        except re.error as e:
            logger.warning("[sanitizer] 正则编译失败，跳过 '%s': %s", p, e)
    return _COMPILED


def _filter_dangerous(text: str) -> str:
    """过滤危险短语，替换为[已过滤]"""
    for pat in _load_patterns():
        text = pat.sub('[已过滤]', text)
    return text


def sanitize_user_input(text, max_len=8000):
    """
    完整清洗：用于直接注入Prompt的用户输入（如用户指令、灵感碎片）。
    1. 去首尾空白
    2. 长度截断
    3. 危险指令短语替换为[已过滤]
    4. 结构化封装：<user_input>...</user_input>
    """
    if not text:
        return ""
    s = str(text).strip()
    if len(s) > max_len:
        s = s[:max_len] + "…[截断]"
    s = _filter_dangerous(s)
    return f"<{_DATA_TAG}>\n{s}\n</{_DATA_TAG}>"


def sanitize_light(text, max_len=8000):
    """
    轻量清洗：仅strip+截断+过滤危险短语，不封装标签。
    用于已是结构化字段的场景（如JSON内的值），或内容性文本（如选段、章节正文）。
    """
    if not text:
        return ""
    s = str(text).strip()
    if len(s) > max_len:
        s = s[:max_len] + "…[截断]"
    s = _filter_dangerous(s)
    return s


def reload_config():
    """重新加载配置（用户修改sanitizer_config.json后调用）"""
    global _COMPILED
    _COMPILED = None
    _load_patterns()
    logger.info("[sanitizer] 配置已重载，当前规则数: %d", len(_COMPILED) if _COMPILED else 0)
