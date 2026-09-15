# 书斋 V66 — 小说创作智能助手

FastAPI 后端 + Vanilla JS SPA 前端 + Capacitor APK（Chaquopy 内嵌后端副本）的单机小说创作工具。
单用户桌面模式，数据全部存于本地 `data/` 目录。

## 快速开始（本机已有环境）

```bat
start.bat
```

自动定位真实 Python 解释器（跳过 Microsoft Store 假壳）、按需安装依赖、以 5 次重试启动服务，
并打开浏览器。默认带 `--lan` 参数（同局域网手机可访问）。

## 从零部署（新机器）

本机环境依赖 `H:\Marvis\MarvisAgent\*\runtime\python311\python.exe`（start.bat 自动探测）。
若新机器没有该运行时，按以下步骤自建环境：

1. 安装 **Python 3.11**（加入 PATH；注意 Microsoft Store 版是重定向假壳，请用官网安装包）
2. 克隆仓库后安装依赖：
   ```bat
   python -m pip install -r requirements.txt
   ```
   （移动端/轻量部署用 `requirements-mobile.txt`，不含 torch/transformers，向量记忆自动降级）
3. 启动：
   ```bat
   python server.py            :: 仅本机访问（默认，安全）
   python server.py --lan      :: 允许同局域网手机访问（无认证，仅限可信网络）
   ```
4. 浏览器访问 `http://127.0.0.1:8894`（端口被占时自动顺延探测）。

## 常用命令

| 用途 | 命令 |
| --- | --- |
| 契约测试 | `python -m pytest tests -v --tb=short` |
| 综合自检 | `python auto_check_and_fix.py` |
| 前端重建 bundle | `cd frontend && npm run build` |
| bundle 漂移检查 | `node frontend/scripts/build-bundle.js --check` |
| APK 副本同步 | `python sync_apk_backend.py` |
| APK 副本一致性校验 | `python sync_apk_backend.py --verify` |
| 手动数据备份 | `python backend/services/backup_service.py --force` |
| 桌面端打包 | `python build.py`（PyInstaller，打包前自动跑双副本校验闸门） |

## 数据安全

- **自动备份**：`server.py` 启动时滚动备份书稿数据到 `data/_backups/`（每天至多一份，保留 7 份；
  SQLite 走 backup API 保证一致性）。
- **章节快照**：应用内 `/api/snapshot` 支持叙事状态快照与恢复。
- **数据库**：SQLite WAL 模式 + busy_timeout + 外键约束（`backend/db.py`）。
- `data/` 不入版本控制——它是你的书稿，请确保 `data/_backups/` 定期拷贝到外部存储。

## 项目结构

```
server.py                  FastAPI 入口（CORS 白名单、路由注册、启动备份）
backend/routers/           HTTP 路由层（契约见 API_CONTRACT.md）
backend/services/          业务服务层（审计、校验、检测、导出、备份等）
backend/agents/            Agent 调度层（dispatcher、router、wizard_agent）
frontend/js/               40 个前端源文件（真相）；js/bundle.js 为构建产物
apk/android/.../python/    backend 的 Chaquopy 副本（sync_apk_backend.py 单向同步）
tests/                     pytest + TestClient 契约测试
docs/plans/                架构规划与分析报告
```

## 必读文档

- [CONTEXT.md](CONTEXT.md) — 模块边界、运行路由、领域词汇、**五条关键不变量**
- [API_CONTRACT.md](API_CONTRACT.md) — 响应信封与状态码语义（路由测试的唯一断言依据）
- `docs/agents/` — issue 跟踪、分诊标签、领域约定

## 提交护栏

`.git/hooks/pre-commit`（仓库内可重装副本 `scripts/pre-commit`）在每次提交前自动执行：

1. `pytest tests -x -q` — 契约测试
2. `ruff check --select E9,F63,F7,F401,F811,F821` — 致命语法错误 + 未定义名/重复定义/未用导入（ruff 可用时）
3. `build-bundle.js --check` — 前端 bundle 与源文件一致性（node 可用时）

重装钩子：`cp scripts/pre-commit .git/hooks/pre-commit`
