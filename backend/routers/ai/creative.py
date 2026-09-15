# -*- coding: utf-8 -*-
import json, logging, re
from fastapi import APIRouter

from backend.services.project_service import state, get_generator
from backend.api_models import err, ErrorCode
from backend.prompt_sanitizer import sanitize_light

logger = logging.getLogger(__name__)

from ._models import BrainstormRequest, ExpandIdeaRequest, SensoryRequest

router = APIRouter()

@router.post("/brainstorm")
def ai_brainstorm(data: BrainstormRequest):
    """AI 头脑风暴：根据当前章节/主题生成创意情节点（扩展版，支持8+模式，12方向）"""
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    gen = get_generator()
    genre = state.project.meta.get("genre", "小说") or "小说"
    title = state.project.meta.get("title", "")

    # 获取当前章节信息作为上下文
    cur_idx = state.project.meta.get("current_chapter", 0)
    chapter_title = ""
    chapter_content = ""
    if 0 <= cur_idx < len(state.project.chapters):
        chapter_title = state.project.chapters[cur_idx].get("title", "")
        chapter_content = state.project.get_content(cur_idx)[:2000]

    mode_prompts = {
        "plot": "请生成12个不同的情节发展方向，每个方向需要出人意料但又合乎逻辑。考虑伏笔回收、角色弧光和节奏控制。确保方向多样化，涵盖主线推进、支线展开、意外转折等。",
        "character": "请生成12个角色发展的可能性，包括角色关系的转变、内心冲突的展开、角色成长的契机、以及角色暗面的揭示。",
        "conflict": "请生成12个冲突升级方案，包括人际冲突、环境冲突和内心冲突的交织。考虑利益对立、价值观碰撞和资源争夺。",
        "theme": "请生成12个主题深化的方向，将故事的核心主题通过具体事件、象征隐喻和角色选择表达出来。",
        "reverse": "请生成12个反常识发展方向——读者最不可能预期的走向，但细想又在情理之中。打破套路，颠覆预期。",
        "foreshadowing": "请生成12个伏笔回收方案——检查前文埋设的伏笔（如神秘物件、未解对话、异常能力），设计出人意料的回收方式。",
        "arc": "请生成12个角色弧光发展方向——角色在认知、情感、价值观层面的成长或堕落轨迹，通过具体事件体现转变。",
        "pacing": "请生成12个节奏调控方案——包括加速/减速/转折/留白等节奏变化，通过场景切换、信息释放速率和情绪起伏来实现。",
    }

    # 处理自定义模式
    if data.mode == "custom" and data.custom_prompt.strip():
        mode_label = f"请生成{data.count}个方向，要求：{data.custom_prompt.strip()}"
    else:
        mode_label = mode_prompts.get(data.mode, mode_prompts["plot"])
        # 将模式描述中的数量替换为实际请求的数量
        mode_label = mode_label.replace("12个", f"{data.count}个")

    user_topic = sanitize_light(data.topic.strip()) if data.topic.strip() else "基于当前故事进展"
    user_context = sanitize_light(data.context.strip()[:1000]) if data.context.strip() else ""

    prompt = f"""你是一位创意写作顾问。正在为一部{genre}小说《{title}》进行头脑风暴。

【当前章节】第{cur_idx + 1}章 - {chapter_title}
【当前章节内容摘要】
{chapter_content[:1500]}

【用户关注点】{user_topic}
{f"【额外上下文】{user_context}" if user_context else ""}

{mode_label}

请以JSON数组格式返回，每个元素包含：
- "title": 创意标题（10字以内）
- "desc": 详细描述（50-100字）
- "tags": 标签数组（如"伏笔"、"高潮"、"转折"、"反常识"等）
- "impact": 影响等级（high/medium/low）

要求：
1. 每个方向必须独特且不重复
2. 兼顾大胆创新和逻辑自洽
3. 标注好每个方向的影响等级
4. 至少包含3个high影响的方向

只返回JSON数组，不要其他解释。"""

    try:
        result = gen.ai.generate(prompt)
        clean = result.replace("```json", "").replace("```", "").strip()
        # 尝试解析JSON数组
        ideas = None
        try:
            ideas = json.loads(clean)
        except json.JSONDecodeError:
            match = re.search(r'\[[\s\S]*\]', clean)
            if match:
                try:
                    ideas = json.loads(match.group())
                except Exception:
                    pass
        if not ideas or not isinstance(ideas, list):
            # 降级：按行解析
            ideas = []
            for line in clean.split('\n'):
                line = line.strip()
                if line and len(line) > 5:
                    ideas.append({"title": line[:20], "desc": line, "tags": [], "impact": "medium"})
        return {"ok": True, "ideas": ideas[:data.count], "mode": data.mode, "count": len(ideas[:data.count])}
    except Exception as e:
        logger.warning(f"AI brainstorm error: {e}")
        return err(ErrorCode.INTERNAL_ERROR, f"头脑风暴失败: {str(e)}")


# ── 灵感碎片扩展 ──

@router.post("/expand-idea")
def expand_idea(data: ExpandIdeaRequest):
    """灵感碎片扩展：将一个简短的创意点子展开为详细的情节片段"""
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    gen = get_generator()
    genre = state.project.meta.get("genre", "小说") or "小说"
    title = state.project.meta.get("title", "")

    cur_idx = state.project.meta.get("current_chapter", 0)
    chapter_content = ""
    if 0 <= cur_idx < len(state.project.chapters):
        chapter_content = state.project.get_content(cur_idx)[:1500]

    mode_hints = {
        "plot": "将这个创意展开为一段详细的情节大纲（200-300字），包含具体场景、人物行动、冲突细节",
        "character": "将这个创意展开为角色发展详细方案（200-300字），包含角色心理变化、关系演变、关键对话",
        "conflict": "将这个创意展开为冲突场景详细描写（200-300字），包含对立双方立场、冲突升级过程、后果",
        "theme": "将这个创意展开为主题表达方案（200-300字），包含象征意象、角色选择、读者感受设计",
        "reverse": "将这个反常识创意展开为详细走向（200-300字），包含反转铺垫、揭示时机、读者冲击点",
        "foreshadowing": "将这个伏笔回收创意展开为详细方案（200-300字），包含前文伏笔位置、回收方式、情感冲击",
        "arc": "将这个角色弧光创意展开为详细轨迹（200-300字），包含转变契机、中间挣扎、最终状态",
        "pacing": "将这个节奏调控创意展开为详细方案（200-300字），包含场景切换点、信息释放节奏、情绪起伏曲线",
    }

    mode_hint = mode_hints.get(data.mode, mode_hints["plot"])

    prompt = f"""你是一位创意写作顾问。正在为一部{genre}小说《{title}》扩展灵感碎片。

【当前章节内容摘要】
{chapter_content}

【灵感碎片】
标题：{sanitize_light(data.title)}
描述：{sanitize_light(data.desc)}

【额外上下文】{sanitize_light(data.context)}

{mode_hint}

要求：
1. 内容要具体、可操作，不要空泛描述
2. 与当前章节内容自然衔接
3. 保持与已有设定的一致性

直接输出扩展内容，不要解释。"""

    try:
        result = gen.ai.generate(prompt)
        expanded = result.strip()
        if not expanded:
            return err(ErrorCode.VALIDATION_ERROR, "扩展失败：AI返回为空")
        return {"ok": True, "expanded": expanded, "original_title": data.title}
    except Exception as e:
        logger.warning(f"AI expand-idea error: {e}")
        return err(ErrorCode.INTERNAL_ERROR, f"灵感扩展失败: {str(e)}")


# ── 感官描写工具 ──

SENSE_MAP = {
    "visual": "视觉（光影、色彩、动态画面）",
    "auditory": "听觉（声音、节奏、静默）",
    "olfactory": "嗅觉（气味、空气质感）",
    "tactile": "触觉（温度、质感、力度）",
    "gustatory": "味觉（味道、口感）",
}

@router.post("/sensory")
def ai_sensory(data: SensoryRequest):
    """AI 五感描写生成器：根据场景描述生成感官细节"""
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    gen = get_generator()
    genre = state.project.meta.get("genre", "小说") or "小说"

    scene = data.scene.strip()[:2000] if data.scene.strip() else ""
    if not scene:
        # 使用当前章节内容
        cur_idx = state.project.meta.get("current_chapter", 0)
        if 0 <= cur_idx < len(state.project.chapters):
            scene = state.project.get_content(cur_idx)[:1500]
    if not scene:
        return err(ErrorCode.VALIDATION_ERROR, "请提供场景描述")

    style_map = {
        "immersive": "沉浸式（细腻丰富，适合重要场景）",
        "subtle": "克制式（点到为止，适合快节奏段落）",
        "poetic": "诗意式（意境化，适合抒情段落）",
    }
    style_label = style_map.get(data.style, style_map["immersive"])

    if data.sense_type == "all":
        sense_instruction = "请分别为以下五种感官各生成2-3句描写"
        sense_fields = list(SENSE_MAP.keys())
    else:
        sense_instruction = f"请重点生成{SENSE_MAP.get(data.sense_type, '综合感官')}的描写，3-5句"
        sense_fields = [data.sense_type]

    prompt = f"""你是一位精通感官描写的小说家。正在为{genre}小说生成感官细节。

【场景/上下文】
{sanitize_light(scene)}

【描写风格】{style_label}
【任务】{sense_instruction}，使其自然融入故事，避免堆砌形容词。

请以JSON格式返回：
{{
  "visual": "视觉描写段落",
  "auditory": "听觉描写段落",
  "olfactory": "嗅觉描写段落",
  "tactile": "触觉描写段落",
  "gustatory": "味觉描写段落",
  "combined": "将以上感官自然融合的完整段落（150-300字）"
}}

如果某感官不适合当前场景，可用空字符串。只返回JSON，不要解释。"""

    try:
        result = gen.ai.generate(prompt)
        clean = result.replace("```json", "").replace("```", "").strip()
        sensory_data = None
        try:
            sensory_data = json.loads(clean)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', clean)
            if match:
                try:
                    sensory_data = json.loads(match.group())
                except Exception:
                    pass
        if not sensory_data:
            return err(ErrorCode.AI_FAILED, "AI返回结果无法解析")
        return {"ok": True, "sensory": sensory_data, "senses": sense_fields}
    except Exception as e:
        logger.warning(f"AI sensory error: {e}")
        return err(ErrorCode.GENERATION_FAILED, f"感官描写生成失败: {str(e)}")


# ═══════════════════════════════════════════
# AI 代理端点 — 前端不再持有 API Key
# ═══════════════════════════════════════════
