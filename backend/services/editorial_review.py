# -*- coding: utf-8 -*-
import re
import logging
from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.project_service import get_generator
from backend.api_models import err, ErrorCode
from backend.routers.validate_models import EditorialReviewRequest, MarketReviewRequest, EDITORIAL_PROMPT_MODES

logger = logging.getLogger(__name__)


router = APIRouter()

# ═══════════════════════════════════════════
# AI责编评分 — 内部函数
# ═══════════════════════════════════════════

def _do_editorial_review(content: str, mode: str = "reader_focus") -> dict:
    """执行AI责编评分 — 内部函数，供端点与 generator.py 共享"""
    import json as _json
    mode_instruction = EDITORIAL_PROMPT_MODES.get(mode, EDITORIAL_PROMPT_MODES["reader_focus"])

    prompt = f"""你是书斋AI责编，对网文章节进行读者视角的多维评分。每个维度评分1-5分（整数）。

{mode_instruction}

【评分维度与标准】

🎭 人物塑造力：
1分：角色沦为工具人，毫无个性
2分：角色扁平，标签化严重
3分：性格清晰但缺乏深度
4分：主角有心理变化和独特风格
5分：立体复杂的人物群像，读者可共情

💔 情感穿透力：
1分：缺乏情绪，人物如空壳
2分：情感流于表面，刻意煽情
3分：情感表达中规中矩
4分：角色情感真实可信，有感染力
5分：极高情感浓度，自然克制而深刻

🔀 情节反转密度：
1分：情节平直无起伏
2分：偶有转折但可预测
3分：情节发展合理但缺乏惊喜
4分：设置反转悬念，结局有不可预期性
5分：多层递进连锁翻转，持续高能

🌍 主题深度：
1分：堆砌设定无思想内核
2分：浅层主题，如简单道德寓言
3分：主旨明确但缺乏深度挖掘
4分：探讨有张力的中心主题
5分：触及人类存在根本悖论，引发哲学级反思

🎨 文体魅力：
1分：语言毫无章法，病句频出
2分：平淡如白开水
3分：通顺但无特色
4分：风格成熟，偶有金句
5分：高度独特风格，不可替代

⚡ 爽点密度：
1分：无爽点，平淡无奇
2分：偶尔有轻微爽感
3分：平均每2000字一个爽点
4分：每1000字一个小高潮
5分：每500字一个情绪高峰，读者欲罢不能

【输出要求】
请严格输出以下JSON格式（不要输出其他内容）：

{{
  "dimensions": [
    {{"name": "人物塑造力", "score": 整数1-5, "description": "一句话评分理由"}},
    {{"name": "情感穿透力", "score": 整数1-5, "description": "一句话评分理由"}},
    {{"name": "情节反转密度", "score": 整数1-5, "description": "一句话评分理由"}},
    {{"name": "主题深度", "score": 整数1-5, "description": "一句话评分理由"}},
    {{"name": "文体魅力", "score": 整数1-5, "description": "一句话评分理由"}},
    {{"name": "爽点密度", "score": 整数1-5, "description": "一句话评分理由"}}
  ],
  "strengths": ["优势1", "优势2", "优势3"],
  "improvements": ["改进1", "改进2", "改进3"],
  "overall_comment": "总体评价（100字内）"
}}

【待评文章节内容】
{content[:8000]}"""

    gen = get_generator()
    if not gen:
        return {"ok": False, "error": "生成器未初始化"}
    raw = gen.ai.generate(prompt)
    try:
        result = _json.loads(raw)
        return {"ok": True, **result}
    except _json.JSONDecodeError:
        # 尝试从输出中提取JSON块
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            try:
                result = _json.loads(m.group(0))
                return {"ok": True, **result}
            except _json.JSONDecodeError:
                pass
        return {"ok": False, "error": "AI返回格式解析失败", "raw": raw}


def _do_market_review(content: str) -> dict:
    """执行市场向评分 — 内部函数"""
    import json as _json
    prompt = f"""你是书斋AI市场编辑，从商业和市场角度评价网文章节。

【评分维度与标准】

📖 追读意愿（章节结束时的钩子强度）：
1分：毫无悬念，读者无继续阅读欲望
2分：结尾略有悬念但冲击力不足
3分：结尾有基本悬念设置
4分：结尾设置有力钩子，读者想继续
5分：强烈断章钩子，读者不读完睡不着

🎯 类型适配度（是否符合目标类型的读者预期）：
1分：完全不匹配任何类型特征
2分：类型模糊，读者预期混乱
3分：基本符合类型框架但缺乏亮点
4分：类型特征鲜明，满足读者预期
5分：类型标杆，完美命中读者期待

🔥 传播潜力（内容是否自带话题性）：
1分：无任何话题基因
2分：偶有可讨论点但缺乏传播力
3分：有一定讨论价值
4分：具备明显话题性，易引发讨论
5分：自带传播基因，适合社交平台引爆

【输出要求】
请严格输出以下JSON格式（不要输出其他内容）：

{{
  "dimensions": [
    {{"name": "追读意愿", "score": 整数1-5, "description": "一句话评分理由"}},
    {{"name": "类型适配度", "score": 整数1-5, "description": "一句话评分理由"}},
    {{"name": "传播潜力", "score": 整数1-5, "description": "一句话评分理由"}}
  ],
  "strengths": ["市场优势1", "市场优势2"],
  "improvements": ["市场改进1", "市场改进2"],
  "overall_comment": "市场总体评价（100字内）"
}}

【待评文章节内容】
{content[:8000]}"""

    gen = get_generator()
    if not gen:
        return {"ok": False, "error": "生成器未初始化"}
    raw = gen.ai.generate(prompt)
    try:
        result = _json.loads(raw)
        return {"ok": True, **result}
    except _json.JSONDecodeError:
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            try:
                result = _json.loads(m.group(0))
                return {"ok": True, **result}
            except _json.JSONDecodeError:
                pass
        return {"ok": False, "error": "AI返回格式解析失败", "raw": raw}



# ═══════════════════════════════════════════
# AI责编评分端点
# ═══════════════════════════════════════════

# ═══════════════════════════════════════════
# AI责编评分端点
# ═══════════════════════════════════════════

@router.post("/editorial-review")
def validate_editorial_review(data: EditorialReviewRequest):
    """AI责编评分 — 6维读者视角评分 + 5种模式切换"""
    if not data.content:
        return err(ErrorCode.VALIDATION_ERROR, "缺少content")
    mode = data.mode or "reader_focus"
    if mode not in EDITORIAL_PROMPT_MODES:
        return err(ErrorCode.VALIDATION_ERROR, f"无效的评分模式: {mode}，支持: {list(EDITORIAL_PROMPT_MODES.keys())}")
    result = _do_editorial_review(data.content, mode)
    if not result.get("ok"):
        return err(ErrorCode.INTERNAL_ERROR, result.get("error", "评分失败"))
    return {"ok": True, "mode": mode, **{k: v for k, v in result.items() if k != "ok"}}


@router.post("/market-review")
def validate_market_review(data: MarketReviewRequest):
    """市场向评分 — 3维（追读意愿/类型适配度/传播潜力）"""
    if not data.content:
        return err(ErrorCode.VALIDATION_ERROR, "缺少content")
    result = _do_market_review(data.content)
    if not result.get("ok"):
        return err(ErrorCode.INTERNAL_ERROR, result.get("error", "评分失败"))
    return {"ok": True, **{k: v for k, v in result.items() if k != "ok"}}


# ============================================================
# AI 修复 API
# ============================================================

class FixParagraphRequest(BaseModel):
    chapter_index: int
    paragraph_index: int
    issue_type: str
    issue: str
    suggestion: str


