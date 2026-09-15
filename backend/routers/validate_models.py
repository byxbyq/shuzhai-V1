# -*- coding: utf-8 -*-
import re
import logging
from pydantic import BaseModel
from typing import Optional, Dict


logger = logging.getLogger(__name__)

# 局部修复 - 纯函数（原 local_fix.py，已内联）
# ═══════════════════════════════════════════
# 可自动局部修复的检查类型（不涉及跨章节）
LOCAL_FIXABLE = [
    'style', 'pacing', 'foreshadowing', 'characterization',
    'worldview', 'logic', 'consistency', 'sensory'
]
# 跨章节问题，不自动修复
CROSS_CHAPTER = ['plot', 'timeline', 'theme']

# 修复指令模板
FIX_TEMPLATES = {
    'style': '请重写这段文字，保持剧情不变，仅调整文风，要求：{suggestion}',
    'pacing': '请重写这段文字，调整节奏感，要求：{suggestion}',
    'foreshadowing': '请重写这段文字，修正伏笔处理，要求：{suggestion}',
    'characterization': '请重写这段文字，使角色行为更符合人设，要求：{suggestion}',
    'worldview': '请重写这段文字，修正与世界观不符之处，要求：{suggestion}',
    'logic': '请重写这段文字，修正逻辑漏洞，要求：{suggestion}',
    'consistency': '请重写这段文字，修正前后矛盾，要求：{suggestion}',
    'sensory': '请重写这段文字，增强感官描写，要求：{suggestion}',
}


def _split_paragraphs(content: str):
    """按空行或换行切分段落，保留非空段落。"""
    if not content:
        return []
    # 先按双换行分，再对每段按单换行分（处理不同格式）
    parts = content.split('\n\n')
    result = []
    for p in parts:
        p = p.strip()
        if p:
            # 如果段落内还有单换行，进一步拆分
            sub_parts = p.split('\n')
            for sp in sub_parts:
                sp = sp.strip()
                if sp:
                    result.append(sp)
    return result


def _find_paragraph_by_index(paragraphs, location: str):
    """根据位置描述（如"第3段"）找到段落索引。"""
    if not location:
        return -1
    m = re.search(r'第\s*(\d+)\s*段', location)
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(paragraphs):
            return idx
    return -1


def _locate_problem_paragraphs(content: str, location: str, problem: str):
    """定位问题段落，返回 (start, end, strategy, paragraphs)。

    6种定位策略：精确段落号 → 关键词匹配 → 空行分段 → 原文返回
    """
    paragraphs = _split_paragraphs(content)
    if not paragraphs:
        return -1, -1, 'no_content', []

    # 策略1：精确段落号
    idx = _find_paragraph_by_index(paragraphs, location)
    if idx >= 0:
        return idx, idx, 'exact_index', paragraphs

    # 策略2：从 location 中提取场景关键词，在段落中查找
    keywords = []
    if location:
        for kw in location.replace('，', ' ').replace(',', ' ').split():
            kw = kw.strip()
            if len(kw) >= 2:
                keywords.append(kw)
    if keywords:
        matches = [i for i, p in enumerate(paragraphs)
                   if all(kw in p for kw in keywords[:3])]
        if matches:
            return matches[0], matches[-1], 'keyword_match', paragraphs

    # 策略3：从 problem 描述中提取关键词
    if problem:
        problem_kws = []
        for kw in problem.replace('，', ' ').replace(',', ' ').split():
            kw = kw.strip()
            if len(kw) >= 2:
                problem_kws.append(kw)
        if problem_kws:
            matches = [i for i, p in enumerate(paragraphs)
                       if any(kw in p for kw in problem_kws[:3])]
            if matches:
                return matches[0], matches[-1], 'problem_keyword', paragraphs

    # 策略4：无法定位，返回首段（保守）
    if len(paragraphs) == 1:
        return 0, 0, 'single_paragraph', paragraphs

    # 策略5：返回-1，跳过修复
    return -1, -1, 'not_located', paragraphs


def _build_fix_instruction(check_type: str, problem: str, suggestion: str) -> str:
    """构建修复指令。"""
    tpl = FIX_TEMPLATES.get(check_type, '请重写这段文字，解决问题：{suggestion}')
    return tpl.format(suggestion=suggestion or problem or '保持剧情，仅修复问题')


class ValidateRequest(BaseModel):
    content: str
    context: Optional[Dict] = None
    index: int = -1
    memory: str = ""


class AIFlavorRequest(BaseModel):
    content: str


class StyleExtractRequest(BaseModel):
    text: str
    source_name: str = ""


class StyleCompareRequest(BaseModel):
    content: str
    fingerprint: dict


class PowerCollapseRequest(BaseModel):
    content: str
    chapter_index: int = 0


class ExtendedAuditRequest(BaseModel):
    content: str = ""
    chapter_index: int = 0


class ConsistencyRequest(BaseModel):
    content: str = ""
    index: int = -1


class OutlineQualityRequest(BaseModel):
    """全书大纲质量检查 — 对 state.project 全量数据评估"""
    pass


class SettingsQualityRequest(BaseModel):
    """世界观设定质量检查 — 对 state.project 全量数据评估"""
    pass


class CharactersQualityRequest(BaseModel):
    """人物档案质量检查 — 对 state.project 全量数据评估"""
    pass


class EditorialReviewRequest(BaseModel):
    """AI责编评分请求 — 读者视角多维评分"""
    content: str
    mode: Optional[str] = "reader_focus"


class MarketReviewRequest(BaseModel):
    """市场向评分请求"""
    content: str


class AllInOneRequest(BaseModel):
    """19维合并检查请求"""
    content: str
    context: Optional[Dict] = None
    index: int = -1
    memory: str = ""


# ═══════════════════════════════════════════
# AI责编评分 — 评分模式定义
# ═══════════════════════════════════════════

EDITORIAL_PROMPT_MODES = {
    "beginner": "考虑作者可能是新手，对基础能力给予适当认可。",
    "editor": "关注编辑质量，检查标点、段落组织和结构完整性。",
    "reader_focus": "从读者追读意愿角度评价，重点关注节奏感和爽点密度。",
    "market": "从市场表现角度评价，重点关注类型适配和商业化潜力。",
    "evidence": "所有评价必须基于文本证据，引用具体段落作为评分依据。",
}


