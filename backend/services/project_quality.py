# -*- coding: utf-8 -*-
import json
import logging
from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.project_service import state, get_generator
from backend.api_models import err, ErrorCode
import asyncio

logger = logging.getLogger(__name__)


from backend.routers.validate_models import OutlineQualityRequest, SettingsQualityRequest, CharactersQualityRequest

# ═══════════════════════════════════════════
# 全书质量检查（大纲 / 设定 / 人物，三者独立）
# ═══════════════════════════════════════════

router = APIRouter()

def _parse_quality_json(raw: str, check_type: str) -> dict:
    """从 AI 返回的文本中提取 JSON，带容错（使用括号配对避免嵌套花括号误截断）"""
    # 查找第一个 '{'，然后使用括号配对找到完整的 JSON 块
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
                        data = json.loads(raw[start:i+1])
                        data["ok"] = True
                        data["check_type"] = check_type
                        return data
                    except (json.JSONDecodeError, ValueError):
                        break  # fall through to fallback
    # 降级：返回原始文本
    return {"ok": True, "check_type": check_type, "result": raw}


@router.post("/outline-quality")
async def validate_outline_quality(data: OutlineQualityRequest):
    """全书大纲质量检查 — 一次性检查全书大纲的结构/节奏/伏笔/逻辑等10个维度"""
    return await asyncio.to_thread(_do_validate_outline_quality, data)


def _do_validate_outline_quality(data: OutlineQualityRequest):
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "no project")

    # ── 收集数据 ──
    # 全书大纲（novel_outline 现在是 Dict）
    novel_outline = getattr(state.project, "novel_outline", {}) or {}
    # 转换为文本用于AI评估
    outline_text = ""
    if novel_outline:
        if isinstance(novel_outline, dict):
            outline_text = json.dumps(novel_outline, ensure_ascii=False, indent=1)
        elif isinstance(novel_outline, list):
            # 兼容旧格式
            outline_text = json.dumps(novel_outline, ensure_ascii=False, indent=1)
    else:
        outline_text = getattr(state.project, "get_outline_text", lambda: "")()
    if not outline_text or not outline_text.strip():
        outline_text = "（暂无全书大纲）"

    # 章节大纲列表
    chapters = getattr(state.project, "chapters", []) or []
    chapter_outlines = []
    for i, ch in enumerate(chapters):
        if isinstance(ch, dict):
            ol = ch.get("outline", "")
            title = ch.get("title", f"第{i+1}章")
            chapter_outlines.append(f"【{title}】{ol.strip() if ol else '（无大纲）'}")
    chapter_outlines_text = "\n\n".join(chapter_outlines) if chapter_outlines else "（暂无章节大纲）"

    # 伏笔数据
    hooks_text = "（暂无伏笔数据）"
    ledger = getattr(state.project, "ledger", None)
    if ledger and hasattr(ledger, "foreshadowing") and ledger.foreshadowing:
        hook_lines = []
        for h in ledger.foreshadowing:
            status_label = {"planted": "已埋设", "active": "激活中", "recovered": "已回收", "abandoned": "已废弃"}.get(h.status, h.status)
            hook_lines.append(f"- [{status_label}] 第{h.planted_chapter}章：{h.content}" + (f"（预计第{h.expected_recovery_chapter}章回收）" if h.expected_recovery_chapter else ""))
        hooks_text = "\n".join(hook_lines)

    # 角色列表
    characters = getattr(state.project, "characters", []) or []
    char_text = ""
    if characters:
        char_lines = []
        for ch in characters:
            if isinstance(ch, dict):
                name = ch.get("name", "")
                identity = ch.get("identity", "") or ch.get("description", "")
                char_lines.append(f"- {name}：{identity}")
        char_text = "\n".join(char_lines) if char_lines else "（暂无角色数据）"
    else:
        char_text = "（暂无角色数据）"

    # 卷信息
    volumes = getattr(state.project, "volumes", []) or []
    volumes_text = ""
    if volumes:
        vol_lines = []
        for v in volumes:
            if isinstance(v, dict):
                vol_lines.append(f"- {v.get('title', '未命名卷')}：第{v.get('start', '?')}-{v.get('end', '?')}章")
        volumes_text = "\n".join(vol_lines)

    prompt = f"""你是资深小说编辑和故事结构专家。请对以下小说大纲进行全面的质量评估。

【全书大纲】
{outline_text[:5000]}

【卷结构】
{volumes_text if volumes_text.strip() else '（暂无分卷）'}

【章节大纲（共{len(chapter_outlines)}章）】
{chapter_outlines_text[:6000]}

【伏笔数据】
{hooks_text}

【角色列表】
{char_text}

请从以下10个维度逐项评分（每项1-10分），并给出详细的分析：

1. **结构完整性**：全书是否有明确的起承转合/开端发展高潮结局
2. **卷结构合理性**：各卷体量是否均衡，分卷点是否合理
3. **节奏规划**：是否有张弛交替的节奏安排，避免连续高压或连续平淡
4. **伏笔分布**：伏笔是否在合理章节埋设和回收，有无遗漏的未回收伏笔
5. **角色弧光**：主要角色是否有成长/变化弧线
6. **逻辑自洽**：大纲中是否存在因果矛盾或逻辑漏洞
7. **情节冲突密度**：冲突设置是否充足且层层递进
8. **主线清晰度**：主线剧情是否清晰，支线是否喧宾夺主
9. **目标驱动**：主角是否有明确的目标和动机驱动剧情
10. **结局规划**：是否有明确的结局方向（开放式/封闭式）

请严格按以下JSON格式返回（不要添加任何其他文字）：
```json
{{
  "dimensions": [
    {{"name": "结构完整性", "score": 8, "status": "✓", "detail": "具体分析..."}},
    {{"name": "卷结构合理性", "score": 7, "status": "✓", "detail": "具体分析..."}},
    {{"name": "节奏规划", "score": 6, "status": "⚠", "detail": "具体分析..."}},
    {{"name": "伏笔分布", "score": 0, "status": "✓", "detail": "暂无伏笔数据，跳过"}},
    {{"name": "角色弧光", "score": 8, "status": "✓", "detail": "具体分析..."}},
    {{"name": "逻辑自洽", "score": 9, "status": "✓", "detail": "具体分析..."}},
    {{"name": "情节冲突密度", "score": 7, "status": "✓", "detail": "具体分析..."}},
    {{"name": "主线清晰度", "score": 8, "status": "✓", "detail": "具体分析..."}},
    {{"name": "目标驱动", "score": 7, "status": "✓", "detail": "具体分析..."}},
    {{"name": "结局规划", "score": 5, "status": "⚠", "detail": "具体分析..."}}
  ],
  "overall_score": 7.2,
  "summary": "整体评价文字...",
  "suggestions": ["建议1", "建议2", "建议3"]
}}
```

评分标准：
- 9-10分(✓)：优秀，无明显问题
- 7-8分(✓)：良好，有小问题但不影响整体
- 5-6分(⚠)：一般，存在需要改进的问题
- 1-4分(✗)：较差，存在严重问题
- 0分(✓)：数据不足，跳过此项

注意：如果某项数据为空（如暂无伏笔），该项评0分，status为"✓"，detail说明数据不足。"""

    try:
        gen = get_generator()
        raw_result = gen.ai.generate(prompt)
        return _parse_quality_json(raw_result, "outline-quality")
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")


@router.post("/settings-quality")
async def validate_settings_quality(data: SettingsQualityRequest):
    """世界观设定质量检查 — 一次性检查世界观的完整性/自洽性/独特性等10个维度"""
    return await asyncio.to_thread(_do_validate_settings_quality, data)


def _do_validate_settings_quality(data: SettingsQualityRequest):
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "no project")

    # ── 收集数据：纯世界观（不含人物） ──
    world_settings = getattr(state.project, "world_settings", {}) or {}
    world_text = ""
    if isinstance(world_settings, dict) and world_settings:
        lines = []
        for k, v in world_settings.items():
            if isinstance(v, dict):
                desc = v.get('description', v.get('val', v.get('content', '')))
                lines.append(f"- {k}：{desc}")
            elif isinstance(v, str):
                lines.append(f"- {k}：{v}")
            else:
                lines.append(f"- {k}：{v}")
        world_text = "\n".join(lines)
    elif isinstance(world_settings, str):
        world_text = world_settings
    if not world_text or not world_text.strip():
        world_text = "（暂无世界观设定）"

    # 章节大纲（仅用于判断设定利用率，不引入人物数据）
    chapters = getattr(state.project, "chapters", []) or []
    chapter_outlines = []
    for i, ch in enumerate(chapters):
        if isinstance(ch, dict):
            ol = ch.get("outline", "")
            if ol and ol.strip():
                chapter_outlines.append(f"第{i+1}章：{ol.strip()}")
    outlines_summary = "\n".join(chapter_outlines[:30]) if chapter_outlines else "（暂无章节大纲）"

    # 全书大纲（仅用于判断设定利用率）
    novel_outline = getattr(state.project, "novel_outline", {}) or {}
    outline_text = ""
    if novel_outline:
        if isinstance(novel_outline, dict):
            outline_text = json.dumps(novel_outline, ensure_ascii=False, indent=1)
        elif isinstance(novel_outline, list):
            outline_text = json.dumps(novel_outline, ensure_ascii=False, indent=1)
    if not outline_text or not outline_text.strip():
        outline_text = getattr(state.project, "get_outline_text", lambda: "")()

    prompt = f"""你是资深小说世界观设计师和设定审核专家。请对以下小说**世界观设定**进行全面的质量评估（不评估人物，只评估设定本身）。

【世界观设定】
{world_text[:5000]}

【全书大纲概要】（仅用于判断设定利用率）
{outline_text[:3000] if outline_text and outline_text.strip() else '（暂无全书大纲）'}

【章节大纲摘要（前30章）】（仅用于判断设定利用率）
{outlines_summary[:3000]}

请从以下10个维度逐项评分（每项1-10分），并给出详细的分析：

1. **体系完整性**：力量体系/社会制度/地理设定是否完整，有无明显缺失的子系统
2. **内部自洽**：世界观各子设定之间是否有矛盾（如规则A与规则B冲突）
3. **边界清晰**：能力/规则的边界是否清晰，是否有模糊地带导致剧情矛盾风险
4. **独特性**：设定是否有辨识度，是否是原创而非模板化（避免"万能元素体系"等套路）
5. **可扩展性**：设定是否留有扩展空间，支持后续剧情发展而不至于挖坑填不上
6. **规则深度**：力量体系/社会制度的底层逻辑是否足够深入，是否有明确的上限和代价
7. **层次感**：世界观的多个子系统（力量/政治/地理/文化等）之间是否有层次分明的关联
8. **设定利用率**：已设定的元素是否在大纲中被充分利用，有无闲置设定（浪费）
9. **信息量平衡**：设定信息量是否适中，是否过多导致读者难以消化或过少导致世界空洞
10. **表达清晰度**：设定文本是否表达清晰，是否有歧义或模糊描述可能导致后续写作困难

请严格按以下JSON格式返回（不要添加任何其他文字）：
```json
{{
  "dimensions": [
    {{"name": "体系完整性", "score": 8, "status": "✓", "detail": "具体分析..."}},
    {{"name": "内部自洽", "score": 7, "status": "✓", "detail": "具体分析..."}},
    {{"name": "边界清晰", "score": 6, "status": "⚠", "detail": "具体分析..."}},
    {{"name": "独特性", "score": 8, "status": "✓", "detail": "具体分析..."}},
    {{"name": "可扩展性", "score": 7, "status": "✓", "detail": "具体分析..."}},
    {{"name": "规则深度", "score": 6, "status": "⚠", "detail": "具体分析..."}},
    {{"name": "层次感", "score": 7, "status": "✓", "detail": "具体分析..."}},
    {{"name": "设定利用率", "score": 5, "status": "⚠", "detail": "具体分析..."}},
    {{"name": "信息量平衡", "score": 8, "status": "✓", "detail": "具体分析..."}},
    {{"name": "表达清晰度", "score": 9, "status": "✓", "detail": "具体分析..."}}
  ],
  "overall_score": 7.0,
  "summary": "整体评价文字...",
  "suggestions": ["建议1", "建议2", "建议3"]
}}
```

评分标准：
- 9-10分(✓)：优秀，无明显问题
- 7-8分(✓)：良好，有小问题但不影响整体
- 5-6分(⚠)：一般，存在需要改进的问题
- 1-4分(✗)：较差，存在严重问题
- 0分(✓)：数据不足，跳过此项

重要：本次检查只评估世界观设定本身，不评估人物。所有维度均围绕设定质量。"""

    try:
        gen = get_generator()
        raw_result = gen.ai.generate(prompt)
        return _parse_quality_json(raw_result, "settings-quality")
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")


# ── 人物档案质量检查 ──

@router.post("/characters-quality")
async def validate_characters_quality(data: CharactersQualityRequest):
    """人物档案质量检查 — 独立于设定检查，纯人物维度评估"""
    return await asyncio.to_thread(_do_validate_characters_quality, data)


def _do_validate_characters_quality(data: CharactersQualityRequest):
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "no project")

    # ── 收集数据：纯人物（不含世界观设定文本） ──
    character_settings = getattr(state.project, "character_settings", {}) or {}
    char_lines = []
    if isinstance(character_settings, dict):
        for name, info in character_settings.items():
            if isinstance(info, dict):
                desc = info.get("description", "")
                char_lines.append(f"- {name}：{desc}")
            else:
                char_lines.append(f"- {name}：{info}")
    characters = getattr(state.project, "characters", []) or []
    if characters:
        for ch in characters:
            if isinstance(ch, dict):
                name = ch.get("name", "")
                identity = ch.get("identity", "") or ch.get("description", "")
                char_lines.append(f"- {name}：{identity}")
    char_text = "\n".join(char_lines) if char_lines else "（暂无人物档案）"

    # 章节大纲（仅用于判断人物出场利用率）
    chapters = getattr(state.project, "chapters", []) or []
    chapter_outlines = []
    for i, ch in enumerate(chapters):
        if isinstance(ch, dict):
            ol = ch.get("outline", "")
            if ol and ol.strip():
                chapter_outlines.append(f"第{i+1}章：{ol.strip()}")
    outlines_summary = "\n".join(chapter_outlines[:30]) if chapter_outlines else "（暂无章节大纲）"

    # 全书大纲
    novel_outline = getattr(state.project, "novel_outline", {}) or {}
    outline_text = ""
    if novel_outline:
        if isinstance(novel_outline, dict):
            outline_text = json.dumps(novel_outline, ensure_ascii=False, indent=1)
        elif isinstance(novel_outline, list):
            outline_text = json.dumps(novel_outline, ensure_ascii=False, indent=1)
    if not outline_text or not outline_text.strip():
        outline_text = getattr(state.project, "get_outline_text", lambda: "")()

    prompt = f"""你是资深小说人物设计师和角色审核专家。请对以下小说**人物档案**进行全面的质量评估（不评估世界观设定，只评估人物本身）。

【人物档案】
{char_text[:5000]}

【全书大纲概要】（仅用于判断人物在剧情中的作用）
{outline_text[:3000] if outline_text and outline_text.strip() else '（暂无全书大纲）'}

【章节大纲摘要（前30章）】（仅用于判断人物出场分布）
{outlines_summary[:3000]}

请从以下10个维度逐项评分（每项1-10分），并给出详细的分析：

1. **人设深度**：主要角色的性格/背景/动机是否立体丰满，是否有足够细节支撑
2. **差异化**：角色之间是否有明确的差异化（性格/说话方式/行为模式），避免"千人一面"
3. **关系网丰富度**：角色之间的关系网络是否丰富且合理（对立/结盟/暧昧/师徒等）
4. **成长弧光**：主要角色是否有明确的成长/变化轨迹，是否有起点和终点的人设差异
5. **动机合理性**：角色的行为动机是否合理且自洽，是否能解释其在剧情中的选择
6. **出场分布**：主要角色的出场频率和章节分布是否合理，是否有角色长期消失
7. **对话适配度**：人物的对话风格是否与性格匹配（可从大纲中的场景描述推断）
8. **能力边界**：角色的能力/技能设定是否有明确边界，避免随时开挂
9. **配角功能性**：配角是否有存在的必要性，是否仅为主角服务而无独立人格
10. **人物利用率**：已创建的角色是否都在大纲中被安排了出场和作用，有无闲置角色

请严格按以下JSON格式返回（不要添加任何其他文字）：
```json
{{
  "dimensions": [
    {{"name": "人设深度", "score": 8, "status": "✓", "detail": "具体分析..."}},
    {{"name": "差异化", "score": 7, "status": "✓", "detail": "具体分析..."}},
    {{"name": "关系网丰富度", "score": 6, "status": "⚠", "detail": "具体分析..."}},
    {{"name": "成长弧光", "score": 7, "status": "✓", "detail": "具体分析..."}},
    {{"name": "动机合理性", "score": 8, "status": "✓", "detail": "具体分析..."}},
    {{"name": "出场分布", "score": 5, "status": "⚠", "detail": "具体分析..."}},
    {{"name": "对话适配度", "score": 0, "status": "✓", "detail": "暂无正文对话，跳过"}},
    {{"name": "能力边界", "score": 6, "status": "⚠", "detail": "具体分析..."}},
    {{"name": "配角功能性", "score": 7, "status": "✓", "detail": "具体分析..."}},
    {{"name": "人物利用率", "score": 5, "status": "⚠", "detail": "具体分析..."}}
  ],
  "overall_score": 6.5,
  "summary": "整体评价文字...",
  "suggestions": ["建议1", "建议2", "建议3"]
}}
```

评分标准：
- 9-10分(✓)：优秀，无明显问题
- 7-8分(✓)：良好，有小问题但不影响整体
- 5-6分(⚠)：一般，存在需要改进的问题
- 1-4分(✗)：较差，存在严重问题
- 0分(✓)：数据不足，跳过此项

重要：本次检查只评估人物本身，不评估世界观。所有维度均围绕人物质量。"""

    try:
        gen = get_generator()
        raw_result = gen.ai.generate(prompt)
        return _parse_quality_json(raw_result, "characters-quality")
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")


# ═══════════════════════════════════════════
# 全书级综合分析端点（手动触发）
# ═══════════════════════════════════════════

class ProjectReviewRequest(BaseModel):
    pass  # 无需额外参数，直接从 state.project 读取数据


@router.post("/project-review")
def validate_project_review(data: ProjectReviewRequest):
    """全书级综合分析：大纲质量(10维) + 世界观质量(10维) + 人物质量(10维) = 30维
    在项目完本或用户手动触发时调用，一次性完成全书级评估。"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "no project")

    gen = get_generator()
    if not gen:
        return err(ErrorCode.INTERNAL_ERROR, "generator 未初始化")

    try:
        results = gen.run_project_level_analysis()
        return {"ok": True, **results}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"全书分析失败: {str(e)}")

