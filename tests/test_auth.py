# -*- coding: utf-8 -*-
"""书斋 V66 — 认证系统测试

覆盖：
1. auth 模块单元测试：密码哈希/验证、Token 生成/验证/过期、请求验证
2. API 集成测试：注册/登录/状态/登出
3. 边界与错误：空用户名、弱密码、重复注册、错误密码、Token 篡改
"""
import time
import sys
import os
import pytest

# 确保 tests 目录在路径中
_test_dir = os.path.dirname(os.path.abspath(__file__))
if _test_dir not in sys.path:
    sys.path.insert(0, _test_dir)

# 单用户模式下认证已从产品移除（backend.auth 不存在），此时整个模块跳过
auth_mod = pytest.importorskip(
    "backend.auth",
    reason="当前为单用户模式，backend.auth 不存在，认证测试不适用",
)
from conftest import assert_ok, assert_error


# ═══════════════════════════════════════════
# Unit Tests — 密码哈希与验证
# ═══════════════════════════════════════════

class TestPasswordHashing:
    """密码哈希为 PBKDF2-SHA256，应具备盐值唯一性和恒定时比较。"""

    def test_hash_produces_unique_salts(self):
        salt1, _ = auth_mod._hash_password("test1234")
        salt2, _ = auth_mod._hash_password("test1234")
        assert salt1 != salt2, "相同密码应产生不同盐值"

    def test_hash_output_is_hex_string(self):
        salt, h = auth_mod._hash_password("test1234")
        assert len(salt) == 32, "盐值应为 32 字符十六进制"
        assert len(h) == 64, "哈希应为 64 字符十六进制"

    def test_verify_password_matches(self):
        salt, h = auth_mod._hash_password("mysecret")
        assert auth_mod._verify_password("mysecret", salt, h) is True

    def test_verify_password_rejects_wrong(self):
        salt, h = auth_mod._hash_password("mysecret")
        assert auth_mod._verify_password("wrongpassword", salt, h) is False

    def test_verify_password_case_sensitive(self):
        salt, h = auth_mod._hash_password("MySecret")
        assert auth_mod._verify_password("mysecret", salt, h) is False

    def test_verify_password_empty(self):
        salt, h = auth_mod._hash_password("")
        assert auth_mod._verify_password("", salt, h) is True
        assert auth_mod._verify_password("x", salt, h) is False


# ═══════════════════════════════════════════
# Unit Tests — Token
# ═══════════════════════════════════════════

class TestTokenCreationAndVerification:

    def test_token_roundtrip(self):
        token = auth_mod._create_token("alice")
        payload = auth_mod._verify_token(token)
        assert payload is not None
        assert payload["username"] == "alice"

    def test_token_verification_rejects_tampered(self):
        token = auth_mod._create_token("alice")
        # 篡改 payload 部分：换个字符
        tampered = "xxx" + token[2:]
        assert auth_mod._verify_token(tampered) is None

    def test_token_verification_rejects_empty(self):
        assert auth_mod._verify_token("") is None

    def test_token_verification_rejects_malformed(self):
        assert auth_mod._verify_token("not.a.token.format") is None

    def test_token_has_expiry(self):
        token = auth_mod._create_token("bob")
        payload = auth_mod._verify_token(token)
        assert "exp" in payload
        # 7 天有效期，exp 距离现在约 604800 秒
        exp = payload["exp"]
        now = int(time.time())
        assert exp > now
        assert exp - now < 605000, f"Token expiry too far: {exp - now} seconds"


# ═══════════════════════════════════════════
# Unit Tests — 注册与登录（模块层）
# ═══════════════════════════════════════════

class TestRegisterModule:

    def test_register_new_user_succeeds(self):
        result = auth_mod.register("newbie", "pass1234")
        assert result["ok"] is True
        assert "token" in result
        assert result["username"] == "newbie"
        # 认证变为启用
        assert auth_mod.is_auth_enabled() is True

    def test_register_duplicate_username_rejected(self):
        auth_mod.register("newbie", "pass1234")
        result = auth_mod.register("newbie", "different")
        assert result["ok"] is False
        assert "已存在" in str(result.get("error", ""))

    def test_register_empty_username_rejected(self):
        result = auth_mod.register("", "pass1234")
        assert result["ok"] is False

    def test_register_short_username_rejected(self):
        result = auth_mod.register("x", "pass1234")
        assert result["ok"] is False

    def test_register_long_username_rejected(self):
        result = auth_mod.register("x" * 21, "pass1234")
        assert result["ok"] is False

    def test_register_short_password_rejected(self):
        result = auth_mod.register("validuser", "ab")
        assert result["ok"] is False
        assert "4个字符" in str(result.get("error", ""))

    def test_user_count_increments(self):
        assert auth_mod.get_user_count() == 0
        auth_mod.register("u1", "p1234")
        assert auth_mod.get_user_count() == 1
        auth_mod.register("u2", "p5678")
        assert auth_mod.get_user_count() == 2


class TestLoginModule:

    def test_login_with_correct_credentials(self):
        auth_mod.register("alice", "secret1")
        result = auth_mod.login("alice", "secret1")
        assert result["ok"] is True
        assert "token" in result

    def test_login_with_wrong_password(self):
        auth_mod.register("alice", "secret1")
        result = auth_mod.login("alice", "wrong")
        assert result["ok"] is False

    def test_login_nonexistent_user(self):
        result = auth_mod.login("ghost", "whatever")
        assert result["ok"] is False

    def test_login_empty_credentials(self):
        result = auth_mod.login("", "")
        assert result["ok"] is False


# ═══════════════════════════════════════════
# Unit Tests — verify_request
# ═══════════════════════════════════════════

class TestVerifyRequest:

    def test_returns_default_when_auth_disabled(self):
        # 默认 auth 未启用
        result = auth_mod.verify_request("")
        assert result is not None
        assert result.get("anonymous") is True

    def test_returns_none_when_no_token_and_auth_enabled(self):
        auth_mod.register("uu", "pass1234")  # 启用认证
        result = auth_mod.verify_request("")
        assert result is None

    def test_returns_payload_with_bearer_prefix(self):
        token = auth_mod.register("uu", "pass1234")["token"]
        payload = auth_mod.verify_request(f"Bearer {token}")
        assert payload is not None
        assert payload["username"] == "uu"

    def test_returns_payload_without_bearer_prefix(self):
        token = auth_mod.register("uu", "pass1234")["token"]
        payload = auth_mod.verify_request(token)  # 无 Bearer 前缀
        assert payload is not None
        assert payload["username"] == "uu"

    def test_returns_none_for_tampered_token(self):
        auth_mod.register("uu", "pass1234")
        payload = auth_mod.verify_request("Bearer tampered.token")
        assert payload is None


# ═══════════════════════════════════════════
# API Integration Tests — 注册接口
# ═══════════════════════════════════════════

class TestRegisterAPI:

    def test_register_returns_token(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "newuser",
            "password": "pass1234"
        })
        body = assert_ok(resp)
        assert "token" in body
        assert body.get("username") == "newuser"

    def test_register_status_after_first_user(self, client):
        client.post("/api/auth/register", json={
            "username": "owner", "password": "pass1234"
        })
        resp = client.get("/api/auth/status")
        body = assert_ok(resp)
        # 注册第一个用户后，auth 自动生效，未带 token 时 auth_required 为 True
        assert body["auth_required"] is True

    def test_register_duplicate_returns_409(self, client):
        client.post("/api/auth/register", json={
            "username": "dup", "password": "pass1234"
        })
        resp = client.post("/api/auth/register", json={
            "username": "dup", "password": "password"
        })
        body = assert_error(resp, status=200)
        # auth router 用 auth.register，返回 ok=false 但仍为 200

    def test_register_short_password(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "user1", "password": "a"
        })
        body = assert_error(resp, status=200)

    def test_register_empty_username(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "", "password": "pass1234"
        })
        body = assert_error(resp, status=200)


# ═══════════════════════════════════════════
# API Integration Tests — 登录接口
# ═══════════════════════════════════════════

class TestLoginAPI:

    def test_login_with_valid_credentials(self, client):
        client.post("/api/auth/register", json={
            "username": "alice", "password": "secret1"
        })
        resp = client.post("/api/auth/login", json={
            "username": "alice", "password": "secret1"
        })
        body = assert_ok(resp)
        assert "token" in body
        assert body.get("username") == "alice"

    def test_login_with_wrong_password(self, client):
        client.post("/api/auth/register", json={
            "username": "alice", "password": "secret1"
        })
        resp = client.post("/api/auth/login", json={
            "username": "alice", "password": "badpassword"
        })
        body = resp.json()
        assert body["ok"] is False

    def test_login_nonexistent_user(self, client):
        resp = client.post("/api/auth/login", json={
            "username": "ghost", "password": "whatever"
        })
        body = resp.json()
        assert body["ok"] is False

    def test_login_empty_fields(self, client):
        resp = client.post("/api/auth/login", json={
            "username": "", "password": ""
        })
        # API_CONTRACT.md §1.2：空字符串对 str 字段是合法值，不触发 422；
        # 业务错误以 200 + err() 信封返回
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False


# ═══════════════════════════════════════════
# API Integration Tests — 认证状态接口
# ═══════════════════════════════════════════

class TestAuthStatusAPI:

    def test_status_no_users_show_auth_not_required(self, client):
        resp = client.get("/api/auth/status")
        body = assert_ok(resp)
        assert body["auth_required"] is False
        assert body["user_count"] == 0

    def test_status_with_users_and_valid_token(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "user1", "password": "pass1234"
        })
        token = resp.json()["token"]
        client.headers["Authorization"] = f"Bearer {token}"

        resp = client.get("/api/auth/status")
        body = assert_ok(resp)
        assert body["auth_required"] is False
        assert body["username"] == "user1"

    def test_status_with_users_but_no_token(self, client):
        client.post("/api/auth/register", json={
            "username": "user1", "password": "pass1234"
        })
        # 不带 Authorization 头
        resp = client.get("/api/auth/status")
        body = assert_ok(resp)
        assert body["auth_required"] is True


# ═══════════════════════════════════════════
# API Integration Tests — 登出接口
# ═══════════════════════════════════════════

class TestLogoutAPI:

    def test_logout_returns_ok(self, client):
        resp = client.get("/api/auth/logout")
        body = assert_ok(resp)
