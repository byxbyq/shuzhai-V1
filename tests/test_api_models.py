# -*- coding: utf-8 -*-
"""书斋 V66 — API 契约模型测试

验证 Pydantic 请求模型符合 API_CONTRACT.md 定义的字段/类型/默认值/必填约束。
覆盖 validate、generate、auth、chapter、memory 等路由的请求模型。
"""
import pytest
from pydantic import ValidationError


# ═══════════════════════════════════════════
# Import all request models
# ═══════════════════════════════════════════

from backend.routers.generate import (
    CancelGenerateRequest,
    ExtractStateRequest,
    NextChapterOutlineRequest,
    GenerateRequest,
    CoverageRequest,
)
from backend.routers.validate import (
    ExtendedAuditRequest,
    ConsistencyRequest,
    OutlineQualityRequest,
    SettingsQualityRequest,
    CharactersQualityRequest,
)


# ═══════════════════════════════════════════
# Validate Router Models
# ═══════════════════════════════════════════

class TestExtendedAuditRequest:

    def test_default_values(self):
        req = ExtendedAuditRequest()
        assert req.content == ""
        assert req.chapter_index == 0

    def test_custom_fields(self):
        req = ExtendedAuditRequest(content="测试内容", chapter_index=5)
        assert req.content == "测试内容"
        assert req.chapter_index == 5

    def test_extra_fields_ignored(self):
        req = ExtendedAuditRequest(content="x", nonsense=999)
        assert not hasattr(req, "nonsense")


class TestConsistencyRequest:

    def test_default_values(self):
        req = ConsistencyRequest()
        assert req.content == ""
        assert req.index == -1

    def test_custom_fields(self):
        req = ConsistencyRequest(content="测试", index=3)
        assert req.content == "测试"
        assert req.index == 3


class TestOutlineQualityRequest:

    def test_no_param_creation(self):
        """无参模型应正常创建。"""
        req = OutlineQualityRequest()
        assert req is not None


class TestSettingsQualityRequest:

    def test_no_param_creation(self):
        req = SettingsQualityRequest()
        assert req is not None


class TestCharactersQualityRequest:

    def test_no_param_creation(self):
        req = CharactersQualityRequest()
        assert req is not None


# ═══════════════════════════════════════════
# Generate Router Models (extending existing tests)
# ═══════════════════════════════════════════

class TestGenerateRequestModel:

    def test_default_values(self):
        req = GenerateRequest(
            title="第一章",
            outline="主角登场",
            context="玄幻世界",
            chapter_index=1,
        )
        assert req.title == "第一章"
        assert req.outline == "主角登场"
        assert req.context == "玄幻世界"
        assert req.chapter_index == 1

    def test_title_required(self):
        with pytest.raises(ValidationError):
            GenerateRequest(outline="x", chapter_index=1)


class TestCoverageRequest:

    def test_default_values(self):
        req = CoverageRequest()
        assert req.chapter_index == 0

    def test_custom_index(self):
        req = CoverageRequest(chapter_index=3)
        assert req.chapter_index == 3


class TestNextChapterOutlineRequest:

    def test_default_values(self):
        req = NextChapterOutlineRequest()
        assert req.current_chapter_index == 0

    def test_custom_index(self):
        req = NextChapterOutlineRequest(current_chapter_index=2)
        assert req.current_chapter_index == 2


class TestCancelGenerateRequest:

    def test_default_values(self):
        req = CancelGenerateRequest()
        assert req.task_id == ""

    def test_custom_task_id(self):
        req = CancelGenerateRequest(task_id="abc123")
        assert req.task_id == "abc123"


class TestExtractStateRequest:

    def test_default_values(self):
        req = ExtractStateRequest()
        assert req.content == ""
        assert req.chapter_idx == 1
        assert req.title == ""

    def test_custom_fields(self):
        req = ExtractStateRequest(content="内容", chapter_idx=3, title="第一章")
        assert req.content == "内容"
        assert req.chapter_idx == 3
        assert req.title == "第一章"


# ═══════════════════════════════════════════
# Auth Router Models
# ═══════════════════════════════════════════

class TestAuthRequestModels:
    """auth_router 的 RegisterReq / LoginReq。

    单用户模式下认证已移除（backend.routers.auth_router 不存在），此时跳过。
    """

    def _get_auth_models(self):
        mod = pytest.importorskip(
            "backend.routers.auth_router",
            reason="当前为单用户模式，auth_router 不存在",
        )
        return mod.RegisterReq, mod.LoginReq

    def test_register_req_minimal(self):
        RegisterReq, _ = self._get_auth_models()
        req = RegisterReq(username="user1", password="pass1234")
        assert req.username == "user1"
        assert req.password == "pass1234"

    def test_register_req_username_required(self):
        RegisterReq, _ = self._get_auth_models()
        with pytest.raises(ValidationError):
            RegisterReq(password="pass1234")

    def test_login_req_minimal(self):
        _, LoginReq = self._get_auth_models()
        req = LoginReq(username="user1", password="pass1234")
        assert req.username == "user1"
        assert req.password == "pass1234"


# ═══════════════════════════════════════════
# Response Envelope Contract
# ═══════════════════════════════════════════

class TestResponseEnvelope:
    """验证 err() 工厂函数产出符合 API_CONTRACT.md 定义的统一响应信封。"""

    def test_err_has_ok_false(self):
        from backend.api_models import err, ErrorCode
        result = err(ErrorCode.NOT_FOUND, "资源不存在")
        assert result["ok"] is False
        assert result["error"]["code"] == "NOT_FOUND"
        assert result["error"]["message"] == "资源不存在"

    def test_err_with_details(self):
        from backend.api_models import err, ErrorCode
        result = err(ErrorCode.VALIDATION_ERROR, "参数错误", details={"field": "title"})
        assert result["ok"] is False
        assert result["error"]["code"] == "VALIDATION_ERROR"
        assert result["error"]["details"] == {"field": "title"}

    def test_err_no_extra_keys(self):
        from backend.api_models import err, ErrorCode
        result = err(ErrorCode.AUTH_FAILED, "认证失败")
        assert set(result.keys()) == {"ok", "error"}
        assert set(result["error"].keys()) == {"code", "message"}
