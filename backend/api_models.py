# -*- coding: utf-8 -*-
"""书斋 V66 — 统一 API 响应/请求模型

定义全项目共享的接口契约类型，确保：
- 成功响应：{ok: true, data: T}
- 错误响应：{ok: false, error: {code, message, details?}}
- 分页响应：{ok: true, data: [...], pagination: {...}}
"""
from typing import Generic, TypeVar, Any, List
from pydantic import BaseModel

T = TypeVar("T")


# ═══════════════════════════════════════════
# 成功响应包装
# ═══════════════════════════════════════════

class APIResponse(BaseModel, Generic[T]):
    """统一成功响应"""
    ok: bool = True
    data: T


# ═══════════════════════════════════════════
# 错误响应
# ═══════════════════════════════════════════

class APIErrorDetail(BaseModel):
    """错误详情"""
    code: str          # 机器可读错误码，如 "PROJECT_NOT_OPEN"
    message: str       # 人类可读描述
    details: Any = None  # 附加信息（字段校验错误列表等）


class APIError(BaseModel):
    """统一错误响应"""
    ok: bool = False
    error: APIErrorDetail


# ═══════════════════════════════════════════
# 分页
# ═══════════════════════════════════════════

class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class PaginatedData(BaseModel, Generic[T]):
    items: List[T]
    pagination: PaginationMeta


# ═══════════════════════════════════════════
# 工厂函数（便捷构造，不引入运行时依赖）
# ═══════════════════════════════════════════

def ok(data: Any = None) -> dict:
    """构造统一成功响应"""
    return {"ok": True, "data": data}


def err(code: str, message: str, details: Any = None) -> dict:
    """构造统一错误响应"""
    d = {"ok": False, "error": {"code": code, "message": message}}
    if details is not None:
        d["error"]["details"] = details
    return d


def paginated(items: list, page: int, page_size: int, total: int) -> dict:
    """构造分页响应"""
    total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 0
    return {
        "ok": True,
        "data": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": total_pages,
        },
    }


# ═══════════════════════════════════════════
# 通用分页参数（Query）
# ═══════════════════════════════════════════

from pydantic import Field


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1, description="页码，从 1 开始")
    page_size: int = Field(default=20, ge=1, le=100, description="每页条数")


# ═══════════════════════════════════════════
# 错误码常量
# ═══════════════════════════════════════════

class ErrorCode:
    PROJECT_NOT_OPEN = "PROJECT_NOT_OPEN"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CHAPTER_EMPTY = "CHAPTER_EMPTY"
    GENERATION_FAILED = "GENERATION_FAILED"
    IMPORT_FAILED = "IMPORT_FAILED"
    PARSE_FAILED = "PARSE_FAILED"
    AI_FAILED = "AI_FAILED"
    AUTH_FAILED = "AUTH_FAILED"
    AUTH_CONFLICT = "AUTH_CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    DUPLICATE = "DUPLICATE"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    SYNC_FAILED = "SYNC_FAILED"
    EXPORT_FAILED = "EXPORT_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
