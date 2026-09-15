# CONTEXT.md — 书斋 V66 项目上下文

小说创作智能助手：FastAPI 后端 + Vanilla JS SPA 前端 + Capacitor APK（Chaquopy 内嵌后端副本）。
单用户桌面模式；`server.py` 不注册认证中间件，所有请求放行。

## 模块边界

| 目录 | 职责 |
| --- | --- |
| `backend/routers/` | HTTP 路由层（project / chapter / ai / generate / writing_assist 等），契约见 `API_CONTRACT.md` |
| `backend/services/` | 业务服务层（审计、校验、检测、导出、蒸馏等） |
| `backend/agents/` | Agent 调度层（dispatcher、router、intent_classifier、wizard_agent） |
| `backend/api_models.py` | 统一响应信封 `ok()/err()/paginated()` 与错误码 `ErrorCode` |
| `frontend/` | Vanilla JS SPA（`js/` 下 40 个源文件为真相，`js/bundle.js` 是构建产物） |
| `apk/android/app/src/main/python/` | **backend 的 Chaquopy 副本**，由 `sync_apk_backend.py` 单向同步 |
| `tests/` | pytest + FastAPI TestClient 契约测试 |

## 运行与验证路由

- **启动**：`start.bat`（自动定位真实 Python——优先本机安装的 Python 运行时，
  跳过 Microsoft Store 假壳；安装依赖并以 5 次重试启动 `server.py`）。
- **测试**：`python -m pytest tests -v --tb=short`（37 个契约测试；`backend.auth` 已从产品移除，
  相关测试经 `importorskip` 跳过）。pre-commit 钩子会自动跑 pytest + 前端 bundle 漂移检查。
- **综合检查**：`python auto_check_and_fix.py`（含 pytest 执行与常见问题自修复）。
- **前端构建**：`cd frontend && npm run build`（把 40 个源文件拼接为 `js/bundle.js`）；
  漂移检查：`node frontend/scripts/build-bundle.js --check`（退出码 1 = 漂移）。
- **数据备份**：`server.py` 启动时自动滚动备份（每天至多一份，保留 7 份）；
  手动：`python backend/services/backup_service.py --force`（快照在 `data/_backups/`）。
- **APK 同步**：改完 backend 后必须运行 `python sync_apk_backend.py`；
  发 APK 前用 `python sync_apk_backend.py --verify` 校验两侧一致（退出码 1 = 漂移）。
  `build.py` 与 `sync_to_phone.py` 已内置该闸门，漂移时自动中止。

## 领域词汇

| 术语 | 含义 |
| --- | --- |
| 项目（project） | 一部小说的工作单元，含章节、卷、大纲；全局状态 `project_service.state` 单例持有 |
| 章节（chapter） | 项目内的正文单元；路由 `/api/chapter/*`、`/api/check/*` |
| 审计（audit） | 对正文的一致性/逻辑/ POV 等检测服务族（`detect_*`、`extended_audit`） |
| 校验（validate） | 提示词与生成结果的结构校验（`validate_*` 路由与服务） |
| dispatcher | Agent 调度入口（`backend/agents/dispatcher.py`），聊天/工具调用分发 |
| 契约（contract） | `API_CONTRACT.md` 定义的响应信封与状态码语义，是路由测试的唯一断言依据 |

## 关键不变量（改动前必读）

1. **API 契约**：业务错误 = HTTP 200 + `err()` 信封；422 仅限 Pydantic 校验失败。
   契约变更必须同步 `API_CONTRACT.md` 与对应测试（见文档头部约定）。
2. **双副本纪律**：`backend/` 与 APK 内嵌副本必须经 `sync_apk_backend.py` 同步，
   禁止直接手改 `apk/android/app/src/main/python/` 下的文件。
3. **测试隔离**：路由测试依赖 `conftest.py` 的全局项目状态重置 fixture；
   新增测试不得绕过该 fixture 直接操作 `state.project`。
4. **前端构建纪律**：`frontend/js/bundle.js` 是构建产物，禁止手改；
   改任何 `frontend/js/` 源文件后必须 `npm run build` 重建（pre-commit 会拦截漂移）。
5. **ADR**：重大架构决策记录于 `docs/adr/`（按需懒创建，见 `docs/agents/domain.md`）。
