---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 62a5f052892935463ed1c42751e16e2e_471e9abc94fe11f181ac525400f8a581
    ReservedCode1: ARMvn6Pv/PxXP0O/gORG4EHem07tZA4JGFwYznTvWBNYmsYUAyHzNsAEoZVuk8QFC/sg3p4whB2ZLmiFD3VBzZc4CYp7xutHIMvYdpakdJTn3UApM87dggVcHf43MX7qs9x3jOzWJYl8CHHh61WZODYoTvRbFwvQGKKGRxYR/p2/1alXA5aV+9ON5Fw=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 62a5f052892935463ed1c42751e16e2e_471e9abc94fe11f181ac525400f8a581
    ReservedCode2: ARMvn6Pv/PxXP0O/gORG4EHem07tZA4JGFwYznTvWBNYmsYUAyHzNsAEoZVuk8QFC/sg3p4whB2ZLmiFD3VBzZc4CYp7xutHIMvYdpakdJTn3UApM87dggVcHf43MX7qs9x3jOzWJYl8CHHh61WZODYoTvRbFwvQGKKGRxYR/p2/1alXA5aV+9ON5Fw=
---

# 书斋 V66 API 参考文档

> 版本: 1.0 | 更新时间: 2026-08-11 | 协议: REST/JSON

## 概述

书斋 API 基于 FastAPI 构建，提供 256 个 RESTful 接口。所有接口均返回 JSON 格式。

### 通用约定

**基础 URL**: `http://127.0.0.1:{PORT}/`

**统一响应格式**:
- 成功: `{"ok": true, "data": ...}` 或 `{"ok": true, ...具体字段}`
- 错误: `{"ok": false, "error": {"code": "ERROR_CODE", "message": "描述"}}`
- 分页: `{"ok": true, "data": [...], "pagination": {"page": 1, "page_size": 20, "total_items": 100, "total_pages": 5}}`

**通用错误码**:

| 错误码 | 说明 |
| --- | --- |
| `PROJECT_NOT_OPEN` | 没有打开的项目 |
| `NOT_FOUND` | 资源不存在 |
| `VALIDATION_ERROR` | 请求参数校验失败 |
| `AI_FAILED` | AI 调用失败 |
| `GENERATION_FAILED` | 生成失败 |
| `TASK_NOT_FOUND` | 异步任务未找到 |
| `SYNC_FAILED` | 同步失败 |
| `EXPORT_FAILED` | 导出失败 |
| `IMPORT_FAILED` | 导入失败 |
| `PARSE_FAILED` | 文件解析失败 |
| `INTERNAL_ERROR` | 服务器内部错误 |

---

## 完整端点列表


### 项目管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/project/status` | 获取当前项目状态（标题、版本） |
| `POST` | `/api/project/new` | 创建新小说项目 |
| `POST` | `/api/project/open` | 打开已有项目 |
| `GET` | `/api/project/info` | 获取当前项目详细信息 |
| `GET` | `/api/project/list` | 列出所有项目（支持分页） |
| `POST` | `/api/project/delete` | 删除小说项目（整个文件夹） |
| `POST` | `/api/project/save` | 保存当前项目 |

### 大纲与设置

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/project/outline` | 获取大纲 |
| `POST` | `/api/project/outline` | 保存大纲 |
| `GET` | `/api/project/settings` | 获取项目设置 |
| `POST` | `/api/project/settings` | 保存项目设置 |
| `GET` | `/api/project/novel-outline` | 获取结构化全书大纲 |
| `POST` | `/api/project/novel-outline` | 保存结构化全书大纲 |
| `PUT` | `/api/project/novel-outline` | PUT 方式保存大纲 |

### 卷管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/project/volumes` | 获取卷列表 |
| `POST` | `/api/project/volumes` | 保存卷列表 |
| `POST` | `/api/project/volume/add` | 添加一卷 |
| `POST` | `/api/project/volume/delete` | 删除一卷 |
| `POST` | `/api/project/volume/rename` | 重命名一卷 |
| `PUT` | `/api/project/volume/{vol_index}/outline` | 更新卷纲要 |
| `POST` | `/api/project/volume/{vol_index}/outline` | 更新卷纲要（POST兼容） |
| `GET` | `/api/project/volume/{vol_index}/outline` | 获取卷纲要 |
| `POST` | `/api/project/auto-volumes` | 自动解析卷结构 |
| `POST` | `/api/project/ai-split-volumes` | AI 智能分卷 |
| `POST` | `/api/project/volume/{vol_index}/add-chapter` | 添加章节到卷 |
| `POST` | `/api/project/volume/{vol_index}/remove-chapter` | 从卷移除章节 |
| `POST` | `/api/project/volume/{vol_index}/set-chapters` | 设置卷章节列表 |

### 章节管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/chapter/list` | 列出所有章节 |
| `POST` | `/api/chapter/add` | 新建章节 |
| `POST` | `/api/chapter/delete` | 删除章节 |
| `POST` | `/api/chapter/rename` | 重命名章节 |
| `GET` | `/api/chapter/load` | 加载章节内容 |
| `POST` | `/api/chapter/save` | 保存章节内容 |
| `POST` | `/api/chapter/{index}/blueprint` | 保存章节蓝图 |
| `POST` | `/api/chapter/outline` | 保存章节大纲 |
| `POST` | `/api/chapter/reorder` | 重排章节顺序 |
| `POST` | `/api/chapter/{index}/status` | 更新章节状态（draft/revised/final） |
| `POST` | `/api/chapter/{index}/pov` | 设置章节 POV 角色 |
| `POST` | `/api/chapter/{index}/scene-labels` | 更新章节场景标签 |

### 快照

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/chapter/snapshots` | 获取快照列表 |
| `POST` | `/api/chapter/snapshot/restore` | 从快照恢复 |
| `POST` | `/api/chapter/snapshot/diff` | 比较两快照差异 |

### 规划与时间线

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/planning/matrix` | 获取矩阵视图（卷×章节×字数×状态） |
| `GET` | `/api/planning/timeline` | 获取时间线视图（角色出场×伏笔×章节） |
| `POST` | `/api/check/completeness` | 检查单章完整性 |
| `POST` | `/api/check/continuity` | 检查章节间连贯性 |

### 世界构建

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/world/` | 获取世界观完整数据 |
| `POST` | `/api/world/force/add` | 添加势力 |
| `GET` | `/api/world/force/{idx}` | 获取势力详情 |
| `PATCH` | `/api/world/force/{idx}` | 更新势力 |
| `DELETE` | `/api/world/force/{idx}` | 删除势力 |
| `POST` | `/api/world/item/add` | 添加物品 |
| `GET` | `/api/world/item/{idx}` | 获取物品详情 |
| `PATCH` | `/api/world/item/{idx}` | 更新物品 |
| `DELETE` | `/api/world/item/{idx}` | 删除物品 |
| `POST` | `/api/world/location/add` | 添加地点 |
| `GET` | `/api/world/location/{idx}` | 获取地点详情 |
| `PATCH` | `/api/world/location/{idx}` | 更新地点 |
| `DELETE` | `/api/world/location/{idx}` | 删除地点 |
| `POST` | `/api/world/constraint/add` | 添加世界规则约束 |
| `GET` | `/api/world/stats` | 世界观统计 |

### 事实账本

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/ledger/stats` | 账本统计 |
| `GET` | `/api/ledger/characters` | 获取所有角色状态 |
| `POST` | `/api/ledger/character/update` | 更新角色状态 |
| `GET` | `/api/ledger/timeline` | 获取时间线事件 |
| `GET` | `/api/ledger/hooks` | 获取伏笔列表 |
| `POST` | `/api/ledger/hook/add` | 添加伏笔 |
| `POST` | `/api/ledger/hook/recover` | 回收伏笔 |
| `POST` | `/api/ledger/hook/activate` | 激活伏笔 |
| `POST` | `/api/ledger/hook/abandon` | 废弃伏笔 |
| `GET` | `/api/ledger/read-pull` | 追读力评分 |
| `GET` | `/api/ledger/strand-stats` | 三线节奏分布 |

### 记忆系统

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/memory/stats` | 记忆统计 |
| `POST` | `/api/memory/add` | 添加记忆 |
| `POST` | `/api/memory/search` | 搜索记忆 |
| `POST` | `/api/memory/search-combined` | 合并搜索（项目+共享） |
| `POST` | `/api/memory/search-for-generation` | 为章节生成召回上下文 |
| `POST` | `/api/memory/context-preview` | 预览注入的记忆源 |
| `POST` | `/api/memory/import-chapter` | 导入章节到向量记忆 |
| `POST` | `/api/memory/share` | 提升为跨项目共享记忆 |
| `POST` | `/api/memory/shared/add` | 添加共享记忆 |
| `GET` | `/api/memory/shared/list` | 列出共享记忆 |
| `GET` | `/api/memory/shared/stats` | 共享记忆统计 |
| `DELETE` | `/api/memory/shared/{memory_id}` | 删除共享记忆 |
| `DELETE` | `/api/memory/{memory_id}` | 删除记忆 |
| `GET` | `/api/memory/embedding-models` | 列出可用嵌入模型 |
| `POST` | `/api/memory/switch-embedding-model` | 切换嵌入模型 |

### 知识库

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/kb/list` | 列出所有知识库设定集 |
| `GET` | `/api/kb/search` | 搜索知识库 |
| `GET` | `/api/kb/templates` | 获取预设模板列表 |
| `POST` | `/api/kb/import-template` | 导入预设设定集 |
| `POST` | `/api/kb/import-custom` | 导入自定义设定集 |
| `POST` | `/api/kb/import-pack` | 导入设定包 |
| `POST` | `/api/kb/export-pack` | 导出共享知识库为设定包 |
| `DELETE` | `/api/kb/pack/{pack_name}` | 删除知识库设定集 |

### 写作辅助

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/creative/describe` | AI 增强描写 |
| `POST` | `/api/creative/expand` | AI 场景扩写 |
| `POST` | `/api/creative/feedback` | AI 5维反馈 |
| `POST` | `/api/creative/rewrite` | AI 灵活重写（3候选版） |
| `GET` | `/api/preference/` | 获取全部偏好记忆 |
| `GET` | `/api/preference/guide` | 生成偏好指南文本 |
| `POST` | `/api/preference/pattern` | 记录喜欢/不喜欢的模式 |
| `POST` | `/api/preference/taboo` | 添加/移除禁忌词 |
| `POST` | `/api/preference/update` | 更新偏好项 |

### 头脑风暴与大纲

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/project/brainstorm-cards` | 保存头脑风暴卡片 |
| `GET` | `/api/project/planning-cards` | 获取连线框画布数据 |
| `POST` | `/api/project/planning-cards` | 保存连线框画布数据 |
| `GET` | `/api/project/workflow-step-status` | 9步工作流状态检查 |
| `POST` | `/api/project/planning-check` | 连线框对照校验 |

### AI 代理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/ai/chat` | AI 对话 |
| `POST` | `/api/ai/chat/stream` | SSE 流式聊天 |
| `POST` | `/api/ai/analyze-content` | 分析提取设定 |
| `POST` | `/api/ai/extract-settings` | 提取设定 |
| `POST` | `/api/ai/generate-characters` | AI 生成人物档案 |
| `POST` | `/api/ai/brainstorm` | AI 头脑风暴 |
| `POST` | `/api/ai/expand-idea` | 灵感碎片扩展 |
| `POST` | `/api/ai/sensory` | 五感描写生成 |
| `POST` | `/api/ai/proxy` | AI 安全代理 |
| `GET` | `/api/ai/usage` | 获取 AI 用量统计 |
| `POST` | `/api/ai/usage/reset` | 清空用量记录 |
| `GET` | `/api/ai/config` | 获取 AI 配置 |
| `POST` | `/api/ai/config` | 更新 AI 配置 |
| `GET` | `/api/ai/api-key` | 安全获取 API Key |
| `GET` | `/api/ai/task-models` | 获取任务型模型映射 |
| `GET` | `/api/ai/test` | 测试 AI 连接 |
| `POST` | `/api/ai/test` | 测试 AI 连接 |

### AI Agent 对话中枢

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/agent/chat` | 自然语言→意图识别→API调度→结果返回 |

### 生成任务

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/generate/start` | 异步提交生成任务 |
| `GET` | `/api/generate/status/{task_id}` | 查询生成任务进度 |
| `POST` | `/api/generate/cancel/{task_id}` | 取消生成任务 |

### 蒸馏

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/distill/chapters` | 蒸馏指定章节 |
| `GET` | `/api/distill/memory` | 读取全部蒸馏记忆 |
| `GET` | `/api/distill/status` | 获取蒸馏状态 |
| `POST` | `/api/distill/start` | 启动后台蒸馏任务 |
| `GET` | `/api/distill/status/{task_id}` | 查询蒸馏任务进度 |
| `POST` | `/api/distill/cancel/{task_id}` | 取消蒸馏任务 |

### 拆书

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/deconstruct/analyze` | 拆书分析 |
| `POST` | `/api/deconstruct/start` | 异步提交拆书任务 |
| `GET` | `/api/deconstruct/status/{task_id}` | 查询拆书任务进度 |
| `POST` | `/api/deconstruct/cancel/{task_id}` | 取消拆书任务 |
| `GET` | `/api/deconstruct/dimensions` | 获取拆书维度列表 |
| `POST` | `/api/deconstruct/dimension` | 单独分析某一维度 |
| `POST` | `/api/deconstruct/chunk/meta` | 增量拆书-提取元信息 |
| `POST` | `/api/deconstruct/chunk/summarize` | 增量拆书-文本块摘要 |
| `POST` | `/api/deconstruct/chunk/merge` | 增量拆书-合并梗概 |
| `POST` | `/api/deconstruct/chunk/analyze` | 增量拆书-维度分析 |
| `POST` | `/api/deconstruct/transform` | 转化拆书结果 |

### 分镜

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/storyboard/generate` | 生成视频分镜脚本 |
| `POST` | `/api/storyboard/batch` | 批量生成分镜 |
| `POST` | `/api/storyboard/start` | 异步提交分镜任务 |
| `GET` | `/api/storyboard/status/{task_id}` | 查询分镜任务进度 |
| `POST` | `/api/storyboard/cancel/{task_id}` | 取消分镜任务 |
| `GET` | `/api/storyboard/history` | 获取历史分镜列表 |
| `GET` | `/api/storyboard/history/{history_id}` | 加载指定历史分镜 |
| `DELETE` | `/api/storyboard/history/{history_id}` | 删除指定历史分镜 |
| `GET` | `/api/storyboard/templates` | 列出分镜模板 |
| `POST` | `/api/storyboard/templates` | 新增/更新模板 |
| `DELETE` | `/api/storyboard/templates/{template_id}` | 删除模板 |

### 导出

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/export/txt` | 导出为 TXT |
| `GET` | `/api/export/epub` | 导出为 EPUB |
| `GET` | `/api/export/epub/{project_path:path}` | 通过项目路径导出 EPUB |
| `GET` | `/api/export/pdf` | 导出为 PDF |
| `POST` | `/api/export/platform` | 平台模板导出 |
| `POST` | `/api/export/script` | 短剧脚本导出 |

### 导入

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/import/novel` | 逆向导入已有小说 |
| `POST` | `/api/import/extract-characters` | 提取候选角色名 |

### 技能包

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/skills/import` | 导入技能包 |
| `GET` | `/api/skills/list` | 列出技能包 |
| `DELETE` | `/api/skills/{skill_id}` | 删除技能包 |
| `POST` | `/api/skills/distill` | 蒸馏写作技能包 |
| `POST` | `/api/skills/deep-analyze` | 一键深度分析 |

### 云同步

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/sync/config` | 读取同步配置 |
| `POST` | `/api/sync/config` | 保存同步配置 |
| `POST` | `/api/sync/push` | 同步上传 |
| `POST` | `/api/sync/pull` | 同步下载 |
| `POST` | `/api/sync/test` | 测试 WebDAV 连接 |

### 阅读模式

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/reader/bookshelf` | 获取书架 |
| `POST` | `/api/reader/bookshelf/toggle` | 添加/移除书架 |
| `GET` | `/api/reader/chapter` | 加载章节（阅读模式） |
| `GET` | `/api/reader/progress` | 获取阅读进度 |
| `POST` | `/api/reader/progress` | 保存阅读进度 |

### 角色对话

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/chat/characters` | 获取可用角色列表 |
| `POST` | `/api/chat/talk` | 以指定角色身份回复 |

### 引擎 V2

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/engine/status` | 获取引擎状态 |
| `POST` | `/api/engine/reset` | 重置引擎状态 |
| `GET` | `/api/engine/graph` | 获取六轴关系图 |
| `POST` | `/api/engine/graph/add-edge` | 手动添加关系边 |
| `POST` | `/api/engine/collide` | 碰撞检测生成灵感 |
| `GET` | `/api/engine/v2/status` | 获取完整引擎状态（V2） |
| `GET` | `/api/engine/v2/goals` | 获取目标列表 |
| `POST` | `/api/engine/v2/goals/add` | 添加目标 |
| `POST` | `/api/engine/v2/goals/complete` | 完成目标 |
| `GET` | `/api/engine/v2/rules` | 获取世界观规则列表 |
| `POST` | `/api/engine/v2/rules/check` | 校验文本是否违反规则 |
| `GET` | `/api/engine/v2/consistency` | 全局一致性校验 |
| `GET` | `/api/engine/v2/branches` | 获取分支树 |
| `POST` | `/api/engine/v2/branches/create` | 创建新分支 |
| `POST` | `/api/engine/v2/branches/switch` | 切换分支 |
| `GET` | `/api/engine/v2/timeline` | 获取世界时间轴 |
| `POST` | `/api/engine/v2/tick/advance` | 推进一个 tick |
| `GET` | `/api/engine/v2/swimlanes` | 获取角色泳道列表 |

### 时间线叙事

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/timeline` | 获取完整时间线树 |
| `GET` | `/api/timeline/{volume_index}/{chapter_index}` | 获取章节时间线对照 |
| `PUT` | `/api/timeline/{volume_index}/{chapter_index}/planned` | 更新计划列 |
| `PUT` | `/api/timeline/{volume_index}/{chapter_index}/actual` | 更新实际列 |
| `PUT` | `/api/timeline/{volume_index}/{chapter_index}/annotation` | 更新手工注释 |
| `POST` | `/api/timeline/{volume_index}/{chapter_index}/compare` | AI 对照（计划 vs 实际） |
| `POST` | `/api/timeline/{volume_index}/{chapter_index}/compare-all` | AI 全量对照 |
| `POST` | `/api/timeline/{volume_index}/{chapter_index}/divergence` | 新增分歧 |
| `PUT` | `/api/timeline/{volume_index}/{chapter_index}/divergence` | 更新分歧内容 |
| `PUT` | `/api/timeline/{volume_index}/{chapter_index}/divergence-status` | 更新分歧状态 |
| `DELETE` | `/api/timeline/{volume_index}/{chapter_index}/divergence/{divergence_index}` | 删除分歧 |
| `POST` | `/api/timeline/{volume_index}/{chapter_index}/fix-divergence` | AI 修复单个偏离 |
| `POST` | `/api/timeline/{volume_index}/{chapter_index}/fix-all-divergences` | AI 修复全部偏离 |
| `POST` | `/api/timeline/{volume_index}/{chapter_index}/finalize` | 定稿章节 |

### 排行与趋势

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/ranking/scan` | 扫榜爬取平台数据 |
| `GET` | `/api/ranking/platforms` | 获取支持的平台配置 |
| `GET` | `/api/ranking/compare` | 多平台榜单对比 |
| `GET` | `/api/ranking/genre-analysis` | 分析题材市场表现 |
| `GET` | `/api/ranking/trends` | 获取趋势变化 |
| `GET` | `/api/ranking/suggestions` | 获取创作建议 |

### 统计

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/stats/daily` | 每日字数 |
| `GET` | `/api/stats/weekly` | 每周字数 |
| `GET` | `/api/stats/monthly` | 每月字数 |
| `GET` | `/api/stats/summary` | 写作汇总 |

### 快照系统

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/snapshot/list` | 列出所有快照 |
| `POST` | `/api/snapshot/take` | 创建叙事状态快照 |
| `POST` | `/api/snapshot/restore` | 从快照恢复 ledgers |

### 流程图

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/flow/registry` | 获取节点注册表 |
| `POST` | `/api/flow/compose` | 一句话生成节点配置 |
| `POST` | `/api/flow/run` | 执行流程图 |
| `GET` | `/api/flow/workflows` | 列出所有工作流 |
| `POST` | `/api/flow/workflows` | 保存工作流 |
| `GET` | `/api/flow/workflows/{workflow_id}` | 加载工作流 |
| `DELETE` | `/api/flow/workflows/{workflow_id}` | 删除工作流 |
| `PUT` | `/api/flow/workflows/{workflow_id}` | 重命名工作流 |

### 伏笔管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/project/hooks/add` | 添加伏笔 |
| `GET` | `/api/project/hooks` | 获取伏笔列表 |
| `POST` | `/api/project/hooks/advance` | 推进伏笔 |
| `POST` | `/api/project/hooks/recover` | 回收伏笔 |
| `POST` | `/api/project/hooks/abandon` | 废弃伏笔 |

### 实体改名

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/project/rename-entity` | 全书实体批量改名 |

### 状态记忆

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/project/state-memory` | 读取蒸馏摘要 |

### 模板系统

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/templates/list` | 获取预置模板列表 |
| `POST` | `/api/templates/apply` | 应用模板 |

### 设置

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/settings/factions` | 列出所有势力/组织 |
| `POST` | `/api/settings/factions` | 新增/更新势力 |
| `GET` | `/api/settings/artifacts` | 列出所有道具/功法 |
| `POST` | `/api/settings/artifacts` | 新增/更新道具/功法 |

### 文件上传

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/file/parse` | 解析上传文件 |

### 审计日志

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/audit-log/list` | 获取审计日志列表 |
| `POST` | `/api/audit-log/log` | 记录审计事件 |
| `GET` | `/api/audit-log/stats` | 按类型分组统计 |

### 系统

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/workflow` | 工作流状态 |
| `POST` | `/api/workflow` | 执行工作流步骤 |
| `POST` | `/api/sanitizer/reload` | 热重载注入防护配置 |
---

## AI Agent 对话中枢

`POST /api/agent/chat` 是系统的核心智脑接口，将自然语言指令转化为后端 API 调用。

### 请求模型

```json
{
  "message": "生成第3章大纲",
  "context": {"current_chapter_index": 2, "current_step": 5},
  "selected_text": ""
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `message` | string | 是 | 用户的自然语言指令 |
| `context` | object | 否 | 上下文信息（当前章节、步骤等） |
| `selected_text` | string | 否 | 编辑器中选中的文字（触发选段修复） |

### 响应模型

```json
{
  "ok": true,
  "reply": "好的，我来生成第3章大纲...",
  "intent": "generate_outline",
  "data": {...},
  "action": {"type": "navigate", "page": "章节大纲"},
  "intermediate_reply": "正在识别意图...",
  "_trace_id": "abc123"
}
```

### Agent 支持的意图类型


**大纲Agent** (`outline`)

处理大纲生成相关意图

| intent | 说明 | 示例 |
| --- | --- | --- |
| `generate_outline` | 生成大纲 | 生成第3章大纲 |
| `generate_all_outlines` | 生成全部章节大纲 | 生成全部章节大纲 |

**章节Agent** (`chapter`)

处理章节生成/续写/优化相关意图

| intent | 说明 | 示例 |
| --- | --- | --- |
| `generate_chapter` | 生成章节正文 | 生成第5章 |
| `continue_writing` | 续写 | 续写500字 |
| `optimize_text` | 优化润色 | 润色这段文字 |
| `generate_all_chapters` | 生成全部章节正文 | 全部生成 |

**校验Agent** (`validate`)

处理校验/检查相关意图

| intent | 说明 | 示例 |
| --- | --- | --- |
| `check_continuity` | 检查连贯性（章节衔接） | 检查第一章连贯性 |
| `check_completeness` | 检查完整性（单章质量） | 检查第2章完整性 |
| `check_drift` | 检查剧情偏差 | 检查剧情是否偏离大纲 |
| `check_style` | 检查风格一致性 | 检查风格是否一致 |
| `check_all` | 全面检查（所有维度） | 全面检查第1章 |
| `check_batch` | 批量检查多章 | 批量检查所有章节 |

**世界观Agent** (`world`)

处理世界观设定相关意图

| intent | 说明 | 示例 |
| --- | --- | --- |
| `get_world` | 查看世界观设定 | 查看世界观 |
| `add_world_force` | 添加势力 | 添加势力青云门 |
| `add_world_location` | 添加地点 | 添加地点幽冥谷 |
| `add_world_item` | 添加物品 | 添加物品玄铁剑 |
| `add_setting` | 添加世界观设定（用户说"添加设定：xxx"时使用） | 添加设定：炁是造化、是灵机 |
| `delete_world_entity` | 删除世界观元素（"删除势力青云门""删掉地点幽冥谷""删除物品玄铁剑"） | 删除势力青云门 |

**人物Agent** (`character`)

处理人物设定相关意图

| intent | 说明 | 示例 |
| --- | --- | --- |
| `list_characters` | 列出角色 | 列出所有角色 |
| `add_character` | 添加角色（"添加角色：林墨，28岁，程序员"） | 添加角色：林墨，28岁，程序员 |
| `get_character_state` | 查看角色状态 | 查看陆远当前状态 |
| `update_character` | 更新角色状态 | 更新陆远的状态为重伤 |
| `generate_characters` | 生成人物档案（"生成人物档案""生成角色档案""创建人物"） | 生成人物档案 |
| `character_chat` | 角色对话 | 让陆远说句话 |
| `delete_character` | 删除人物（"删除人物林墨""把张三这个角色删掉"） | 删除人物林墨 |
| `edit_character` | 修改人物档案字段（"把林墨的性格改成冷淡寡言"） | 把林墨的性格改成冷淡寡言 |

**项目Agent** (`project`)

处理项目管理相关意图

| intent | 说明 | 示例 |
| --- | --- | --- |
| `create_project` | 新建小说项目（需要title和genre） | 新建一本仙侠小说叫《问道苍穹》 |
| `get_stats` | 查看写作统计 | 这周写了多少字 |
| `get_templates` | 获取大纲模板 | 有哪些大纲模板 |
| `apply_template` | 应用大纲模板 | 用退婚流模板 |

**章节管理Agent** (`chapter_manage`)

处理章节管理相关意图

| intent | 说明 | 示例 |
| --- | --- | --- |
| `list_chapters` | 列出章节 | 列出所有章节 |
| `load_chapter` | 加载章节内容 | 加载第3章 |
| `save_chapter` | 保存章节 | 保存当前章节 |
| `add_chapter` | 新建章节（"新建第6章""添加一章"） | 新建第6章 |
| `delete_chapter` | 删除章节（"删除第5章"） | 删除第5章 |
| `reorder_chapter` | 调整章节顺序（"把第2章移到第4章后面"） | 把第2章移到第4章后面 |
| `rename_chapter` | 重命名章节（"把第3章改名为风起"） | 把第3章改名为风起云涌 |

**记忆Agent** (`memory`)

处理记忆/伏笔/时间线相关意图

| intent | 说明 | 示例 |
| --- | --- | --- |
| `get_memory` | 查看记忆/伏笔/时间线 | 查看伏笔 |
| `memory_search` | 搜索记忆 | 搜索玉佩相关的记忆 |
| `get_timeline` | 查看时间线事件 | 查看时间线 |
| `recover_hook` | 回收伏笔 | 回收玉佩伏笔 |
| `add_hook` | 添加伏笔 | 添加伏笔：玉佩来历不明 |
| `abandon_hook` | 废弃伏笔（"废弃伏笔xxx""那个玉佩的伏笔不要了"） | 废弃伏笔玉佩 |

**导出Agent** (`export`)

处理导出/卷管理/版本对比相关意图

| intent | 说明 | 示例 |
| --- | --- | --- |
| `export_book` | 导出书籍（txt/epub/pdf） | 导出epub |
| `snapshot_diff` | 版本对比 | 对比版本 |
| `get_volumes` | 查看卷列表 | 查看卷列表 |
| `add_volume` | 新增卷（title为新卷名，description为卷简介可空） | 新增一卷叫龙起卷 |
| `delete_volume` | 删除卷（"删除第2卷""删掉龙起卷"） | 删除第2卷 |
| `rename_volume` | 重命名卷（"把第2卷改名为xxx"） | 把第2卷改名为龙起 |

**同步Agent** (`sync`)

处理云同步相关意图

| intent | 说明 | 示例 |
| --- | --- | --- |
| `sync_push` | 云同步上传 | 同步到云端 |
| `sync_pull` | 云同步下载 | 从云端同步 |
| `sync_config` | 云同步配置 | 配置云同步 |

**AI创作Agent** (`ai`)

处理通用对话、头脑风暴、五感描写、分析、总结等AI调用意图

| intent | 说明 | 示例 |
| --- | --- | --- |
| `general_chat` | 通用对话（不属于以上任何意图） | 你好 |
| `brainstorm` | 头脑风暴 | 帮我头脑风暴一个开篇 |
| `sensory` | 五感描写生成（视觉/听觉/嗅觉/触觉/味觉） | 给这段加视觉描写 |
| `ai_analyze` | AI分析文本提取设定 | 帮我分析这段提取设定 |
| `analyze_chapter` | 深度分析章节（"分析第1章的节奏""这章哪里有问题"） | 分析第1章的节奏和结构 |
| `summarize_plot` | 总结故事主线（"总结一下故事主线""梳理一下剧情"） | 总结一下故事主线 |

**编辑Agent** (`edit`)

处理查找替换相关意图

| intent | 说明 | 示例 |
| --- | --- | --- |
| `find_replace` | 全文查找替换（"把陆远替换为路远""全文替换xxx为yyy"） | 把陆远替换为路远 |

**创作向导Agent** (`wizard`)

处理创作向导相关意图

| intent | 说明 | 示例 |
| --- | --- | --- |
| `wizard` | 创作向导对话（用户正在走新手创作向导流程，回答题材/主角/剧情等问题。追加模式时stage应为append_outline，常见触发："延长故事""继续扩展""追加新阶段""故事还没写完""加一个大结局""再来一卷""继续发展剧情""追加""扩展大纲"） | 仙侠（在创作向导中回答题材） |

**搜索Agent** (`search`)

处理联网搜索相关意图

| intent | 说明 | 示例 |
| --- | --- | --- |
| `search` | 联网搜索（用户要求搜索、查资料、核实信息时使用，params.query为搜索关键词） | 搜索唐朝官制 |

**导航Agent** (`navigate`)

处理页面导航相关意图

| intent | 说明 | 示例 |
| --- | --- | --- |
| `open_page` | 打开页面/导航跳转（"打开时间线""去写作页""跳到伏笔管理"。params.page从以下列表选：世界观/人物/全书大纲/分卷/章节大纲/连线框/写作/时间线/草稿定稿/伏笔管理/头脑风暴/五感描写/写作统计/版本对比/云同步/导出/导入/大纲模板/批量检查/角色对话/技能包/AI编辑器/排行榜/描写/扩写/改写/反馈/AI分析/快捷模式/提炼/审计日志/创作向导/拆书/分镜/书架） | 打开伏笔管理 |

**选段修复** (`edit_selection`)

当 `selected_text` 长度大于 10 字符时触发，直接进入文本编辑模式。

---

## 附录: Agent 全部配置

共 15 个 Agent，配置来源: `backend/agents/agent_config.json`。

*（内容由AI生成，仅供参考）*
