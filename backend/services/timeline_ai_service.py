# -*- coding: utf-8 -*-
"""时间线 AI 对照与修复服务（从 routers/timeline.py 拆分）

包含 _fix_para_index, _ensure_structure 工具函数和
ai_compare / ai_compare_all / ai_fix_divergence / ai_fix_all_divergences / finalize_chapter 的完整实现。
"""
import datetime
import json
import logging

from backend.ai_client import AIClient
from backend.api_models import err, ErrorCode
from backend.models.timeline_models import CompareRequest, DivergenceFixRequest
from backend.services.project_service import state
from backend.timeline_service import TimelineService

logger = logging.getLogger(__name__)


def _get_timeline_service() -> TimelineService:
    """获取时间线服务实例"""
    return TimelineService(state.project)


def _fix_para_index(item: dict, chapter_index: int, volume_index: int) -> dict:
    """确保 divergence item 的 paragraph_index 指向正确的章节和卷。

    逻辑：如果 item 中没有 paragraph_index 或者 chapter_index/volume_index 不匹配，
    就根据当前上下文（volume_index, chapter_index）写入正确的 paragraph_index。
    """
    pi = item.get("paragraph_index") or {}
    needs_fix = False

    if not pi:
        needs_fix = True
    else:
        # 检查是否匹配当前上下文
        pi_vol = pi.get("volume_index")
        pi_ch = pi.get("chapter_index")
        if pi_vol != volume_index or pi_ch != chapter_index:
            needs_fix = True

    if needs_fix:
        item["paragraph_index"] = {
            "volume_index": volume_index,
            "chapter_index": chapter_index,
        }
    return item


def _ensure_structure(node: dict) -> dict:
    """确保时间线节点包含所有必要字段"""
    defaults = {
        "planned": "",
        "actual": "",
        "annotation": "",
        "divergences": [],
        "actual_summary": "",
    }
    for key, val in defaults.items():
        if key not in node:
            node[key] = val
    return node


# ═══════════════════════════════════════════════
# AI 端点实现
# ═══════════════════════════════════════════════

def do_ai_compare(volume_index: int, chapter_index: int, body: CompareRequest):
    """触发 AI 对照：计划 vs 实际，自动生成 actual 和 divergences。"""
    try:
        svc = _get_timeline_service()
        project = state.project

        # 获取计划文本
        planned = body.planned_text
        if not planned:
            node = svc.get_chapter(volume_index, chapter_index)
            planned = node.get("planned", "") if node else ""

        # 获取正文
        chapter_text = body.chapter_text
        if not chapter_text:
            volumes = project.volumes or []
            global_ch_idx = None
            if 0 <= volume_index < len(volumes):
                vol_ch_list = volumes[volume_index].get("chapters", [])
                if 1 <= chapter_index <= len(vol_ch_list):
                    global_ch_idx = vol_ch_list[chapter_index - 1]
            ch_list = project.chapters or []
            arr_idx = None
            if global_ch_idx is not None:
                for i, ch in enumerate(ch_list):
                    if ch.get("index") == global_ch_idx:
                        arr_idx = i
                        break
            if arr_idx is not None and arr_idx < len(ch_list):
                ch_data = ch_list[arr_idx]
                ch_title = ch_data.get("title", "")
                ch_content = ch_data.get("content", "") or ch_data.get("body", "") or ""
                ch_outline = ch_data.get("outline", "") or ""
                combined = []
                if ch_title:
                    combined.append(f"章节标题：{ch_title}")
                if ch_outline:
                    combined.append(f"章节大纲：{ch_outline}")
                if ch_content:
                    combined.append(f"正文内容：{ch_content}")
                chapter_text = "\n\n".join(combined)

        if not planned:
            return err(ErrorCode.INVALID_PARAM, "未提供计划文本，请先填写章节大纲")

        # 调用 AI 进行对照
        ai = AIClient()
        prompt = f"""你是一位资深网文编辑，请对以下章节的计划大纲与实际正文进行逐段对照分析。

【计划大纲】
{planned}

【实际正文】
{chapter_text}

请生成：
1. actual_summary：实际正文内容的简洁摘要（100字以内）
2. divergences：偏离列表，每项包含：
   - type: "修改"/"新增"/"删除"
   - item: 偏离的具体内容描述
   - note: 编辑建议

请以 JSON 格式返回，格式为：
{{"actual_summary": "...", "divergences": [{{"type": "修改", "item": "...", "note": "..."}}]}}
"""
        result_text = ai.generate(prompt)
        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            # 尝试从 Markdown 代码块中提取 JSON
            import re
            m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', result_text, re.DOTALL)
            if m:
                try:
                    result = json.loads(m.group(1))
                except json.JSONDecodeError:
                    return err(ErrorCode.PARSE_ERROR, "AI 返回格式错误，无法解析")
            else:
                return err(ErrorCode.PARSE_ERROR, "AI 返回格式错误，无法解析")

        actual_summary = result.get("actual_summary", "")
        divergences = result.get("divergences", [])

        # 修复 paragraph_index
        for d in divergences:
            _fix_para_index(d, chapter_index, volume_index)

        # 写入时间线
        node = svc.get_chapter(volume_index, chapter_index) or {}
        node = _ensure_structure(node)
        node["actual"] = actual_summary
        node["divergences"] = divergences
        svc.update_chapter(volume_index, chapter_index, node)

        return {"ok": True, "data": {"actual_summary": actual_summary, "divergences": divergences}}
    except Exception as e:
        logger.exception("ai_compare failed")
        return err(ErrorCode.INTERNAL_ERROR, str(e))


def do_ai_compare_all(volume_index: int, chapter_index: int):
    """AI 全量对照所有章节。"""
    try:
        svc = _get_timeline_service()
        project = state.project

        volumes = project.volumes or []
        total_compared = 0
        errors = []

        for vi, vol in enumerate(volumes):
            ch_list = vol.get("chapters", [])
            for ci_offset, global_ch_idx in enumerate(ch_list):
                ci = ci_offset + 1  # 1-based
                ch_data = None
                for ch in (project.chapters or []):
                    if ch.get("index") == global_ch_idx:
                        ch_data = ch
                        break
                if not ch_data:
                    continue

                planned = ""
                node = svc.get_chapter(vi, ci)
                if node:
                    planned = node.get("planned", "")

                ch_content = ch_data.get("content", "") or ch_data.get("body", "") or ""
                ch_title = ch_data.get("title", "")
                ch_outline = ch_data.get("outline", "") or ""
                combined = []
                if ch_title:
                    combined.append(f"章节标题：{ch_title}")
                if ch_outline:
                    combined.append(f"章节大纲：{ch_outline}")
                if ch_content:
                    combined.append(f"正文内容：{ch_content}")
                chapter_text = "\n\n".join(combined)

                if not planned and not chapter_text:
                    continue

                body = CompareRequest(
                    chapter_index=ci - 1,
                    planned_text=planned,
                    chapter_text=chapter_text,
                )
                try:
                    result = do_ai_compare(vi, ci, body)
                    if result.get("ok"):
                        total_compared += 1
                    else:
                        errors.append(f"卷{vi+1}章{ci}: {result.get('message','')}")
                except Exception as e:
                    errors.append(f"卷{vi+1}章{ci}: {str(e)}")

        return {
            "ok": True,
            "data": {
                "total_compared": total_compared,
                "errors": errors,
            }
        }
    except Exception as e:
        logger.exception("ai_compare_all failed")
        return err(ErrorCode.INTERNAL_ERROR, str(e))


def do_ai_fix_divergence(volume_index: int, chapter_index: int, body: DivergenceFixRequest):
    """AI 修复单个偏离。"""
    try:
        svc = _get_timeline_service()
        node = svc.get_chapter(volume_index, chapter_index)
        if not node:
            return err(ErrorCode.NOT_FOUND, "章节不存在")
        node = _ensure_structure(node)

        planned = node.get("planned", "")
        divergences = node.get("divergences", [])

        if not divergences:
            return err(ErrorCode.INVALID_PARAM, "没有可修复的偏离")

        # 构建修复提示
        div_text = json.dumps(divergences, ensure_ascii=False, indent=2)

        ai = AIClient()
        prompt = f"""你是一位资深网文编辑。以下章节的计划大纲和实际偏离列表，请为每个偏离项生成修复后的文本。

【计划大纲】
{planned}

【偏离列表】
{div_text}

请为每个偏离项生成修复建议，以 JSON 格式返回：
{{"fixes": [{{"divergence_index": 0, "fixed_text": "修复后的段落文本"}}]}}
"""
        result_text = ai.generate(prompt)
        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            import re
            m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', result_text, re.DOTALL)
            if m:
                try:
                    result = json.loads(m.group(1))
                except json.JSONDecodeError:
                    return err(ErrorCode.PARSE_ERROR, "AI 返回格式错误")
            else:
                return err(ErrorCode.PARSE_ERROR, "AI 返回格式错误")

        fixes = result.get("fixes", [])
        for fix in fixes:
            idx = fix.get("divergence_index", -1)
            fixed_text = fix.get("fixed_text", "")
            if 0 <= idx < len(divergences):
                divergences[idx]["fixed_text"] = fixed_text
                divergences[idx]["status"] = "已修复"

        node["divergences"] = divergences
        svc.update_chapter(volume_index, chapter_index, node)

        return {"ok": True, "data": {"divergences": divergences}}
    except Exception as e:
        logger.exception("ai_fix_divergence failed")
        return err(ErrorCode.INTERNAL_ERROR, str(e))


def do_ai_fix_all_divergences(volume_index: int, chapter_index: int):
    """AI 修复全部偏离。"""
    try:
        svc = _get_timeline_service()
        project = state.project

        volumes = project.volumes or []
        total_fixed = 0
        errors = []

        for vi, vol in enumerate(volumes):
            ch_list = vol.get("chapters", [])
            for ci_offset in range(len(ch_list)):
                ci = ci_offset + 1
                node = svc.get_chapter(vi, ci)
                if not node:
                    continue
                node = _ensure_structure(node)
                divergences = node.get("divergences", [])
                if not divergences:
                    continue

                planned = node.get("planned", "")
                div_text = json.dumps(divergences, ensure_ascii=False, indent=2)

                ai = AIClient()
                prompt = f"""你是一位资深网文编辑。以下章节的计划大纲和实际偏离列表，请为每个偏离项生成修复后的文本。

【计划大纲】
{planned}

【偏离列表】
{div_text}

请为每个偏离项生成修复建议，以 JSON 格式返回：
{{"fixes": [{{"divergence_index": 0, "fixed_text": "修复后的段落文本"}}]}}
"""
                try:
                    result_text = ai.generate(prompt)
                    result = json.loads(result_text)
                except json.JSONDecodeError:
                    import re
                    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', result_text, re.DOTALL)
                    if m:
                        try:
                            result = json.loads(m.group(1))
                        except json.JSONDecodeError:
                            errors.append(f"卷{vi+1}章{ci}: AI返回格式错误")
                            continue
                    else:
                        errors.append(f"卷{vi+1}章{ci}: AI返回格式错误")
                        continue

                fixes = result.get("fixes", [])
                for fix in fixes:
                    idx = fix.get("divergence_index", -1)
                    fixed_text = fix.get("fixed_text", "")
                    if 0 <= idx < len(divergences):
                        divergences[idx]["fixed_text"] = fixed_text
                        divergences[idx]["status"] = "已修复"
                        total_fixed += 1

                node["divergences"] = divergences
                svc.update_chapter(vi, ci, node)

        return {
            "ok": True,
            "data": {
                "total_fixed": total_fixed,
                "errors": errors,
            }
        }
    except Exception as e:
        logger.exception("ai_fix_all_divergences failed")
        return err(ErrorCode.INTERNAL_ERROR, str(e))


def do_finalize_chapter(volume_index: int, chapter_index: int):
    """定稿章节：标记为已完成。"""
    try:
        svc = _get_timeline_service()
        node = svc.get_chapter(volume_index, chapter_index)
        if not node:
            return err(ErrorCode.NOT_FOUND, "章节不存在")

        node = _ensure_structure(node)
        node["finalized"] = True
        node["finalized_at"] = datetime.datetime.now().isoformat()
        svc.update_chapter(volume_index, chapter_index, node)

        return {"ok": True, "data": node}
    except Exception as e:
        logger.exception("finalize_chapter failed")
        return err(ErrorCode.INTERNAL_ERROR, str(e))
