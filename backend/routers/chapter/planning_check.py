# -*- coding: utf-8 -*-
import re
import json
from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.project_service import state
from backend.api_models import err, ErrorCode
import logging
from backend.ai_client import AIClient

from ._utils import _smart_truncate

logger = logging.getLogger(__name__)

router = APIRouter()

planning_router = APIRouter(prefix="/api/planning")

@planning_router.get("/matrix")
def planning_matrix():
    """返回矩阵视图数据：卷 × 章节 × 字数 × 状态 × POV"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    data = state.project.get_planning_matrix()
    return {"ok": True, **data}

@planning_router.get("/timeline")
def planning_timeline():
    """返回时间线视图数据：角色出场 × 伏笔埋设/回收 × 章节序号"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    data = state.project.get_planning_timeline()
    return {"ok": True, **data}


# ═══════════════════════════════════════════════════════════════════
# 章节检查路由 - /api/check/*  (原 chapter_check.py)
# ═══════════════════════════════════════════════════════════════════

check_router = APIRouter(prefix="/api/check")

class CompletenessRequest(BaseModel):
    content: str
    title: str = ""
    expected_length: str = ""  # 如 "2000-4000字"

class ContinuityRequest(BaseModel):
    chapter_a: str  # 前一章内容
    chapter_b: str  # 后一章内容
    title_a: str = ""
    title_b: str = ""

def _ai_check(prompt: str) -> dict:
    """调AI做分析，返回结构化JSON"""
    ai = AIClient()
    raw = ai.generate(prompt)
    # 剥离think标签
    raw = re.sub(r'<think\b.*?</think\b\s*>', '', raw, flags=re.DOTALL)
    raw = re.sub(r'```json\s*', '', raw)
    raw = re.sub(r'```\s*', '', raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 尝试提取JSON块（使用括号配对避免嵌套花括号误截断）
        start = -1
        for i, ch in enumerate(raw):
            if ch == '{':
                start = i
                break
        if start >= 0:
            depth = 0
            for i in range(start, len(raw)):
                if raw[i] == '{':
                    depth += 1
                elif raw[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(raw[start:i+1])
                        except Exception:
                            break
        return {"error": "AI返回格式异常", "raw": raw[:500]}

@check_router.post("/completeness")
def check_completeness(data: CompletenessRequest):
    """检查单章正文是否完整：有开头/发展/结尾，情绪曲线，字数
    ⚠ 注意：本检查的5个维度（结构/情绪/字数/收束/张力）与 audit.py 中
    completeness/wordcount/twist/style 等维度存在评估重叠。当两个端点对同一内容
    给出不同结论时，以 audit.py 的 audited_score 为准（权重体系更完整）。
    长期建议：统一到 audit.py 维度体系中，check_completeness 仅作快速概览。"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")

    content = data.content.strip()
    if len(content) < 100:
        return err(ErrorCode.INTERNAL_ERROR, "内容太短，至少100字")

    title = data.title or "当前章节"
    expected = data.expected_length or "2000-4000字"

    prompt = f"""你是资深小说编辑。请对以下章节正文进行完整性分析。

## 章节标题
{title}

## 目标字数
{expected}

## 章节正文
{_smart_truncate(content, 5000)}

## 分析要求
从以下5个维度评估，每个维度给0-10分，并给出具体说明：

1. **结构完整度**：是否有清晰的开头（引入情境）、发展（推进事件）、结尾（收束或钩子）？是否有明显的截断感？
2. **情绪曲线**：情绪是否有起伏变化？是否有低谷和高峰？是否一直平铺直叙？
3. **信息密度**：是否有足够的情节推进/角色发展/世界观展示？是否有明显的水文段落？
4. **字数健康度**：与目标字数是否匹配？是否过短或过长？
5. **可读性**：段落结构是否合理？对话和描写的比例是否恰当？

## 输出格式
严格输出JSON，不要任何解释：
{{
  "overall_score": 平均分(0-10),
  "overall_level": "优秀/良好/一般/需改进",
  "word_count": 实际字数,
  "dimensions": {{
    "structure": {{"score": 分数, "comment": "说明", "issues": ["问题1"]}},
    "emotion_curve": {{"score": 分数, "comment": "说明", "issues": []}},
    "info_density": {{"score": 分数, "comment": "说明", "issues": []}},
    "length_health": {{"score": 分数, "comment": "说明", "issues": []}},
    "readability": {{"score": 分数, "comment": "说明", "issues": []}}
  }},
  "summary": "总体一句话评价",
  "suggestions": ["改进建议1", "改进建议2"]
}}"""

    try:
        result = _ai_check(prompt)
        result["word_count"] = len(content)
        return {"ok": True, "result": result}
    except Exception as e:
        logger.error(f"Completeness check error: {e}")
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")

@check_router.post("/continuity")
def check_continuity(data: ContinuityRequest):
    """检查两章之间的连贯性：情节衔接、角色一致、时间线、伏笔"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")

    a = data.chapter_a.strip()
    b = data.chapter_b.strip()
    if len(a) < 100 or len(b) < 100:
        return err(ErrorCode.INTERNAL_ERROR, "两章内容都至少100字")

    ta = data.title_a or "前一章"
    tb = data.title_b or "后一章"

    prompt = f"""你是资深小说编辑。请检查以下两章之间的连贯性和衔接质量。

## 前一章：{ta}
{a[:3000]}

## 后一章：{tb}
{b[:3000]}

## 分析要求
从以下6个维度评估连贯性，每维度0-10分：

1. **情节衔接**：后一章是否自然承接前一章的结尾？是否有跳跃或断裂？
2. **时间线一致**：时间推进是否合理？有没有时间矛盾？
3. **角色一致性**：同一角色的行为/性格/状态是否连贯？有没有突然转变？
4. **地点/场景过渡**：场景切换是否合理？有没有凭空瞬移？
5. **伏笔/信息承接**：前一章埋的伏笔/信息在后一章是否有呼应或推进？
6. **情绪/节奏衔接**：两章之间的情绪和节奏是否顺畅过渡？

## 输出格式
严格输出JSON：
{{
  "overall_score": 平均分(0-10),
  "overall_level": "优秀/良好/一般/需改进",
  "dimensions": {{
    "plot_flow": {{"score": 分数, "comment": "说明", "gap": "如果有断裂，具体描述"}},
    "timeline": {{"score": 分数, "comment": "说明", "conflict": "如果有时间矛盾"}},
    "character_consistency": {{"score": 分数, "comment": "说明", "issues": []}},
    "scene_transition": {{"score": 分数, "comment": "说明", "issues": []}},
    "foreshadowing": {{"score": 分数, "comment": "说明", "issues": []}},
    "pacing": {{"score": 分数, "comment": "说明", "issues": []}}
  }},
  "summary": "总体一句话评价两章的衔接质量",
  "suggestions": ["改进建议1", "改进建议2"],
  "gap_points": ["具体的断裂点1"]
}}"""

    try:
        result = _ai_check(prompt)
        return {"ok": True, "result": result}
    except Exception as e:
        logger.error(f"Continuity check error: {e}")
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")
