# -*- coding: utf-8 -*-
import logging
from fastapi import APIRouter

from backend.services.project_service import state, get_generator
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)

from ._models import GenerateRequest, ConfirmRequest, ExtractStateRequest

router = APIRouter()

@router.post("/chapter")
def generate_chapter(data: GenerateRequest):
    """
    [DEPRECATED] 旧的章节生成端点。
    请改用 /api/generate/gate（预览不落盘）+ /api/generate/confirm（确认保存）的 C4 事前确认流程。
    本端点为兼容旧前端保留，已移除自动落盘、状态提取、向量记忆注入。
    """
    import logging
    logging.getLogger(__name__).warning(
        "调用已废弃端点 /api/generate/chapter，请迁移到 /api/generate/gate + /api/generate/confirm"
    )
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    gen = get_generator()
    gen.reload_world()
    ch_idx = data.chapter_index
    # 占位符列表：这些outline值不是真正的大纲内容
    _PLACEHOLDER_PATTERNS = ['【第', '大纲要点', '在此输入', 'placeholder', 'TODO']
    def _is_placeholder(text):
        if not text or not text.strip():
            return True
        t = text.strip()
        return any(p in t for p in _PLACEHOLDER_PATTERNS)

    if ch_idx < len(state.project.chapters):
        current_outline = state.project.chapters[ch_idx].get('outline', '')
        current_blueprint = state.project.chapters[ch_idx].get('blueprint')
        # 过滤占位符：outline如果是占位符，视为空
        if _is_placeholder(current_outline):
            current_outline = ''
        if not current_outline and not current_blueprint:
            return {'ok': False, 'error': '没有章节大纲，请先生成章节大纲'}
        # 如果有blueprint但outline为空（或为占位符），将blueprint转为结构化大纲文本
        if not current_outline and current_blueprint:
            bp_parts = []
            intro = current_blueprint.get("intro", {})
            if intro:
                bp_parts.append("【起】场景：%s — 触发事件：%s" % (intro.get("scene",""), intro.get("trigger","")))
                if intro.get("atmosphere"):
                    bp_parts.append("  氛围：%s" % intro["atmosphere"])
                if intro.get("characters"):
                    bp_parts.append("  出场角色：%s" % ", ".join(intro["characters"]))
            for dev in current_blueprint.get("development", []):
                bp_parts.append("【承】场景：%s" % dev.get("scene",""))
                bp_parts.append("  事件：%s" % dev.get("event",""))
                if dev.get("characters"):
                    bp_parts.append("  角色：%s" % ", ".join(dev["characters"]))
                if dev.get("choice"):
                    bp_parts.append("  选择：%s" % dev["choice"])
                if dev.get("cost"):
                    bp_parts.append("  代价：%s" % dev["cost"])
                if dev.get("info_reveal"):
                    bp_parts.append("  信息释放：%s" % dev["info_reveal"])
                if dev.get("new_state"):
                    bp_parts.append("  新状态：%s" % dev["new_state"])
            climax = current_blueprint.get("climax", {})
            if climax:
                bp_parts.append("【转】冲突：%s" % climax.get("conflict",""))
                if climax.get("twist"):
                    bp_parts.append("  转折：%s" % climax["twist"])
                if climax.get("key_choice"):
                    bp_parts.append("  关键选择：%s" % climax["key_choice"])
            ending = current_blueprint.get("ending", {})
            if ending:
                bp_parts.append("【合】新状态：%s" % ending.get("new_state",""))
                if ending.get("info_reveal"):
                    bp_parts.append("  信息揭露：%s" % ending["info_reveal"])
                if ending.get("next_hook"):
                    bp_parts.append("  下章钩子：%s" % ending["next_hook"])
            current_outline = "\n".join(bp_parts)
    # 如果未提供 context，自动获取前一章全文作为衔接上下文
    context = data.context
    if not context and data.chapter_index > 0:
        try:
            context = state.project.get_previous_context(chapter_index=data.chapter_index)
            if context:
                context = "前一章全文：\n" + context
        except Exception:
            pass


    # 字数预算
    target_wc = 2500
    try:
        if data.chapter_index < len(state.project.chapters):
            ch = state.project.chapters[data.chapter_index]
            target_wc = ch.get('word_count_target', ch.get('target_words', 2500))
    except Exception: pass
    wc_text = '<wordcount>目标' + str(target_wc) + '字，控制在' + str(int(target_wc*0.8)) + '-' + str(int(target_wc*1.2)) + '字</wordcount>'
    if context: context += '\n' + wc_text
    else: context = wc_text

    # 偏好记忆（使用标准guide格式）
    try:
        import os as _o
        pf = _o.path.join(state.project.project_dir, 'user_preferences.json')
        if _o.path.exists(pf):
            # 尝试使用标准guide接口
            try:
                from backend.services.preference_service import get_pref_guide
                guide_result = get_pref_guide()
                if guide_result.get("ok") and not guide_result.get("empty"):
                    context += '\n' + guide_result["guide"]
            except Exception:
                # 回退：手动格式化
                import json as _j
                with open(pf, 'r', encoding='utf-8') as _fh:
                    prefs = _j.load(_fh)
                parts = []
                for k, v in prefs.items():
                    if isinstance(v, str) and v.strip():
                        parts.append(k + ': ' + v)
                    elif isinstance(v, list) and v:
                        parts.append(k + ': ' + ', '.join(str(i) for i in v))
                    elif isinstance(v, dict):
                        for sk, sv in v.items():
                            if isinstance(sv, str) and sv.strip():
                                parts.append(k + '/' + sk + ': ' + sv)
                            elif isinstance(sv, list) and sv:
                                parts.append(k + '/' + sk + ': ' + ', '.join(str(i) for i in sv))
                if parts:
                    context += '\n## 用户偏好\n' + '\n'.join(parts)
    except Exception: pass

    # 诊断反馈闭环
    try:
        from backend.services.project_service import get_ledger
        ledger = get_ledger()
        if ledger and ledger.validation_warnings:
            last_diag = ledger.validation_warnings[-1] if ledger.validation_warnings else {}
            diag_summary = last_diag.get("summary", {})
            if diag_summary and isinstance(diag_summary, dict):
                s = diag_summary
                diag_parts = ['上次诊断: ' + str(s.get('written_chapters',0)) + '/' + str(s.get('total_chapters',0)) + '章已写, ' + str(s.get('total_issues',0)) + '个问题(' + str(s.get('high_issues',0)) + '严重)']
                for w in last_diag.get('worklist', []):
                    ch_idx = w.get('chapter', 0)
                    if ch_idx == data.chapter_index + 1 or ch_idx == 0:
                        issues_detail = '; '.join([i.get('detail','') for i in w.get('issues', []) if i.get('detail')])
                        if issues_detail:
                            diag_parts.append('当前章: ' + issues_detail)
                if diag_parts:
                    context += '\n## 诊断反馈\n' + '\n'.join(diag_parts)
    except Exception: pass
# 大纲优先级：后端从blueprint构建的完整大纲 > 前端传来的outline
    # 后端current_outline是从blueprint的起承转合完整转换的，是最准确的章节大纲
    # 前端data.outline可能包含占位符或错误分配的幕事件，不可信
    outline = current_outline if current_outline and current_outline.strip() else data.outline
    if data.chapter_index > 0 and outline:
        try:
            prev_ch = state.project.chapters[data.chapter_index - 1]
            prev_outline = prev_ch.get("outline", "")
            if not prev_outline and prev_ch.get("blueprint"):
                bp = prev_ch["blueprint"]
                parts = []
                intro = bp.get("intro", {})
                if intro:
                    parts.append("【起】%s — %s" % (intro.get("scene",""), intro.get("trigger","")))
                for dev in bp.get("development", []):
                    parts.append("【承】%s：%s" % (dev.get("scene",""), dev.get("event","")))
                climax = bp.get("climax", {})
                if climax:
                    parts.append("【转】%s — %s" % (climax.get("conflict",""), climax.get("twist","")))
                ending = bp.get("ending", {})
                if ending:
                    parts.append("【合】%s → %s" % (ending.get("new_state",""), ending.get("next_hook","")))
                prev_outline = "\n".join(parts)

            if prev_outline and outline.strip() == prev_outline.strip():
                # 大纲重复！保留原始大纲，将提示追加到context
                prev_content = state.project.get_content(data.chapter_index - 1)
                extra_ctx = ("注意：本章大纲与前一章相同，请勿重复前一章的内容。\n"
                          "前一章已经写了上述场景，本章请从前一章结尾处继续推进剧情。\n"
                          "前一章全文：\n" + prev_content + "\n\n"
                          "请基于前一章的结尾，编写后续剧情发展，场景和时间线要自然推进，不要回到前一章的开始。")
                if context:
                    context = extra_ctx + "\n\n" + context + "\n\n⚠️ 重要：本章大纲与前一章重复，必须写全新的剧情，不能重复前一章内容。"
                else:
                    context = extra_ctx + "\n\n⚠️ 重要：本章大纲与前一章重复，必须写全新的剧情，不能重复前一章内容。"
        except Exception:
            pass

    # 最后一章强制完结指令
    total_chapters = len(state.project.chapters) if state.project.chapters else 0
    is_last_chapter = (data.chapter_index >= total_chapters - 1) and total_chapters > 0
    if is_last_chapter:
        conclusion_directive = (
            "\n\n⚠️ 【重要：本章是最后一章，必须完结】\n"
            "1. 本章必须是整个故事的结局，所有主要伏笔必须收束\n"
            "2. 主角与反派的对抗必须有明确结果（胜负已分）\n"
            "3. 不能再埋新悬念或留开放结局，不能有'游戏才刚刚开始'之类的话\n"
            "4. 结尾要给出主角的最终状态和故事的核心主题升华\n"
            "5. 如果有感情线，要给出明确交代\n"
            "6. 最后一段应该是整个故事的收尾，而非新剧情的开始\n"
        )
        if context:
            context += conclusion_directive
        else:
            context = conclusion_directive.strip()
        outline += conclusion_directive

    result = gen.generate_and_validate(data.title, outline, context, chapter_index=data.chapter_index, max_retries=2, skill_rules=getattr(data, 'skill_rules', '') or '', use_distilled_memory=getattr(data, 'use_distilled_memory', True))
    content = result.get("content", "")

    # [DEPRECATED] 不再自动落盘、状态提取、向量记忆。
    # 需调用 /api/generate/confirm 显式保存（C4 事前确认流程）。
    return {
        "ok": result.get("ok", True),
        "content": content,
        "word_count": len(content),
        "warning": result.get("warning", ""),
        "validation_log": result.get("validation_log", []),
        "deprecated": True,
        "migrate_hint": "请改用 /api/generate/gate + /api/generate/confirm"
    }

@router.post("/gate")
def generate_with_gate(data: GenerateRequest):
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    gen = get_generator()
    result = gen.generate_and_validate(data.title, data.outline, data.context, chapter_index=data.chapter_index, max_retries=3, skill_rules=getattr(data, 'skill_rules', '') or '', use_distilled_memory=getattr(data, 'use_distilled_memory', True))
    return result

@router.post("/confirm")
def confirm_chapter(data: ConfirmRequest):
    """确认保存预览的章节内容（C4 事前确认流程）"""
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    content = data.content
    if not content:
        return err(ErrorCode.VALIDATION_ERROR, "内容为空")
    gen = get_generator()
    # 保存
    try:
        state.project.set_content(content, data.chapter_index)
        state.project.save_all()
    except Exception as e:
        logger.warning("confirm save chapter %d failed: %s", data.chapter_index+1, e)
    # 状态提取
    try:
        gen.apply_state_extraction(content, data.chapter_index + 1, data.title, validation_issues=data.validation_log)
    except Exception as e:
        logger.warning("state extraction chapter %d failed: %s", data.chapter_index+1, e)
    # 向量记忆注入
    try:
        from backend.services.project_service import get_vector_memory
        from backend.services.vector_memory import MemoryType
        vm = get_vector_memory()
        if vm:
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip() and len(p.strip()) > 50]
            for pi, para in enumerate(paragraphs):
                vm.add_memory(
                    content=para,
                    memory_type=MemoryType.EVENT,
                    importance=0.6,
                    metadata={"chapter": data.chapter_index + 1, "chapter_title": data.title, "paragraph": pi}
                )
    except Exception as e:
        logger.warning("vector memory chapter %d failed: %s", data.chapter_index+1, e)
    return {"ok": True, "word_count": len(content)}

@router.post("/extract-state")
def extract_state(data: ExtractStateRequest):
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    gen = get_generator()
    content = data.content
    chapter_idx = data.chapter_idx
    title = data.title
    result = gen.apply_state_extraction(content, chapter_idx, title)
    return {"ok": True, "extracted": result}
