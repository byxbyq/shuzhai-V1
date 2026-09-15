# -*- coding: utf-8 -*-
import logging
from fastapi import APIRouter

from backend.services.project_service import get_generator
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)

from backend.routers.validate_models import AIFlavorRequest, ExtendedAuditRequest, PowerCollapseRequest, StyleCompareRequest, StyleExtractRequest

# ═══════════════════════════════════════════
# 扩展审计端点（纯规则，不消耗Token）
# ═══════════════════════════════════════════

router = APIRouter()

@router.post("/ai-flavor")
def validate_ai_flavor(data: AIFlavorRequest):
    """AI味检测 — 套话密度/公式化转折/叙述者越权/塑料描写"""
    from backend.services.audit import detect_ai_flavor
    if not data.content:
        return err(ErrorCode.VALIDATION_ERROR, "缺少content")
    result = detect_ai_flavor(data.content)
    return {"ok": True, **result}


@router.post("/style-extract")
def validate_style_extract(data: StyleExtractRequest):
    """文风指纹提取 — 从参考文本提取统计指纹（零Token）"""
    from backend.services.audit import extract_style_fingerprint
    if not data.text:
        return err(ErrorCode.VALIDATION_ERROR, "缺少text")
    result = extract_style_fingerprint(data.text, data.source_name)
    return {"ok": True, "fingerprint": result}


@router.post("/style-compare")
def validate_style_compare(data: StyleCompareRequest):
    """文风偏离度对比 — 正文 vs 参考指纹（零Token）"""
    from backend.services.audit import compare_style_fingerprint
    if not data.content or not data.fingerprint:
        return err(ErrorCode.VALIDATION_ERROR, "缺少content或fingerprint")
    result = compare_style_fingerprint(data.content, data.fingerprint)
    return {"ok": True, **result}


@router.post("/power-collapse")
def validate_power_collapse(data: PowerCollapseRequest):
    """战力崩坏检测 — 境界跳跃/死亡复活/越级战胜"""
    from backend.services.audit import detect_power_collapse
    if not data.content:
        return err(ErrorCode.VALIDATION_ERROR, "缺少content")

    characters = []
    gen = get_generator()
    if gen and gen.ledger:
        for name, cs in gen.ledger.character_states.items():
            characters.append({
                "name": name,
                "realm": getattr(cs, 'realm', ''),
                "prev_realm": getattr(cs, 'prev_realm', ''),
                "status": "alive" if cs.is_alive else "dead",
            })

    result = detect_power_collapse(data.content, data.chapter_index, characters)
    return {"ok": True, **result}


@router.post("/extended-audit")
def validate_extended_audit(data: ExtendedAuditRequest):
    """综合扩展审计 — AI味 + 战力崩坏 + 逾期伏笔"""
    from backend.services.audit import run_extended_audit
    content = data.content
    chapter_index = data.chapter_index
    if not content:
        return err(ErrorCode.VALIDATION_ERROR, "缺少content")

    characters = []
    overdue_hooks = []
    gen = get_generator()
    if gen and gen.ledger:
        for name, cs in gen.ledger.character_states.items():
            characters.append({
                "name": name,
                "realm": getattr(cs, 'realm', ''),
                "prev_realm": getattr(cs, 'prev_realm', ''),
                "status": "alive" if cs.is_alive else "dead",
            })
        try:
            overdue = gen.ledger.get_overdue_hooks(chapter_index)
            if overdue:
                overdue_hooks = [{"content": h.content, "chapter": h.expected_recovery_chapter} for h in overdue]
        except Exception:
            pass

    result = run_extended_audit(content, chapter_index, characters, overdue_hooks)
    return {"ok": True, **result}

