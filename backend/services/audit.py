# -*- coding: utf-8 -*-
"""审计模块 — 薄转发层，向后兼容 re-export"""

# 再导出：generator.py / audit_proxy.py / validate_batch.py 直接从本模块导入，禁止删除
__all__ = [
    "_line_number", "_paragraph_index", "_context_snippet",
    "_find_all_positions", "_find_word_positions",
    "AI_BUZZWORDS",
    "detect_ai_flavor", "compute_ai_score",
    "detect_power_collapse", "detect_logic_gaps", "detect_character_break",
    "detect_pov_drift", "detect_setting_conflict", "detect_spatial_consistency",
    "detect_climax_missing",
    "run_extended_audit",
    "extract_style_fingerprint", "compare_style_fingerprint",
]

# 工具函数
from backend.services.audit_utils import (
    _line_number, _paragraph_index, _context_snippet,
    _find_all_positions, _find_word_positions,
)

# 词表
from backend.services.audit_vocab import AI_BUZZWORDS

# AI味检测
from backend.services.ai_flavor import detect_ai_flavor, compute_ai_score

# 各维检测器
from backend.services.detect_power import detect_power_collapse
from backend.services.detect_logic import detect_logic_gaps
from backend.services.detect_character import detect_character_break
from backend.services.detect_pov import detect_pov_drift
from backend.services.detect_setting import detect_setting_conflict
from backend.services.detect_spatial import detect_spatial_consistency
from backend.services.detect_climax import detect_climax_missing

# 综合审计
from backend.services.extended_audit import run_extended_audit

# 文风指纹
from backend.services.style_fingerprint import (
    extract_style_fingerprint, compare_style_fingerprint,
)
