# API_CONTRACT.md — 书斋 V66 接口契约

本文档是 `tests/test_project_routes.py`、`tests/test_chapter_routes.py`、
`tests/test_api_models.py` 中路由/模型测试引用的契约锚点。

契约 owner（实际行为来源）：

- `backend/api_models.py` — 统一响应信封工厂 `ok()` / `err()` / `paginated()`、
  `PaginationParams`、错误码常量 `ErrorCode`
- `backend/routers/project.py` — `/api/project/*` 路由（§3.1）
- `backend/routers/chapter/`（`crud.py`、`planning_check.py` 等）—
  `/api/chapter/*`、`/api/check/*`、`/api/planning/*` 路由（§3.2）
- `server.py` — 单用户模式：无认证中间件，所有请求放行

> 契约变更必须同步修改本文档与对应测试；测试断言以本文档描述的精确行为为准。

---

## §1 统一响应信封与 HTTP 状态码语义

### 1.1 响应信封

| 工厂 | 形状 | 用途 |
| --- | --- | --- |
| `ok(data)` | `{"ok": true, "data": <T>}` | 统一成功响应 |
| `err(code, message, details?)` | `{"ok": false, "error": {"code": str, "message": str, "details"?: any}}` | 统一业务错误响应 |
| `paginated(items, page, page_size, total)` | `{"ok": true, "data": [...], "pagination": {"page", "page_size", "total_items", "total_pages"}}` | 分页列表响应 |

部分历史端点直接返回手写字典（如 `{"ok": true, "title": ..., "path": ...}`），
其共同点：顶层必有 `ok` 布尔字段。

### 1.2 HTTP 状态码语义（全项目统一）

| 状态码 | 含义 |
| --- | --- |
| **200** | 请求已被路由处理。**业务成功与业务错误都以 200 返回**，由 `ok` 字段区分；`err()` 信封不改变状态码 |
| **422** | 仅表示 FastAPI/Pydantic 请求体或查询参数校验失败（缺少必填字段、类型错误、越界等）。注意：空字符串对 `str` 字段是合法值，不会触发 422 |
| **404** | 路径不存在（未注册路由） |
| **500** | 路由内未捕获异常（契约之外的故障，测试不应预期） |

业务错误**不使用** 400 表达；因此测试中不允许出现
`status_code in (200, 400)` 之类的宽泛断言。

### 1.3 认证

单用户模式：`server.py` 不注册认证中间件与 `/api/auth/*` 端点，所有请求放行。
依赖认证的测试在无 `backend.auth` 模块时自动跳过。

---

## §2 错误码（`backend.api_models.ErrorCode`）

| 错误码 | 语义 |
| --- | --- |
| `PROJECT_NOT_OPEN` | 未打开项目时访问需要项目的端点 |
| `VALIDATION_ERROR` | 业务层参数校验失败 |
| `NOT_FOUND` | 资源不存在 |
| `CHAPTER_EMPTY` | 章节内容为空 |
| `INTERNAL_ERROR` | 内部处理失败（含章节索引越界、内容过短等） |
| `AUTH_FAILED` / `AUTH_CONFLICT` / `RATE_LIMITED` / `DUPLICATE` | 认证与限流（单用户模式下不产生） |
| `GENERATION_FAILED` / `AI_FAILED` / `IMPORT_FAILED` / `PARSE_FAILED` / `SYNC_FAILED` / `EXPORT_FAILED` | 各子系统操作失败 |
| `TASK_NOT_FOUND` | 异步任务不存在 |

---

## §3 端点契约

### §3.1 项目端点 — `/api/project/*`（owner: `backend/routers/project.py`）

| 端点 | 请求 | 成功（200） | 业务错误（200） | 422 场景 |
| --- | --- | --- | --- | --- |
| `GET /status` | 无 | `{"ok": true, "project": <标题或 null>, "version": "6.6"}` | 无 | 无 |
| `POST /new` | `ProjectCreate {title: str 必填, genre?: str, length?: int=10}` | `{"ok": true, "title", "path"}`；空标题合法（slug 回退 `untitled`） | 无（异常→500） | 缺少 `title` 或类型错误 |
| `POST /open` | `{path: str}` | `{"ok": true, "title", "chapters"}` | `{"ok": false, "error": "无法打开项目"}`（旧式字符串 error） | 缺少 `path` |
| `GET /info` | 无 | `{"ok": true, "title", "genre", "chapters", "current_chapter", "project_dir", "planned_chapters"}` | `{"ok": false, "error": "没有打开的项目"}`（旧式字符串 error） | 无 |
| `GET /list` | Query `page>=1, page_size 1..100` | `paginated(...)` | 无 | 分页参数越界（如 `page_size>100`） |
| `POST /save` | 无 | `{"ok": true}` | `{"ok": false, "error": "没有打开的项目"}`（旧式字符串 error） | 无 |
| `POST /delete` | `{project_dir: str}` | `{"ok": true}` | `{"ok": false, "error": "非法路径"/"项目不存在"/<异常信息>}`（旧式字符串 error） | 缺少 `project_dir` |

> 旧式字符串 `error` 为历史遗留形状；新端点与章节系端点一律使用 §1.1 的
> `err()` 信封（`error` 为对象，含 `code`/`message`）。

### §3.2 章节与检查端点（owner: `backend/routers/chapter/`）

`/api/chapter/*` 由 `chapter/crud.py`、`chapter/snapshots.py`、
`chapter/status.py` 提供；`/api/check/*`、`/api/planning/*` 由
`chapter/planning_check.py` 提供。所有业务错误使用 `err()` 信封。

| 端点 | 请求 | 成功（200） | 业务错误（200，err() 信封） | 422 场景 |
| --- | --- | --- | --- | --- |
| `GET /api/chapter/list` | Query `page, page_size` | `paginated(...) + {"current": <当前章>}` | `PROJECT_NOT_OPEN` | 分页参数越界 |
| `POST /api/chapter/add` | `ChapterAdd {title: str 必填, vol_index?: int}` | `{"ok": true, "index"}` | `PROJECT_NOT_OPEN` | 缺少 `title` |
| `POST /api/chapter/delete` | `{index: int}` | `{"ok": true}` | `PROJECT_NOT_OPEN` | 缺少/类型错误 `index` |
| `POST /api/chapter/rename` | `{index, title}` | `{"ok": true}` | `PROJECT_NOT_OPEN`；索引越界→`INTERNAL_ERROR` | 字段缺失 |
| `GET /api/chapter/load` | Query `index: int=0` | `{"ok": true, "title", "content", "word_count", "outline", "blueprint"}` | `PROJECT_NOT_OPEN` | `index` 类型错误 |
| `POST /api/chapter/save` | `ContentSave` | `{"ok": true, "saved", "word_count", "warnings"}` | `PROJECT_NOT_OPEN` / `INTERNAL_ERROR`（附 `warnings` 键） | 字段缺失 |
| `POST /api/check/completeness` | `{content: str 必填, title?, expected_length?}` | `{"ok": true, "result": {...}}` | `PROJECT_NOT_OPEN`；`content` 去空白后 <100 字→`INTERNAL_ERROR` | 缺少 `content` |
| `POST /api/check/continuity` | `{chapter_a: str, chapter_b: str, title_a?, title_b?}` | `{"ok": true, "result": {...}}` | `PROJECT_NOT_OPEN`；任一章 <100 字→`INTERNAL_ERROR` | 缺少必填字段 |
| `GET /api/planning/matrix` | 无 | `{"ok": true, ...矩阵数据}` | `PROJECT_NOT_OPEN` | 无 |
| `GET /api/planning/timeline` | 无 | `{"ok": true, ...时间线数据}` | `PROJECT_NOT_OPEN` | 无 |

---

## §4 契约测试锚点

| 测试文件 | 覆盖章节 |
| --- | --- |
| `tests/test_project_routes.py` | §1 信封/状态码语义、§3.1 全部端点（含 422 负例） |
| `tests/test_chapter_routes.py` | §1 信封/状态码语义、§3.2 list/load/add/check（含 `PROJECT_NOT_OPEN` 负例断言与 422 负例） |
| `tests/test_api_models.py` | §1 `err()` 信封形状、各路由请求模型字段/必填约束 |
| `tests/conftest.py` `assert_ok` / `assert_error` | §1 信封的统一断言工具（`assert_error` 支持按 `error.code` 校验） |

断言规范：

- 成功与业务错误场景断言**精确**状态码 `== 200`，并校验信封字段；
- 请求校验失败场景使用专门的负例断言 `== 422`；
- 禁止 `status_code in (200, 400, ...)` 一类宽泛断言。
