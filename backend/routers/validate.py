# -*- coding: utf-8 -*-
"""验证路由 — 薄转发层，仅负责 router 注册和子路由 include"""
from fastapi import APIRouter

# 再导出：generator.py 与 tests 直接从本模块导入这些符号，禁止删除（__all__ 声明给 ruff 识别）
__all__ = [
    "router",
    "ValidateRequest", "AIFlavorRequest", "StyleExtractRequest", "StyleCompareRequest",
    "PowerCollapseRequest", "ExtendedAuditRequest", "ConsistencyRequest",
    "OutlineQualityRequest", "SettingsQualityRequest", "CharactersQualityRequest",
    "EditorialReviewRequest", "MarketReviewRequest", "EDITORIAL_PROMPT_MODES",
    "AllInOneRequest", "BatchValidateRequest",
    "ProjectReviewRequest", "FixChapterRequest", "FixAllRequest", "FixParagraphRequest",
    "_do_editorial_review", "_do_market_review",
]

from backend.routers.validate_models import (
    ValidateRequest, AIFlavorRequest, StyleExtractRequest, StyleCompareRequest,
    PowerCollapseRequest, ExtendedAuditRequest, ConsistencyRequest,
    OutlineQualityRequest, SettingsQualityRequest, CharactersQualityRequest,
    EditorialReviewRequest, MarketReviewRequest, EDITORIAL_PROMPT_MODES,
)
from backend.routers.validate_batch import AllInOneRequest, BatchValidateRequest, router as validate_batch_router
from backend.services.project_quality import ProjectReviewRequest
from backend.services.chapter_fixer import FixChapterRequest, FixAllRequest, FixParagraphRequest
from backend.routers.audit_proxy import router as audit_proxy_router
from backend.routers.validate_item import router as validate_item_router
from backend.services.editorial_review import _do_editorial_review, _do_market_review, router as editorial_review_router
from backend.services.validate_all_in_one import router as validate_all_in_one_router
from backend.services.consistency_check import router as consistency_check_router
from backend.services.project_quality import router as project_quality_router
from backend.services.chapter_fixer import router as chapter_fixer_router

router = APIRouter(prefix="/api/validate")
router.include_router(audit_proxy_router)
router.include_router(validate_all_in_one_router)
router.include_router(validate_batch_router)
router.include_router(consistency_check_router)
router.include_router(project_quality_router)
# 注意：chapter_fixer 的具体路由（fix-all/fix/deai-deep）必须注册在
# validate_item 的通配路由 /{check_type} 之前，否则会被拦截
router.include_router(chapter_fixer_router)
router.include_router(validate_item_router)
router.include_router(editorial_review_router)
