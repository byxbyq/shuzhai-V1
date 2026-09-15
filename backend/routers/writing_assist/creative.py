# -*- coding: utf-8 -*-
import json
import re
import logging
from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.project_service import state, get_generator
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)

creative_router = APIRouter(prefix="/api/creative")

def _get_genre_title():
    """获取当前项目的题材与标题"""
    if not state.project:
        return "小说", ""
    genre = state.project.meta.get("genre", "小说") or "小说"
    title = state.project.meta.get("title", "")
    return genre, title

def _build_full_context(user_context: str, extra_chars: int = 500) -> str:
    """构建上下文：用户传入的上下文 + 当前章节前后文"""
    parts = []
    if user_context and user_context.strip():
        parts.append(user_context.strip()[:1000])
    if state.project:
        cur_idx = state.project.meta.get("current_chapter", 0)
        if 0 <= cur_idx < len(state.project.chapters):
            content = state.project.get_content(cur_idx) or ""
            if content:
                parts.append("【当前章节内容参考】\n" + content[:extra_chars * 2])
    return "\n\n".join(parts) if parts else ""

def _clean_ai_output(text: str) -> str:
    """清理AI输出：去掉markdown代码块包裹"""
    if not text:
        return ""
    text = text.strip()
    # 去掉开头的 ```text / ```markdown 等标记
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


# -- Describe（描写增强） --

DESCRIBE_TYPE_MAP = {
    "sensory": "感官细节（视觉/听觉/嗅觉/触觉/味觉），让读者身临其境",
    "environment": "环境氛围（天气/光影/温度/气味），烘托场景气氛",
    "character": "人物外貌（穿着/表情/小动作），让角色更立体鲜活",
    "action": "动作细节（武术动作/日常动作/微表情），让画面更生动",
}

class DescribeRequest(BaseModel):
    text: str
    type: str = "sensory"  # sensory | environment | character | action
    context: str = ""

@creative_router.post("/describe")
def creative_describe(data: DescribeRequest):
    """AI 增强描写：为选中文本增加指定类型的细节"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    gen = get_generator()
    genre, title = _get_genre_title()
    type_label = DESCRIBE_TYPE_MAP.get(data.type, DESCRIBE_TYPE_MAP["sensory"])
    text = (data.text or "").strip()
    if not text:
        return err(ErrorCode.VALIDATION_ERROR, "请提供需要增强描写的文本")
    context = _build_full_context(data.context)

    prompt = (
        f"你是一个描写增强专家。请为以下文本增加{type_label}，"
        f"保持原意不变，字数可增加50-100%。只返回增强后的段落，不要加任何说明。\n\n"
        f"【作品类型】{genre}小说《{title}》\n"
    )
    if context:
        prompt += f"【上下文参考】\n{context}\n\n"
    prompt += f"【原文】\n{text}\n\n请直接返回增强后的段落："

    try:
        result = gen.ai.generate(prompt)
        cleaned = _clean_ai_output(result)
        if not cleaned:
            return err(ErrorCode.VALIDATION_ERROR, "AI返回结果为空")
        return {"ok": True, "result": cleaned, "original": text}
    except Exception as e:
        logger.warning(f"[Creative/Describe] error: {e}")
        return err(ErrorCode.INTERNAL_ERROR, f"描写增强失败: {e}")


# -- Expand（场景扩写） --

EXPAND_DIRECTION_MAP = {
    "dialogue": "增加对话（补充角色互动，通过对话推动情节和展现性格）",
    "psychology": "增加心理描写（内心独白、情绪波动、思绪流转）",
    "environment": "增加环境描写（场景烘托、氛围渲染、空间细节）",
    "action": "增加动作描写（打斗细节、肢体语言、动作分解）",
    "slow": "放慢节奏（展开时间线，将一瞬间的事拆解为多个层次）",
}

class ExpandRequest(BaseModel):
    text: str
    direction: str = "dialogue"  # dialogue | psychology | environment | action | slow
    multiplier: float = 2.0  # 1.5 / 2 / 3
    context: str = ""

@creative_router.post("/expand")
def creative_expand(data: ExpandRequest):
    """AI 场景扩写：将简略的文本向指定方向扩写"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    gen = get_generator()
    genre, title = _get_genre_title()
    direction_label = EXPAND_DIRECTION_MAP.get(data.direction, EXPAND_DIRECTION_MAP["dialogue"])
    text = (data.text or "").strip()
    if not text:
        return err(ErrorCode.VALIDATION_ERROR, "请提供需要扩写的文本")
    multiplier = max(1.0, min(data.multiplier, 5.0))
    context = _build_full_context(data.context)

    prompt = (
        f"你是一个场景扩写专家。请将以下文本向「{direction_label}」方向扩写，"
        f"目标字数是原文的{multiplier}倍。保持核心内容不变，只返回扩写后的段落。\n\n"
        f"【作品类型】{genre}小说《{title}》\n"
        f"【原文长度】{len(text)}字，目标长度约{int(len(text) * multiplier)}字\n"
    )
    if context:
        prompt += f"【上下文参考】\n{context}\n\n"
    prompt += f"【原文】\n{text}\n\n请直接返回扩写后的段落："

    try:
        result = gen.ai.generate(prompt)
        cleaned = _clean_ai_output(result)
        if not cleaned:
            return err(ErrorCode.VALIDATION_ERROR, "AI返回结果为空")
        return {"ok": True, "result": cleaned, "original": text}
    except Exception as e:
        logger.warning(f"[Creative/Expand] error: {e}")
        return err(ErrorCode.INTERNAL_ERROR, f"场景扩写失败: {e}")


# -- Rewrite（灵活重写） --

REWRITE_STYLE_MAP = {
    "casual": "更口语化（降低书面感，使用日常对话般的语言）",
    "literary": "更文学化（提升文笔，使用更有质感的词句和修辞）",
    "tense": "更紧张感（增加悬念，短句为主，制造压迫感）",
    "relaxed": "更轻松感（增加幽默，语气活泼，适当调侃）",
    "perspective": "换个视角（从另一角色的视角重写同一段落）",
}

class RewriteRequest(BaseModel):
    text: str
    style: str = "literary"  # casual | literary | tense | relaxed | perspective | custom
    custom_instruction: str = ""
    context: str = ""
    single_version: bool = False  # 局部修复场景：只返回1个版本，避免多版本混合

@creative_router.post("/rewrite")
def creative_rewrite(data: RewriteRequest):
    """AI 灵活重写：用指定风格重写文本，返回3个候选版本

    single_version=True 时只生成1个版本（用于局部修复场景，避免多版本混合）
    """
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    gen = get_generator()
    genre, title = _get_genre_title()
    text = (data.text or "").strip()
    if not text:
        return err(ErrorCode.VALIDATION_ERROR, "请提供需要重写的文本")

    if data.style == "custom" and data.custom_instruction.strip():
        style_label = data.custom_instruction.strip()
    else:
        style_label = REWRITE_STYLE_MAP.get(data.style, REWRITE_STYLE_MAP["literary"])

    context = _build_full_context(data.context)

    if data.single_version:
        # 局部修复场景：只生成1个版本，prompt 严格约束
        prompt = (
            f"你是文本修复专家。请按以下指令修复这段文字，"
            f"只返回修复后的完整文本，不要返回多个版本，不要加任何说明或版本号。\n\n"
            f"【作品类型】{genre}小说《{title}》\n"
            f"【修复指令】{style_label}\n"
        )
        if context:
            prompt += f"【上下文参考】\n{context}\n\n"
        prompt += (
            f"【原文】\n{text}\n\n"
            f"要求：\n"
            f"1. 严格按修复指令修改，不要自行发挥\n"
            f"2. 保留原文未涉及修复的部分，不改动\n"
            f"3. 不引入原文没有的人物、设定、情节\n"
            f"4. 直接输出修复后的完整段落，不要任何前后缀说明\n"
        )
    else:
        # 默认场景：3个版本（用户交互用）
        prompt = (
            f"你是一个文本重写专家。请用「{style_label}」风格重写以下文本。"
            f"提供3个不同的重写版本，用---分隔。只返回重写后的文本，不要加版本号或说明。\n\n"
            f"【作品类型】{genre}小说《{title}》\n"
        )
        if context:
            prompt += f"【上下文参考】\n{context}\n\n"
        prompt += f"【原文】\n{text}\n\n请返回3个重写版本（用---分隔）："

    try:
        result = gen.ai.generate(prompt)
        cleaned = _clean_ai_output(result)
        if not cleaned:
            return err(ErrorCode.VALIDATION_ERROR, "AI返回结果为空")

        if data.single_version:
            # 单版本场景：清理可能的多版本残留
            # 如果AI还是返回了 --- 分隔的多个版本，只取第一个
            if '---' in cleaned:
                versions = re.split(r'\n*---\n*', cleaned)
                versions = [v.strip() for v in versions if v.strip()]
                versions = versions[:1]
            else:
                versions = [cleaned.strip()]
        else:
            # 按 --- 分割为多个版本
            versions = re.split(r'\n*---\n*', cleaned)
            versions = [v.strip() for v in versions if v.strip()]
            # 如果AI没有按格式分割，至少返回1个版本
            if not versions:
                versions = [cleaned]
            # 最多保留3个
            versions = versions[:3]
        return {"ok": True, "versions": versions, "original": text, "count": len(versions)}
    except Exception as e:
        logger.warning(f"[Creative/Rewrite] error: {e}")
        return err(ErrorCode.INTERNAL_ERROR, f"灵活重写失败: {e}")


# -- Feedback（5维反馈） --
FEEDBACK_DIMENSIONS = [
    "情感张力", "节奏感", "画面感", "对话自然度", "悬念设置",
]

class FeedbackRequest(BaseModel):
    content: str
    chapter_index: int = -1

@creative_router.post("/feedback")
def creative_feedback(data: FeedbackRequest):
    """AI 5维反馈：对文本进行5维度评分和改进建议（不修改原文）"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    gen = get_generator()
    genre, title = _get_genre_title()
    content = (data.content or "").strip()
    if not content:
        # 如果未提供内容，使用当前章节
        if data.chapter_index >= 0 and data.chapter_index < len(state.project.chapters):
            content = state.project.get_content(data.chapter_index) or ""
        else:
            cur_idx = state.project.meta.get("current_chapter", 0)
            if 0 <= cur_idx < len(state.project.chapters):
                content = state.project.get_content(cur_idx) or ""
    if not content:
        return err(ErrorCode.VALIDATION_ERROR, "请提供需要反馈的内容")
    # 限制长度避免token超限
    content = content[:6000]

    prompt = (
        f"你是一个专业的小说编辑。请对以下文本从5个维度评分(0-10)并给出具体改进建议。\n\n"
        f"【作品类型】{genre}小说《{title}》\n"
        f"【待评估文本】\n{content}\n\n"
        f"5个评估维度：\n"
        f"1. 情感张力（是否有情绪起伏，能否引发读者共鸣）\n"
        f"2. 节奏感（快慢交替是否自然，是否存在拖沓或仓促）\n"
        f"3. 画面感（是否有生动的视觉画面，场景是否立体）\n"
        f"4. 对话自然度（对话是否符合角色身份和性格，是否生硬）\n"
        f"5. 悬念设置（是否有吸引读者的钩子，信息释放节奏是否合理）\n\n"
        f"返回JSON格式（只返回JSON，不要解释）：\n"
        f'{{"dimensions": ['
        f'{{"name": "情感张力", "score": 8, "suggestion": "具体改进建议"}},'
        f'{{"name": "节奏感", "score": 7, "suggestion": "具体改进建议"}},'
        f'{{"name": "画面感", "score": 9, "suggestion": "具体改进建议"}},'
        f'{{"name": "对话自然度", "score": 6, "suggestion": "具体改进建议"}},'
        f'{{"name": "悬念设置", "score": 7, "suggestion": "具体改进建议"}}'
        f'], "overall_score": 7.4, "summary": "总体评价（100字以内）"}}'
    )

    try:
        result = gen.ai.generate(prompt)
        clean = result.replace("```json", "").replace("```", "").strip()
        feedback_data = None
        try:
            feedback_data = json.loads(clean)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', clean)
            if match:
                try:
                    feedback_data = json.loads(match.group())
                except Exception:
                    pass
        if not feedback_data:
            # 降级：返回原始文本
            return {**err(ErrorCode.AI_FAILED, "AI返回结果无法解析"), "raw": clean[:500]}
        # 校验并补全结构
        dims = feedback_data.get("dimensions", [])
        if not isinstance(dims, list) or len(dims) == 0:
            return {**err(ErrorCode.AI_FAILED, "AI返回的维度数据格式异常"), "raw": clean[:500]}
        # 确保每个维度有 score 和 suggestion
        for d in dims:
            if "score" not in d:
                d["score"] = 5
            d["score"] = max(0, min(10, float(d["score"])))
            if "suggestion" not in d:
                d["suggestion"] = ""
        # 计算 overall_score（如果AI没给）
        if "overall_score" not in feedback_data or not feedback_data["overall_score"]:
            scores = [d["score"] for d in dims]
            feedback_data["overall_score"] = round(sum(scores) / len(scores), 1) if scores else 0
        if "summary" not in feedback_data:
            feedback_data["summary"] = ""
        return {"ok": True, **feedback_data}
    except Exception as e:
        logger.warning(f"[Creative/Feedback] error: {e}")
        return err(ErrorCode.INTERNAL_ERROR, f"5维反馈失败: {e}")
