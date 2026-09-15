# -*- coding: utf-8 -*-
"""云同步路由 - /api/sync/*
使用 httpx 实现 WebDAV 客户端，连接复用、统一超时。
"""
from fastapi import APIRouter
from pydantic import BaseModel

import os, json, io, zipfile, tempfile, shutil, logging, base64
import httpx

from backend.services.project_service import state
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sync")

# 数据目录：<项目根>/data
_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)
SYNC_CONFIG_PATH = os.path.join(_DATA_DIR, "sync_config.json")

# 密码混淆密钥（单机自用级别的防偷窥，不是强加密）
_PASSWORD_SALT = "shuzhai_webdav_salt_2024"


def _obfuscate_password(pwd: str) -> str:
    """简单的密码混淆（base64 + 异或），防明文偷窥，不是强加密"""
    if not pwd:
        return ""
    try:
        salt_bytes = _PASSWORD_SALT.encode()
        pwd_bytes = pwd.encode()
        xored = bytes(b ^ salt_bytes[i % len(salt_bytes)] for i, b in enumerate(pwd_bytes))
        return "enc:" + base64.b64encode(xored).decode("ascii")
    except Exception:
        return pwd


def _deobfuscate_password(pwd: str) -> str:
    """解密混淆后的密码"""
    if not pwd or not pwd.startswith("enc:"):
        return pwd  # 老配置明文直接返回
    try:
        salt_bytes = _PASSWORD_SALT.encode()
        encoded = pwd[4:]
        xored = base64.b64decode(encoded)
        return bytes(b ^ salt_bytes[i % len(salt_bytes)] for i, b in enumerate(xored)).decode()
    except Exception:
        return pwd


class SyncConfig(BaseModel):
    webdav_url: str
    username: str
    password: str
    remote_path: str = "/"
    auto_sync: bool = False


# ── 内部工具 ──

def _load_config() -> dict:
    if os.path.exists(SYNC_CONFIG_PATH):
        try:
            with open(SYNC_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if cfg.get("password"):
                cfg["password"] = _deobfuscate_password(cfg["password"])
            return cfg
        except Exception:
            return {}
    return {}


def _save_config(cfg: dict):
    os.makedirs(os.path.dirname(SYNC_CONFIG_PATH), exist_ok=True)
    cfg = dict(cfg)
    if cfg.get("password"):
        cfg["password"] = _obfuscate_password(cfg["password"])
    with open(SYNC_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _make_client(cfg: SyncConfig, timeout: float = 15.0) -> httpx.Client:
    """创建带 Basic Auth 的 httpx Client"""
    return httpx.Client(
        auth=(cfg.username, cfg.password),
        timeout=httpx.Timeout(timeout, connect=10.0),
    )


def _join_url(base: str, path: str) -> str:
    """拼接 URL，处理多余斜杠"""
    base = base.rstrip("/")
    path = path.strip("/")
    return f"{base}/{path}" if path else base


def _safe_filename(name: str) -> str:
    """生成安全的远端文件名"""
    safe = "".join(c for c in name if c not in '\\/:*?"<>|').strip()
    return safe or "project"


# ═══════════════════════════════════════════
# 配置管理
# ═══════════════════════════════════════════

@router.get("/config")
def get_sync_config():
    """读取同步配置，不存在返回空配置"""
    cfg = _load_config()
    if not cfg:
        return {
            "ok": True,
            "config": {
                "webdav_url": "",
                "username": "",
                "password": "",
                "remote_path": "/",
                "auto_sync": False,
            },
        }
    return {"ok": True, "config": cfg}


@router.post("/config")
def save_sync_config(data: SyncConfig):
    """保存同步配置"""
    try:
        try:
            cfg = data.dict()
        except AttributeError:
            cfg = data.dict()
        _save_config(cfg)
        return {"ok": True}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")


# ═══════════════════════════════════════════
# 连接测试
# ═══════════════════════════════════════════

@router.post("/test")
def test_sync(data: SyncConfig):
    """用 PROPFIND 请求验证 WebDAV 连接"""
    try:
        url = _join_url(data.webdav_url, data.remote_path)
        body = (
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<propfind xmlns="DAV:"><prop><displayname/></prop></propfind>'
        )
        with _make_client(data, timeout=15.0) as client:
            resp = client.request(
                "PROPFIND",
                url,
                content=body,
                headers={"Depth": "0", "Content-Type": "application/xml; charset=utf-8"},
            )
        if resp.status_code in (200, 207):
            return {"ok": True, "message": f"连接成功（HTTP {resp.status_code}）"}
        return {"ok": False, "message": f"服务器返回状态码 {resp.status_code}"}
    except httpx.HTTPStatusError as e:
        return {"ok": False, "message": f"WebDAV 错误：HTTP {e.response.status_code}"}
    except httpx.RequestError as e:
        return {"ok": False, "message": f"连接失败：{e}"}
    except Exception as e:
        return {"ok": False, "message": f"测试失败：{e}"}


# ═══════════════════════════════════════════
# 推送 / 拉取
# ═══════════════════════════════════════════

@router.post("/push")
def sync_push(data: SyncConfig):
    """打包当前项目目录并 PUT 到 WebDAV 远端"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "未打开项目")
    try:
        project_dir = state.project.project_dir
        project_name = state.project.meta.get("title", "project")
        remote_file = f"{_safe_filename(project_name)}.zip"

        # 打包项目目录到内存
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(project_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    arcname = os.path.relpath(fpath, project_dir)
                    zf.write(fpath, arcname)
        zip_bytes = buf.getvalue()

        # PUT 到 WebDAV
        url = _join_url(_join_url(data.webdav_url, data.remote_path), remote_file)
        with _make_client(data, timeout=120.0) as client:
            resp = client.put(
                url,
                content=zip_bytes,
                headers={"Content-Type": "application/zip"},
            )
        if resp.status_code in (200, 201, 204):
            return {
                "ok": True,
                "message": f"上传成功（{len(zip_bytes)} 字节）",
                "size": len(zip_bytes),
            }
        return {"ok": False, "message": f"上传失败，状态码 {resp.status_code}"}
    except httpx.HTTPStatusError as e:
        return {"ok": False, "message": f"WebDAV 错误：HTTP {e.response.status_code}"}
    except httpx.RequestError as e:
        return {"ok": False, "message": f"上传失败：{e}"}
    except Exception as e:
        logger.exception("sync push failed")
        return {"ok": False, "message": f"上传失败：{e}"}


@router.post("/pull")
def sync_pull(data: SyncConfig):
    """从 WebDAV 下载远端 zip 并解压覆盖当前项目目录"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "未打开项目")
    try:
        project_dir = state.project.project_dir
        project_name = state.project.meta.get("title", "project")
        remote_file = f"{_safe_filename(project_name)}.zip"

        # GET 下载远端 zip
        url = _join_url(_join_url(data.webdav_url, data.remote_path), remote_file)
        with _make_client(data, timeout=120.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            zip_bytes = resp.content

        # 解压到临时目录，再覆盖项目目录
        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                zf.extractall(tmpdir)
            for root, dirs, files in os.walk(tmpdir):
                rel = os.path.relpath(root, tmpdir)
                dest = project_dir if rel == "." else os.path.join(project_dir, rel)
                os.makedirs(dest, exist_ok=True)
                for fname in files:
                    src = os.path.join(root, fname)
                    dst = os.path.join(dest, fname)
                    shutil.copy2(src, dst)

        return {
            "ok": True,
            "message": f"拉取成功（{len(zip_bytes)} 字节），已覆盖项目目录",
            "size": len(zip_bytes),
        }
    except httpx.HTTPStatusError as e:
        return {"ok": False, "message": f"WebDAV 错误：HTTP {e.response.status_code}"}
    except httpx.RequestError as e:
        return {"ok": False, "message": f"下载失败：{e}"}
    except Exception as e:
        logger.exception("sync pull failed")
        return {"ok": False, "message": f"拉取失败：{e}"}
