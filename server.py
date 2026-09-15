# -*- coding: utf-8 -*-
"""书斋 - FastAPI 服务 (安全加固版)"""
import sys, os, logging

# 强制无缓冲输出，确保日志立即显示
os.environ.setdefault("PYTHONUNBUFFERED", "1")

# 在任何其他导入之前设置离线模式，防止 HF Hub 发起网络 HEAD 请求
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# 全局日志配置 - 统一日志体系（控制台 + 文件双输出，按天轮转保留7天）
from backend.logger_config import setup_logging
setup_logging(app_name="shuzhai", log_dir=None)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.routers import project, chapter, ai_router, file_router, validate, workflow, generate, memory, knowledge_base, deconstruct, storyboard, sync, export, chat, reader_router, distill, world, writing_assist, analytics, ranking, settings, snapshot, timeline, flow
from backend.routers import engine as engine_router
from backend.agents import router as agent
from backend.routers import import_router
from backend.routers import skill_import
from backend.services.project_service import FRONTEND_DIR, ensure_initialized

logger = logging.getLogger(__name__)

app = FastAPI(title="书斋", version="1.0", docs_url=None, redoc_url=None, openapi_url=None)

# ═══════════════════════════════════════════
# CORS 配置 - 仅允许本地和局域网来源，防止跨站请求伪造
# ═══════════════════════════════════════════
def _get_allowed_origins():
    """动态生成允许的来源列表（本地 + 局域网常见网段）"""
    origins = [
        "https://localhost",  # Capacitor WebView (APK)
        "http://localhost",    # Capacitor WebView (HTTP)
        "http://127.0.0.1:8893",
        "http://localhost:8893",
        "http://127.0.0.1:8888",
        "http://localhost:8888",
    ]
    # 端口范围 8893-8914（覆盖 _find_port 自动探测范围 8894-8913）
    for p in range(8893, 8915):
        origins.append(f"http://127.0.0.1:{p}")
        origins.append(f"http://localhost:{p}")
    return origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",  # 允许所有localhost变体
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "X-Internal-Key", "Accept", "Origin"],
)

# ═══════════════════════════════════════════
# 单用户模式 — 无认证，全部放行
# ═══════════════════════════════════════════

# ═══════════════════════════════════════════
# Register Routers
# ═══════════════════════════════════════════
app.include_router(project.router)
app.include_router(chapter.router)
app.include_router(chapter.planning_router)
app.include_router(ai_router.router)
app.include_router(file_router.router)
app.include_router(validate.router)
app.include_router(workflow.router)
app.include_router(generate.router)
app.include_router(memory.router)
app.include_router(knowledge_base.router)
app.include_router(deconstruct.router)
app.include_router(storyboard.router)
app.include_router(sync.router)
app.include_router(export.router)
app.include_router(chat.router)
app.include_router(agent)
app.include_router(reader_router.router)
app.include_router(import_router.router)
app.include_router(skill_import.router)
app.include_router(chapter.check_router)
app.include_router(world.world_router)
app.include_router(world.ledger_router)
app.include_router(writing_assist.preference_router)
app.include_router(writing_assist.templates_router)
app.include_router(writing_assist.creative_router)
app.include_router(analytics.audit_log_router)
app.include_router(analytics.stats_router)
app.include_router(distill.router)
app.include_router(ranking.router)
app.include_router(engine_router.router)
app.include_router(settings.router)
app.include_router(snapshot.router)
app.include_router(timeline.router)
app.include_router(flow.router)

# ═══════════════════════════════════════════
# Prompt注入防护 — 热重载端点
# ═══════════════════════════════════════════
from backend.prompt_sanitizer import reload_config as _reload_sanitizer

@app.post("/api/sanitizer/reload")
async def _sanitizer_reload():
    """热重载 sanitizer_config.json 配置"""
    try:
        _reload_sanitizer()
        return {"ok": True, "message": "Prompt注入防护配置已重载"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ═══════════════════════════════════════════
# 全局异常处理器 — 记录完整堆栈，返回统一错误信封
# ═══════════════════════════════════════════
import traceback as _traceback
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """兜底捕获所有未处理异常，记录完整堆栈后返回 INTERNAL_ERROR"""
    _logger = logging.getLogger("server")
    _logger.error(
        "[%s %s] 未处理异常:\n%s",
        request.method, request.url.path,
        _traceback.format_exc().strip(),
    )
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": {"code": "INTERNAL_ERROR", "message": "服务器内部错误"}},
    )

# ═══════════════════════════════════════════
# Static Files + Frontend (SPA 模式)
# ═══════════════════════════════════════════
import os as _os
if _os.path.isdir(str(FRONTEND_DIR)):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    # APK模式：前端由Capacitor WebView从assets加载，后端只提供API
    @app.get("/")
    async def _root():
        return {"status": "ok", "message": "ShuZhai API"}

# ═══════════════════════════════════════════
# Entry
# ═══════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    # 延迟初始化项目（避免 import 时副作用）
    ensure_initialized()
    # 启动前滚动备份书稿数据（每天至多一份，失败不阻塞启动）
    try:
        from backend.services.backup_service import run_backup
        _bk = run_backup()
        if _bk['created']:
            print(f"  [OK] 数据已备份: data/_backups/{_bk['created']}（{_bk['size_mb']} MB）")
        elif _bk['skipped']:
            print(f"  [备份] {_bk['skipped']}")
    except Exception as _e:
        print(f"  [备份] 跳过: {_e}")
    import socket
    import threading
    import webbrowser
    # 获取局域网IP，方便手机访问
    def _get_lan_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return None
    lan_ip = _get_lan_ip()
    # 端口冲突自动重试
    import socket as _sock
    def _find_port(start=8888):
        for p in range(start, start + 20):
            try:
                s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
                s.bind(("0.0.0.0", p))
                s.close()
                return p
            except OSError:
                continue
        return start

    PORT = _find_port(8894)
    if PORT != 8894:
        print(f"  [!] 端口8894被占用，改用 {PORT}")
    import os
    os.environ["SHUZHAI_PORT"] = str(PORT)

    # 安全默认：仅监听本机；显式 --lan（或 SHUZHAI_LAN=1）才暴露到局域网
    LAN_MODE = ("--lan" in sys.argv) or (os.environ.get("SHUZHAI_LAN") == "1")
    HOST = "0.0.0.0" if LAN_MODE else "127.0.0.1"

    lan_ip = _get_lan_ip() if LAN_MODE else None
    print("\n" + "=" * 50)
    print("  ShuZhai - Novel Creator")
    print(f"  本机访问:  http://127.0.0.1:{PORT}")
    if LAN_MODE and lan_ip:
        print(f"  手机访问:  http://{lan_ip}:{PORT}")
        print(f"  (手机需与电脑同一局域网，防火墙放行{PORT}端口)")
        print("  [!] 局域网模式无认证，同网段设备可访问全部数据")
    elif not LAN_MODE:
        print("  (仅本机可访问；需手机访问请加 --lan 参数启动)")
    print("=" * 50 + "\n")

    # 延迟2秒后自动打开浏览器（等服务器启动完成）
    def _auto_open_browser():
        import time
        time.sleep(2)
        webbrowser.open(f"http://127.0.0.1:{PORT}")
        print(f"  [OK] 已自动打开浏览器（如未弹出请手动访问 http://127.0.0.1:{PORT}）")
    threading.Thread(target=_auto_open_browser, daemon=True).start()

    # 0.0.0.0 允许局域网设备访问
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
