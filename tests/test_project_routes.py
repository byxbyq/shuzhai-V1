# -*- coding: utf-8 -*-
"""书斋 V66 — 项目路由集成测试

覆盖 /api/project 端点：状态、创建、信息、列表、保存。
遵循 API_CONTRACT.md §3.1 定义的契约：
- 业务成功与业务错误均以 HTTP 200 返回，以 ok 字段区分
- 422 仅表示 Pydantic 请求体校验失败（缺少必填字段/类型错误）
- 测试环境不触发 auto_init_project，state.project 初始为 None
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


@pytest.fixture
def created_projects():
    """收集测试中创建的项目目录，测试结束后统一清理。"""
    paths = []
    yield paths
    _release_project_handles()
    from backend.services.project_service import PROJECTS_DIR
    base = os.path.realpath(PROJECTS_DIR)
    for p in paths:
        real = os.path.realpath(p)
        # 安全护栏：只允许清理项目根目录之下的子目录
        if real.startswith(base + os.sep) and os.path.isdir(real):
            shutil.rmtree(real)


class TestProjectStatus:

    def test_status_no_project_open(self, client):
        """未打开项目时 /api/project/status 返回 200，project 字段为 None。"""
        resp = client.get("/api/project/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["project"] is None

    def test_status_with_auth(self, auth_client):
        """带认证时状态接口仍可访问（auth status 不能阻塞项目接口）。"""
        client, token, username = auth_client
        resp = client.get("/api/project/status")
        assert resp.status_code == 200


class TestProjectNew:

    def test_create_project_returns_ok(self, client, created_projects):
        """合法请求体创建项目返回 200 且 ok=true，携带 title/path。"""
        resp = client.post("/api/project/new", json={
            "title": "契约测试小说A",
            "genre": "仙侠",
            "length": 2,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["title"] == "契约测试小说A"
        assert "path" in body
        created_projects.append(body["path"])

    def test_create_project_with_minimal_fields(self, client, created_projects):
        """仅必填字段 title 即可创建，返回 200 且 ok=true。"""
        resp = client.post("/api/project/new", json={"title": "契约测试小说B"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        created_projects.append(body["path"])

    def test_create_project_empty_title_accepted(self, client, created_projects):
        """空标题是合法字符串，Pydantic 不拒绝：返回 200 且 ok=true（见 API_CONTRACT.md §3.1）。"""
        resp = client.post("/api/project/new", json={
            "title": "",
            "genre": "",
            "length": 1,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        created_projects.append(body["path"])

    def test_create_project_missing_title_422(self, client):
        """负例：缺少必填字段 title 时 Pydantic 校验失败，精确返回 422。"""
        resp = client.post("/api/project/new", json={"genre": "仙侠"})
        assert resp.status_code == 422


class TestProjectInfo:

    def test_info_no_project_open(self, client):
        """未打开项目时 info 返回 200 + ok=false 与错误描述。"""
        resp = client.get("/api/project/info")
        assert resp.status_code == 200
        body = assert_error(resp, status=200)
        assert body["error"] == "没有打开的项目"


class TestProjectList:

    def test_list_returns_paginated_array(self, client):
        """项目列表返回 200 + ok=true，data 为数组且带 pagination 元信息。"""
        resp = client.get("/api/project/list")
        assert resp.status_code == 200
        body = assert_ok(resp)
        assert isinstance(body["data"], list)
        assert "pagination" in body


class TestProjectSave:

    def test_save_no_project_returns_error(self, client):
        """未打开项目时保存返回 200 + ok=false（业务错误走响应信封，不改状态码）。"""
        resp = client.post("/api/project/save")
        assert resp.status_code == 200
        body = assert_error(resp, status=200)
        assert body["error"] == "没有打开的项目"
