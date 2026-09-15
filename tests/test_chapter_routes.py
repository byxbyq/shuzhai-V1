# -*- coding: utf-8 -*-
"""书斋 V66 — 章节路由集成测试

覆盖 /api/chapter 与 /api/check 端点：列表、加载、添加、完整性检查。
遵循 API_CONTRACT.md §3.2 定义的契约：
- 业务错误以 HTTP 200 + err() 统一信封返回：{ok:false, error:{code, message}}
- 未打开项目的错误码固定为 PROJECT_NOT_OPEN
- 422 仅表示 Pydantic 请求体校验失败（缺少必填字段/类型错误）
"""
import sys
import os
import gc
import shutil
import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
if _test_dir not in sys.path:
    sys.path.insert(0, _test_dir)

from conftest import assert_ok, assert_error


def _release_project_handles():
    """关闭当前项目的 SQLite 连接并回收引用，避免 Windows 下目录被占用无法清理。"""
    from backend.services.project_service import state
    proj = state.project
    state.project = None
    if proj is not None:
        try:
            proj._get_db().close()
        except Exception:
            pass
    gc.collect()


@pytest.fixture(autouse=True)
def clean_project_state():
    """每个测试前后重置全局项目状态，保证用例互相隔离、结果确定。"""
    from backend.services.project_service import state
    state.project = None
    yield
    state.project = None


def _create_project(client, title="章节契约测试", length=2):
    """通过契约接口创建项目，返回响应体（调用方负责清理目录）。"""
    resp = client.post("/api/project/new", json={"title": title, "length": length})
    assert resp.status_code == 200, f"项目创建失败: {resp.status_code} {resp.text[:200]}"
    body = resp.json()
    assert body["ok"] is True
    return body


@pytest.fixture
def cleanup_project_dir():
    """记录待清理的项目目录，测试结束后统一清理。"""
    holder = {"path": None}
    yield holder
    _release_project_handles()
    from backend.services.project_service import PROJECTS_DIR
    base = os.path.realpath(PROJECTS_DIR)
    path = holder["path"]
    if path:
        real = os.path.realpath(path)
        if real.startswith(base + os.sep) and os.path.isdir(real):
            shutil.rmtree(real)


class TestChapterList:

    def test_list_supports_pagination_defaults(self, client):
        """章节列表接受分页参数；未打开项目时返回 200 + PROJECT_NOT_OPEN。"""
        resp = client.get("/api/chapter/list?page=1&page_size=20")
        assert resp.status_code == 200
        assert_error(resp, status=200, error_code="PROJECT_NOT_OPEN")

    def test_list_without_project_returns_error(self, client):
        """未打开项目时章节列表返回 200 + err() 信封，不应 crash。"""
        resp = client.get("/api/chapter/list")
        assert resp.status_code == 200
        body = assert_error(resp, status=200, error_code="PROJECT_NOT_OPEN")
        assert "data" not in body

    def test_list_with_project_returns_paginated(self, client, cleanup_project_dir):
        """已打开项目时返回 200 + ok=true：data 为章节数组并带分页元信息。"""
        created = _create_project(client)
        cleanup_project_dir["path"] = created["path"]
        resp = client.get("/api/chapter/list?page=1&page_size=20")
        assert resp.status_code == 200
        body = assert_ok(resp)
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 2
        assert body["pagination"]["total_items"] == 2
        assert "current" in body


class TestChapterLoad:

    def test_load_without_project_returns_error(self, client):
        """未打开项目时加载章节返回 200 + PROJECT_NOT_OPEN。"""
        resp = client.get("/api/chapter/load?index=0")
        assert resp.status_code == 200
        assert_error(resp, status=200, error_code="PROJECT_NOT_OPEN")


class TestChapterAdd:

    def test_add_without_project_returns_error(self, client):
        """未打开项目时添加章节返回 200 + PROJECT_NOT_OPEN，不应 crash。"""
        resp = client.post("/api/chapter/add", json={
            "title": "第一章", "vol_index": 0
        })
        assert resp.status_code == 200
        assert_error(resp, status=200, error_code="PROJECT_NOT_OPEN")

    def test_add_missing_title_422(self, client):
        """负例：缺少必填字段 title 时 Pydantic 校验失败，精确返回 422。"""
        resp = client.post("/api/chapter/add", json={"vol_index": 0})
        assert resp.status_code == 422


class TestCheckEndpoint:

    def test_check_without_project_returns_error(self, client):
        """未打开项目时完整性检查返回 200 + PROJECT_NOT_OPEN。"""
        resp = client.post("/api/check/completeness", json={
            "content": "测试内容",
        })
        assert resp.status_code == 200
        assert_error(resp, status=200, error_code="PROJECT_NOT_OPEN")

    def test_check_missing_content_422(self, client):
        """负例：缺少必填字段 content 时 Pydantic 校验失败，精确返回 422。"""
        resp = client.post("/api/check/completeness", json={"title": "x"})
        assert resp.status_code == 422
