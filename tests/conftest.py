# -*- coding: utf-8 -*-
"""书斋 V66 — 测试基础设施（conftest.py）

提供所有测试共享的 fixtures：FastAPI TestClient、临时用户数据库、
认证 Token、临时项目目录等。
"""
import sys
import os
import tempfile
import shutil
import pytest
from pathlib import Path

# 确保项目路径在 sys.path 中
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))


# ═══════════════════════════════════════════
# Auth module state isolation helpers
# ═══════════════════════════════════════════

def _try_import_auth():
    """尝试导入 backend.auth；单用户模式下该模块不存在，返回 None。"""
    try:
        import backend.auth as auth_mod
        return auth_mod
    except ModuleNotFoundError:
        return None


def auth_available() -> bool:
    """当前部署是否包含认证模块（单用户模式为 False）。"""
    return _try_import_auth() is not None


def reset_auth_module():
    """重置 auth 模块的全局状态到干净初始值。

    测试之间需要隔离，避免前一个测试的注册/登录状态导致后继测试失败。
    单用户模式（无 backend.auth）下为空操作。
    """
    auth_mod = _try_import_auth()
    if auth_mod is None:
        return
    auth_mod._users = {}
    auth_mod._auth_enabled = False


def setup_auth_with_users(users: dict):
    """向 auth 模块注入已注册用户（{username: {salt, hash}}）。

    同时开启认证模式，模拟已有注册用户的场景。
    单用户模式（无 backend.auth）下为空操作。
    """
    auth_mod = _try_import_auth()
    if auth_mod is None:
        return
    auth_mod._users = dict(users)
    auth_mod._auth_enabled = True


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════

@pytest.fixture(autouse=True)
def isolated_auth():
    """每个测试前后自动重置 auth 模块全局状态，保证隔离。"""
    reset_auth_module()
    yield
    reset_auth_module()


@pytest.fixture(scope="module")
def app():
    """FastAPI app 实例（模块级复用）。"""
    from server import app
    return app


@pytest.fixture
def client(app):
    """httpx TestClient（不预置认证头）。"""
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client):
    """注册一个测试用户并返回带 Token 的 TestClient。

    返回 (client, token, username) 三元组。
    单用户模式（无 backend.auth / 无 /api/auth 端点）下跳过依赖本 fixture 的测试。
    """
    if not auth_available():
        pytest.skip("当前为单用户模式，backend.auth 不存在，跳过认证相关测试")
    reset_auth_module()
    username = "testuser"
    password = "test1234"

    resp = client.post("/api/auth/register", json={
        "username": username,
        "password": password
    })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert "token" in resp.json()

    token = resp.json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client, token, username


@pytest.fixture
def temp_project_dir():
    """创建临时项目目录，测试结束后自动清理。"""
    tmp = tempfile.mkdtemp(prefix="shuzhai_test_")
    yield tmp
    if os.path.exists(tmp):
        shutil.rmtree(tmp, ignore_errors=True)


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════

def assert_ok(resp, status=200):
    """断言 HTTP 状态和 ok 字段都为预期值。"""
    assert resp.status_code == status, f"Expected {status}, got {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body["ok"] is True, f"Expected ok=true, got {body}"
    return body


def assert_error(resp, status=400, error_code=None):
    """断言返回错误响应。"""
    body = resp.json()
    if status:
        assert resp.status_code == status, f"Expected {status}, got {resp.status_code}: {resp.text[:200]}"
    assert body["ok"] is False, f"Expected ok=false, got {body}"
    if error_code:
        assert body.get("error", {}).get("code") == error_code, \
            f"Expected error code '{error_code}', got {body.get('error', {}).get('code')}"
    return body
