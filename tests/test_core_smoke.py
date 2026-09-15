# -*- coding: utf-8 -*-
"""核心路由契约冒烟测试（遵循 API_CONTRACT.md）

覆盖此前无测试的核心路由族：ai 配置、settings、snapshot、export。
断言依据 API_CONTRACT.md：
  §1.1 统一信封 ok()/err()；§1.2 业务错误 = HTTP 200 + ok=false 信封；
  §2 错误码表（PROJECT_NOT_OPEN 等）。
"""
import gc
import os
import shutil

import pytest


def _release_project_handles():
    """释放项目 SQLite 句柄，避免 Windows 上目录清理被占用。"""
    from backend.services.project_service import state
    if state.project is not None:
        try:
            state.project._get_db().close()
        except Exception:
            pass
    gc.collect()


@pytest.fixture(autouse=True)
def clean_project_state():
    """每个测试前后重置全局项目状态（含派生句柄缓存），保证用例互相隔离。"""
    from backend.services.project_service import state
    state.project = None
    state.ledger = None
    state.world = None
    yield
    state.project = None
    state.ledger = None
    state.world = None


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


class TestAIConfigSmoke:
    """ai 配置路由冒烟：不调用外部模型，仅验证配置读取链路"""

    def test_get_config(self, client):
        resp = client.get("/api/ai/config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True

    def test_get_task_models(self, client):
        resp = client.get("/api/ai/task-models")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestSettingsSmoke:
    """settings 路由冒烟：依赖真相账本，无项目时返回 PROJECT_NOT_OPEN 信封"""

    def test_get_artifacts_no_project(self, client):
        resp = client.get("/api/settings/artifacts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "PROJECT_NOT_OPEN"

    def test_get_factions_no_project(self, client):
        resp = client.get("/api/settings/factions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "PROJECT_NOT_OPEN"


class TestNoProjectEnvelope:
    """无打开项目时，依赖项目状态的路由必须返回 PROJECT_NOT_OPEN 信封
    （契约 §1.2：业务错误 = 200 + err() 信封，而非 500）"""

    def test_export_txt_no_project(self, client):
        resp = client.get("/api/export/txt")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "PROJECT_NOT_OPEN"

    def test_snapshot_list_no_project(self, client):
        resp = client.get("/api/snapshot/list")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "PROJECT_NOT_OPEN"

    def test_snapshot_take_no_project(self, client):
        resp = client.post("/api/snapshot/take")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "PROJECT_NOT_OPEN"


class TestProjectScopedSmoke:
    """新建项目后的核心链路冒烟：快照列表与 txt 导出"""

    def test_snapshot_and_export_with_project(self, client, created_projects):
        # 新建项目（契约 §1.1 ok 信封）
        resp = client.post("/api/project/new", json={"title": "冒烟测试小说"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        created = body.get("project") or body.get("data") or {}
        if created.get("path"):
            created_projects.append(created["path"])

        # 快照列表：空项目应成功返回空列表
        resp = client.get("/api/snapshot/list")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert isinstance(body["data"], list)

        # txt 导出：返回纯文本响应
        resp = client.get("/api/export/txt")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")

        # settings：有项目时账本可读，返回 ok 信封 + 列表
        resp = client.get("/api/settings/artifacts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert isinstance(body["data"], list)
        resp = client.get("/api/settings/factions")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
