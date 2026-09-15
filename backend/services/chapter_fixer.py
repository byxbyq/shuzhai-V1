# -*- coding: utf-8 -*-
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, List

from backend.services.project_service import state, get_generator
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)


from backend.routers.validate_models import (
    LOCAL_FIXABLE, CROSS_CHAPTER, _locate_problem_paragraphs, _build_fix_instruction,
    EditorialReviewRequest, MarketReviewRequest, EDITORIAL_PROMPT_MODES,
)
from backend.services.editorial_review import _do_editorial_review, _do_market_review

# ══════════════════════════════════════════
# 局部修复 + 综合修复端点
# ══════════════════════════════════════════

router = APIRouter()

class FixChapterRequest(BaseModel):
    chapter_index: int
    issues: List[dict]
    dry_run: bool = False


# 注：LOCAL_FIXABLE / CROSS_CHAPTER / FIX_TEMPLATES / _split_paragraphs /
# _find_paragraph_by_index / _locate_problem_paragraphs / _build_fix_instruction
# 均从 local_fix.py 导入（见文件顶部 import 块），此处不重复定义。


def _local_fix_paragraph(paragraph_text, fix_instruction, context_before="", context_after="",
                         check_type=""):
    gen = get_generator()
    full_context = ""
    if context_before:
        full_context += f"【前文】\n{context_before[-300:]}\n\n"
    if context_after:
        full_context += f"【后文】\n{context_after[:300]}\n\n"

    original_len = len(paragraph_text)
    min_length_ratio = 0.5
    if check_type == 'wordcount':
        min_length_ratio = 0.95
    min_accept_len = int(original_len * min_length_ratio)

    prompt = f"""请根据以下指令修改这段文字：

{fix_instruction}

【要修改的段落】
{paragraph_text}

{full_context}

要求：
1. 严格按修复指令修改，不要改写无关内容
2. 不要引入新设定或新角色
3. 保持原有的叙事风格和人物口吻
4. 修改后长度不能少于原长度的{int(min_length_ratio * 100)}%

直接输出修改后的文本，不要包含任何解释或说明。"""

    try:
        result = gen.ai.generate(prompt)
        fixed_text = result.strip()

        if len(fixed_text) < min_accept_len:
            return None, f"长度保护拒绝(原{original_len}→{len(fixed_text)}，需≥{min_accept_len})"

        return fixed_text, f"成功({len(fixed_text)}字)"
    except Exception as e:
        return None, f"异常: {str(e)[:80]}"


def _group_issues_by_type(issues: List[dict]) -> Dict[str, dict]:
    """按 check_type 分组问题列表"""
    issues_detail = {}
    for issue in issues:
        check_type = issue.get('check_type', '')
        if check_type not in issues_detail:
            issues_detail[check_type] = {'issues': []}
        issues_detail[check_type]['issues'].append(issue)
    return issues_detail


def _is_severe_problem(problem: str, severity: str) -> bool:
    """判断是否为严重问题（整章级别的，不适合局部修复）"""
    if severity != 'high':
        return False
    severe_keywords = ['完全偏离', '完全缺失', '完全不符', '未覆盖大纲任何要点',
                      '完全跑题', '与大纲完全', '整章']
    return any(kw in problem for kw in severe_keywords)


def _process_single_fixable_issue(
    check_type: str, issue: dict, content: str, dry_run: bool
) -> tuple:
    """处理单个可修复问题，返回 (new_content, result_dict, status_flags)

    status_flags: dict with keys: fixed, skipped_locate, skipped_failed
    """
    status_flags = {'fixed': 0, 'skipped_locate': 0, 'skipped_failed': 0}

    problem = issue.get('type', '') or issue.get('description', '')
    location = issue.get('location', '')
    suggestion = issue.get('suggestion', '')
    severity = issue.get('severity', 'medium')

    if not problem and not suggestion:
        return content, None, status_flags

    if _is_severe_problem(problem, severity):
        result = {
            'check_type': check_type,
            'problem': problem[:60],
            'location': location[:60],
            'status': 'skipped_severe',
            'reason': '严重问题，建议整章重写而非局部修复',
        }
        return content, result, status_flags

    start, end, strategy, paragraphs = _locate_problem_paragraphs(
        content, location, problem
    )

    if start < 0 or end < 0:
        result = {
            'check_type': check_type,
            'problem': problem[:60],
            'location': location[:60],
            'status': 'skipped_locate',
            'reason': '无法定位',
        }
        status_flags['skipped_locate'] = 1
        return content, result, status_flags

    target_text = '\n\n'.join(paragraphs[start:end + 1])
    if len(target_text) > 1500:
        result = {
            'check_type': check_type,
            'problem': problem[:60],
            'location': location[:60],
            'strategy': strategy,
            'paragraph_range': f'{start + 1}-{end + 1}',
            'status': 'skipped_too_long',
            'reason': f'定位段落过长({len(target_text)}字)，建议人工处理',
        }
        return content, result, status_flags

    context_before = '\n\n'.join(paragraphs[max(0, start - 2):start]) if start > 0 else ''
    context_after = '\n\n'.join(paragraphs[end + 1:min(len(paragraphs), end + 3)]) if end < len(paragraphs) - 1 else ''

    if dry_run:
        result = {
            'check_type': check_type,
            'problem': problem[:60],
            'location': location[:60],
            'strategy': strategy,
            'paragraph_range': f'{start + 1}-{end + 1}',
            'status': 'located',
            'target_text': target_text[:100],
            'target_len': len(target_text),
        }
        return content, result, status_flags

    fix_instruction = _build_fix_instruction(check_type, problem, suggestion)

    fixed_text, status_msg = _local_fix_paragraph(
        target_text, fix_instruction, context_before, context_after,
        check_type=check_type,
    )

    if fixed_text is None:
        result = {
            'check_type': check_type,
            'problem': problem[:60],
            'location': location[:60],
            'strategy': strategy,
            'paragraph_range': f'{start + 1}-{end + 1}',
            'status': 'failed',
            'reason': status_msg,
        }
        status_flags['skipped_failed'] = 1
        return content, result, status_flags

    new_paragraphs = paragraphs[:start] + [fixed_text] + paragraphs[end + 1:]
    new_content = '\n\n'.join(new_paragraphs)

    result = {
        'check_type': check_type,
        'problem': problem[:60],
        'location': location[:60],
        'strategy': strategy,
        'paragraph_range': f'{start + 1}-{end + 1}',
        'status': 'fixed',
        'reason': status_msg,
        'original_len': len(target_text),
        'fixed_len': len(fixed_text),
        'len_change': len(fixed_text) - len(target_text),
    }
    status_flags['fixed'] = 1
    return new_content, result, status_flags


def _process_fixable_issues(
    issues_detail: Dict[str, dict], content: str, dry_run: bool
) -> tuple:
    """处理所有可局部修复的问题，返回 (new_content, fix_results, fixed_count, skipped_locate, skipped_failed)"""
    fix_results = []
    fixed_count = 0
    skipped_locate = 0
    skipped_failed = 0

    fixable_cts = [ct for ct in LOCAL_FIXABLE if ct in issues_detail]

    for check_type in fixable_cts:
        ct_data = issues_detail.get(check_type, {})
        if not isinstance(ct_data, dict):
            continue
        issues_list = ct_data.get('issues', []) or []
        if not issues_list:
            continue

        for issue in issues_list[:3]:
            if not isinstance(issue, dict):
                continue

            content, result, flags = _process_single_fixable_issue(
                check_type, issue, content, dry_run
            )
            if result is not None:
                fix_results.append(result)
            fixed_count += flags['fixed']
            skipped_locate += flags['skipped_locate']
            skipped_failed += flags['skipped_failed']

    return content, fix_results, fixed_count, skipped_locate, skipped_failed


def _process_cross_chapter_issues(issues_detail: Dict[str, dict]) -> tuple:
    """处理跨章节问题（仅记录，不修复），返回 (fix_results, skipped_cross)"""
    fix_results = []
    skipped_cross = 0

    cross_cts = [ct for ct in CROSS_CHAPTER if ct in issues_detail]

    for check_type in cross_cts:
        ct_data = issues_detail.get(check_type, {})
        if not isinstance(ct_data, dict):
            continue
        issues_list = ct_data.get('issues', []) or []
        for issue in issues_list[:2]:
            if not isinstance(issue, dict):
                continue
            problem = issue.get('type', '') or issue.get('description', '')
            fix_results.append({
                'check_type': check_type,
                'problem': problem[:60],
                'location': issue.get('location', '')[:60],
                'status': 'skipped_cross',
                'reason': '跨章节问题，需人工处理',
            })
            skipped_cross += 1

    return fix_results, skipped_cross


@router.post("/fix/chapter")
def fix_chapter(data: FixChapterRequest):
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "no project")

    ch_idx = data.chapter_index
    ch_data = state.project.load_chapter(ch_idx)
    if not ch_data:
        return err(ErrorCode.INTERNAL_ERROR, f"加载章节失败")

    content = ch_data.get('content', '')
    title = ch_data.get('title', f'第{ch_idx + 1}章')

    if not content or len(content) < 100:
        return err(ErrorCode.INTERNAL_ERROR, '内容过短')

    original_content = content

    issues_detail = _group_issues_by_type(data.issues)

    content, fix_results_fixable, fixed_count, skipped_locate, skipped_failed = \
        _process_fixable_issues(issues_detail, content, data.dry_run)

    fix_results_cross, skipped_cross = _process_cross_chapter_issues(issues_detail)

    fix_results = fix_results_fixable + fix_results_cross

    if not data.dry_run and fixed_count > 0 and content != original_content:
        state.project.save_chapter(ch_idx, content)

    return {
        'ok': True,
        'chapter_index': ch_idx,
        'chapter_title': title,
        'total_issues': len(data.issues),
        'fixed': fixed_count,
        'skipped_cross': skipped_cross,
        'skipped_locate': skipped_locate,
        'skipped_failed': skipped_failed,
        'results': fix_results,
        'content_changed': content != original_content,
        'content_length': len(content),
    }


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



# ═══════════════════════════════════════════════════════════════════
# 综合修复端点 - 基于19维检查结果一次性修复所有问题
# ═══════════════════════════════════════════════════════════════════

class FixAllRequest(BaseModel):
    content: str
    check_result: Dict
    chapter_index: int = 0
    context: Optional[Dict] = None


@router.post("/fix-all")
def fix_all(data: FixAllRequest):
    """综合修复：基于19维检查结果一次性修复所有问题

    优势：
    1. 综合考虑所有问题，避免冲突修改
    2. 一次AI调用完成所有修复
    3. 保持上下文连贯性
    """
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "no project")

    gen = get_generator()
    if not gen:
        return err(ErrorCode.INTERNAL_ERROR, "generator未初始化")

    content = data.content
    check_result = data.check_result
    chapter_index = data.chapter_index
    ctx = data.context or {}

    # 收集所有问题
    issues_summary = []

    # 1. 收集10维问题检查的问题
    if check_result.get('checks'):
        for check_type, check_data in check_result['checks'].items():
            if not check_data.get('ok', True):
                issue_content = check_data.get('content', '')
                if issue_content and not issue_content.startswith('无'):
                    issues_summary.append(f"【{check_type}】{issue_content}")

    # 2. 收集评分中的低分项（1-2分）
    if check_result.get('editorial') and check_result['editorial'].get('dimensions'):
        for dim in check_result['editorial']['dimensions']:
            if dim.get('score', 5) <= 2:
                issues_summary.append(f"【责编评分-{dim['name']}】{dim.get('score', 0)}分：{dim.get('description', '')}")

    if check_result.get('market') and check_result['market'].get('dimensions'):
        for dim in check_result['market']['dimensions']:
            if dim.get('score', 5) <= 2:
                issues_summary.append(f"【市场评分-{dim['name']}】{dim.get('score', 0)}分：{dim.get('description', '')}")

    if not issues_summary:
        return {"ok": True, "message": "没有需要修复的问题", "content": content}

    # 获取章节大纲
    chapter_outline = ctx.get('chapterOutline', '')
    if not chapter_outline and 0 <= chapter_index < len(state.project.chapters):
        chapter_outline = state.project.chapters[chapter_index].get('outline', '')

    # 构建修复prompt（混合模式：读取全文，只修改有问题的段落）
    prompt = f"""你是小说修复专家。请根据以下检查结果，对正文进行**精准修复**。

【核心原则】
1. **只修改有问题的段落**，未提及的段落保持原样不动
2. 修改时考虑前后文上下文，保持连贯性
3. 不要引入新的问题
4. 保持原有风格不变

【本章大纲】
{chapter_outline if chapter_outline else '（未提供）'}

【发现的问题】
{chr(10).join(f'{i+1}. {issue}' for i, issue in enumerate(issues_summary))}

【待修复正文（按段落编号）】
{chr(10).join(f'[P{i+1}] {p}' for i, p in enumerate(content.split(chr(10))) if p.strip())}

【输出格式】
请按以下格式输出：
1. 先输出需要修改的段落编号列表，如：需修改：P2, P5, P8
2. 然后输出修复后的完整正文，保持原有段落换行格式

需修改：P?
---FIXED---
（修复后的完整正文，未修改的段落保持原样）"""

    try:
        raw_result = gen.ai.generate(prompt)

        # 解析混合模式输出
        fixed_content = raw_result
        changed_paragraphs = []

        # 提取"需修改：P?"行
        if '需修改：' in raw_result:
            for line in raw_result.split(chr(10)):
                if line.strip().startswith('需修改：') or line.strip().startswith('需修改:'):
                    # 解析段落编号：P2, P5, P8
                    import re
                    p_nums = re.findall(r'P(\d+)', line)
                    changed_paragraphs = [int(n) for n in p_nums]
                    break

        # 提取 ---FIXED--- 之后的正文
        if '---FIXED---' in raw_result:
            fixed_content = raw_result.split('---FIXED---')[-1].strip()
        else:
            # 如果没有标记，尝试去掉第一行的"需修改：..."
            lines = raw_result.split(chr(10))
            start = 0
            for i, l in enumerate(lines):
                if '需修改' in l:
                    start = i + 1
                    break
            fixed_content = chr(10).join(lines[start:]).strip()

        return {
            "ok": True,
            "original": content,
            "fixed": fixed_content,
            "changed_paragraphs": changed_paragraphs,  # 修改了哪些段落
            "issues_fixed": len(issues_summary),
            "issues_summary": issues_summary[:5],
            "mode": "hybrid"  # 混合模式标识
        }
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"综合修复失败: {str(e)}")


# ═══════════════════════════════════════════
# 深度去AI味端点 — 逐段反检测重写（不依赖自家检测定位）
# ═══════════════════════════════════════════

class DeaiDeepRequest(BaseModel):
    content: str
    chapter_index: int = 0


_DEAI_DEEP_PROMPT = """你是一位有十年经验的网文作者，请把下面的小说段落改写成反AI检测风格。

【红线】
- 每段的情节、人物动作、对话含义必须完全保留，不增不减不改剧情
- 逐段改写：输入有几段就输出几段，用换行分隔，顺序不变

【风格要求（破坏AI文本的统计指纹）】
1. 句长必须极端参差：三五个字的超短句和四十字以上的长句混用，禁止均匀的中长句
2. 多用残句、省略主语的句子、倒装（"走进来一个男人。""安静。整个房间都安静。"）
3. 节奏突变：流畅描写到一半硬生生切断，跳到另一个细节
4. 删掉所有圆滑过渡词（然而、就在此时、只见、不禁、缓缓、一丝、一抹）
5. 对话要口语、结巴、说半句、带岔开，禁止过于工整的回答
6. 形容词减到最少，用具体动词和名词；描写带生活化的细节质感
7. 偶尔插入与主线无关的琐碎细节（小动作、环境的声音和颜色）
8. 破折号（——）每千字不超过2个
9. 字数与原文接近（上下浮动20%以内）

【输出】
直接输出改写后的段落，每段一行，不要编号，不要任何解释。
"""


def _build_deai_deep_prompt(batch_text: str) -> str:
    """拼接深度去AI提示词（不用 % 格式化，避免正文中的 % 字符引发错误）"""
    return _DEAI_DEEP_PROMPT + "\n【原文段落】\n" + batch_text


@router.post("/deai-deep")
def deai_deep(data: DeaiDeepRequest):
    """深度去AI味：逐段反外部检测重写

    与"去AI味"单次全文重写的区别：
    1. 逐段（3段一批）重写，段落级聚焦，避免长文重写时的稀释
    2. 不依赖自家检测定位问题（自家检测达标也照样执行）
    3. 提示词专门针对外部ML检测器的统计特征（句长极差/残句/节奏突变）
    代价：耗时较长（一章约2-4分钟），消耗Token较多。
    单批失败时保留原文段落，不阻塞整体。
    """
    import re

    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "no project")

    content = (data.content or '').strip()
    if len(content) < 100:
        return err(ErrorCode.VALIDATION_ERROR, "内容过短，无需深度处理")

    from backend.ai_client import AIClient
    ai = AIClient()

    paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
    batch_size = 3
    rewritten = []
    processed = 0
    total_batches = (len(paragraphs) + batch_size - 1) // batch_size

    for bi, start in enumerate(range(0, len(paragraphs), batch_size)):
        batch = paragraphs[start:start + batch_size]
        batch_text = '\n'.join(batch)
        prompt = _build_deai_deep_prompt(batch_text)
        result = None
        try:
            result = ai.generate_for_task(prompt, task_type="chat",
                                          temperature=1.05, max_tokens=6000)
        except Exception as e:
            logger.warning(f"[deai-deep] 批次{bi + 1}/{total_batches} AI调用异常: {e}")
        if result and not result.startswith('[生成失败') and not result.startswith('[错误'):
            result = result.strip()
            m = re.match(r'^```(?:\w+)?\s*\n([\s\S]*?)\n```$', result)
            if m:
                result = m.group(1).strip()
            new_paras = [p.strip() for p in result.split('\n') if p.strip()]
            orig_len = sum(len(p) for p in batch)
            new_len = sum(len(p) for p in new_paras)
            # 合理性闸门：重写结果长度需在原文的 50%~200% 之间，否则回退原文
            if new_paras and orig_len > 0 and 0.5 < new_len / orig_len < 2.0:
                rewritten.extend(new_paras)
                processed += len(batch)
                logger.info(f"[deai-deep] 批次{bi + 1}/{total_batches} 重写成功，{len(batch)}段")
                continue
            logger.warning(f"[deai-deep] 批次{bi + 1} 结果长度异常({new_len}/{orig_len})，回退原文")
        else:
            logger.warning(f"[deai-deep] 批次{bi + 1}/{total_batches} 生成失败，保留原文")
        rewritten.extend(batch)

    return {
        "ok": True,
        "content": '\n\n'.join(rewritten),
        "processed": processed,
        "total": len(paragraphs),
    }


@router.post("/fix")
def fix_paragraph(data: FixParagraphRequest):
    """AI 修复指定段落的问题"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "no project")

    idx = data.chapter_index
    if idx < 0 or idx >= len(state.project.chapters):
        return err(ErrorCode.NOT_FOUND, "章节不存在")

    try:
        content = state.project.get_content(idx)
    except Exception:
        return err(ErrorCode.INTERNAL_ERROR, "无法读取章节内容")

    if not content:
        return err(ErrorCode.INTERNAL_ERROR, "章节内容为空")

    # 分割段落
    paragraphs = content.split('\n')

    if data.paragraph_index < 0 or data.paragraph_index >= len(paragraphs):
        return err(ErrorCode.NOT_FOUND, "段落不存在")

    original_para = paragraphs[data.paragraph_index]

    # 构建 AI 修复 prompt
    gen = get_generator()

    # 获取上下文（前后各 2 段）
    context_start = max(0, data.paragraph_index - 2)
    context_end = min(len(paragraphs), data.paragraph_index + 3)

    context_paras = []
    for i in range(context_start, context_end):
        prefix = ""
        if i == data.paragraph_index:
            prefix = "[待修复段落] "
        context_paras.append(f"段落{i}: {prefix}{paragraphs[i]}")

    context_text = "\n".join(context_paras)

    prompt = f"""你是一位专业小说编辑。请修复以下段落的问题。

【问题类型】{data.issue_type}
【问题描述】{data.issue}
【修改建议】{data.suggestion}

【上下文】（段落{context_start}到段落{context_end-1}，其中段落{data.paragraph_index}是待修复段落）
{context_text}

【要求】
1. 只修复段落{data.paragraph_index}，保持其他段落不变
2. 保持与上下文的连贯性
3. 保持原有的写作风格和语气
4. 直接返回修复后的段落内容，不要解释

【修复后的段落{data.paragraph_index}】"""

    try:
        fixed_para = gen.ai.generate(prompt).strip()

        # 更新段落
        paragraphs[data.paragraph_index] = fixed_para
        new_content = "\n".join(paragraphs)

        # 保存
        state.project.set_content(new_content, idx)

        return {
            "ok": True,
            "original": original_para,
            "fixed": fixed_para
        }
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"AI 修复失败：{str(e)}")
