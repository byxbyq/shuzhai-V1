# -*- coding: utf-8 -*-
"""
书斋 V66 - 意图执行/调度模块

v3: 全部意图已迁移到 12 个 Agent 子类（通过 AgentRegistry 注册表动态路由）。
dispatcher.py 现在只负责：
- 辅助函数（_resolve_chapter_index, _api_get, _api_post 等，被 Agent 共用）
- 常量映射（模板关键词、题材列表等，被 Agent 共用）
- 注册表初始化 + Agent 路由
- 选段修复独立入口（execute_edit_selection）
- 兜底回复

所有业务逻辑已分散到各 Agent 文件：
  outline, chapter, validate, world, character (example_agents.py)
  project, chapter_manage, memory, export, sync, ai, edit (独立文件)
"""

import json, re, urllib.request, logging, os
from backend.services.project_service import state
from backend.agents.intent_classifier import call_ai
from backend.agents.prompts import EDIT_SELECTION_PROMPT
from backend.agents.trace import TraceContext
from backend.prompt_sanitizer import sanitize_user_input, sanitize_light

logger = logging.getLogger(__name__)

def _get_base_url() -> str:
    """获取内部API基础URL，从环境变量读取端口"""
    port = os.environ.get("SHUZHAI_PORT", "8894")
    return f"http://127.0.0.1:{port}"

# ── 延迟导入，避免循环引用 ──
_registry = None
_registry_initialized = False


def _get_registry():
    """获取全局 AgentRegistry 单例（延迟初始化）"""
    global _registry
    if _registry is None:
        from backend.agents.agent_registry import get_registry
        _registry = get_registry()
    return _registry


def _ensure_registry_initialized():
    """确保注册表已加载所有 Agent（幂等），动态从 agent_config.json 读取。"""
    global _registry_initialized
    if _registry_initialized:
        return
    try:
        import importlib
        from backend.agents.config_loader import AgentConfig
        cfg = AgentConfig()
        registry = _get_registry()
        agent_count = 0
        for agent_cfg in cfg.get_agents():
            try:
                class_path = agent_cfg["class_path"]
                parts = class_path.rsplit(".", 1)
                module = importlib.import_module(parts[0])
                agent_cls = getattr(module, parts[1])
                agent_instance = agent_cls()
                registry.register(agent_instance)
                agent_count += 1
                logger.debug("[dispatcher] 动态注册 Agent: %s", agent_cfg["id"])
            except Exception as e:
                logger.warning("[dispatcher] 跳过 Agent '%s': %s", agent_cfg.get("id"), e)
        _registry_initialized = True
        logger.info("[dispatcher] Agent 注册表已初始化（%d个Agent）", agent_count)
    except Exception as e:
        logger.warning("[dispatcher] Agent 注册表初始化失败: %s", e)

# 内部API调用头（单用户模式，无需认证）
_INTERNAL_HEADERS = {"Content-Type": "application/json"}

# 共享常量（从 agent_config.json 加载，保留模块级变量保持向后兼容）
from backend.agents.config_loader import AgentConfig as _AgentConfig
_constants = _AgentConfig().get_constants()

_TEMPLATE_KEYWORD_MAP = _constants.get("template_keyword_map", {})
_ANALYZE_TYPE_MAP = _constants.get("analyze_type_map", {})
_WORLD_ENDPOINT_MAP = _constants.get("world_endpoint_map", {})
_WORLD_LABEL_MAP = _constants.get("world_label_map", {})
_GENRE_LIST = _constants.get("genre_list", [])
_FIND_REPLACE_PATTERNS = _constants.get("find_replace_patterns", [])


# ═══════════════════════════════════════════
# 辅助函数（被各 Agent 共用）
# ═══════════════════════════════════════════

def _resolve_chapter_index(params: dict, context: dict) -> int:
    """解析章节索引"""
    idx = params.get("chapter_index")
    if idx is None or idx == -1:
        idx = context.get("current_chapter_index", 0) if context else 0
    return max(0, idx)


def _get_chapter_content(index: int) -> tuple:
    """加载章节内容，返回 (title, content)"""
    if not state.project:
        return ("", "")
    project = state.project
    chapters = project.chapters
    if index < 0 or index >= len(chapters):
        return ("", "")
    ch = chapters[index]
    title = ch.get("title", f"第{index+1}章")
    content = project.get_content(index) or ""
    return (title, content)


def _api_get(url: str, timeout: int = 10) -> dict:
    """发起内部GET请求"""
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _api_post(url: str, body: dict, timeout: int = 300) -> dict:
    """发起内部POST请求"""
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_INTERNAL_HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _api_delete(url: str, timeout: int = 10) -> dict:
    """发起内部DELETE请求"""
    req = urllib.request.Request(url, headers=_INTERNAL_HEADERS, method="DELETE")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _clean_ai_output(text: str) -> str:
    """清理AI输出中的think标签和代码块标记"""
    text = re.sub(r'<think\b.*?</think\b\s*>', '', text, flags=re.DOTALL)
    text = text.strip()
    text = re.sub(r'^```\w*\s*', '', text)
    text = re.sub(r'\s*```$', '', text).strip()
    return text


def _looks_like_question(text: str) -> bool:
    """判断文本是否像一个问题（用于自动触发搜索）。"""
    text = text.strip()
    if len(text) < 4:
        return False
    # 包含问号、疑问词、或明显的查询意图
    question_words = ["什么", "怎么", "如何", "为什么", "是啥", "啥是", "查", "搜索",
                      "哪个", "哪里", "谁", "几", "多少", "吗", "呢", "吧",
                      "定义", "解释", "说明", "介绍", "背景", "历史",
                      "what", "how", "why", "who", "when", "where"]
    return text.endswith("?") or text.endswith("？") or any(w in text for w in question_words)


# ═══════════════════════════════════════════
# 选段修复（独立入口，不走意图识别）
# ═══════════════════════════════════════════

def execute_edit_selection(message: str, selected_text: str, context: dict) -> dict:
    """选段修复：根据用户指令修改选中的文字，返回修改后的文本"""
    idx = context.get("current_chapter_index", 0) if context else 0

    # 获取章节上下文（前后文）
    before_after = ""
    if state.project:
        try:
            full_content = state.project.get_content(idx) or ""
            pos = full_content.find(selected_text[:50])
            if pos >= 0:
                before = full_content[max(0, pos-200):pos]
                after_pos = pos + len(selected_text)
                after = full_content[after_pos:after_pos+200]
                if before:
                    before_after += f"\n【选中段落前文】\n{before}\n"
                if after:
                    before_after += f"\n【选中段落后文】\n{after}\n"
        except Exception as e:
            logger.debug("[dispatcher] 获取前后文失败: %s", e)

    prompt = EDIT_SELECTION_PROMPT.format(
        message=sanitize_user_input(message),
        selected_text=sanitize_light(selected_text),
        before_after=before_after,
    )

    try:
        new_text = call_ai(prompt)
        new_text = _clean_ai_output(new_text)

        if not new_text or len(new_text) < 5:
            return {"reply": "修改失败：AI返回内容为空，请重试。"}

        diff = len(new_text) - len(selected_text)
        diff_str = f"（{('+'+str(diff)) if diff >= 0 else str(diff)}字）" if diff != 0 else ""

        return {
            "reply": f"已修改选中段落{diff_str}，请查看编辑器。",
            "action": {
                "type": "replace_selection",
                "new_text": new_text,
                "original_text": selected_text
            }
        }
    except Exception as e:
        return {"reply": f"修改失败：{str(e)}"}


# ═══════════════════════════════════════════
# 意图执行主函数
# ═══════════════════════════════════════════

def execute_intent(intent: str, params: dict, context: dict, message: str) -> dict:
    """执行识别出的意图，返回结果。

    v3: 全部意图通过 AgentRegistry 查找匹配的 Agent 处理。
    每次调用创建一条 TraceContext 用于调用链追踪。
    """
    # ── 创建调用链追踪 ──
    trace = TraceContext.new_root("execute_intent")
    trace.log_event("intent_received", {"intent": intent, "message": message[:100]})

    # ── 通过注册表查找 Agent ──
    _ensure_registry_initialized()
    registry = _get_registry()
    agent = registry.find(intent)

    if agent is not None:
        # 将 intent 注入 params 供 Agent 内部路由
        agent_params = dict(params)
        agent_params["_intent"] = intent
        agent_params["message"] = message
        # 创建子 span 追踪 Agent 执行
        child_span = trace.new_span(f"agent.{agent.agent_id}")
        try:
            agent_result = agent.run(agent_params, context)
            # 合并 trace 信息到结果
            agent_result["intent"] = intent
            agent_result["_trace"] = trace.to_dict()
            if not agent_result.get("reply"):
                agent_result["reply"] = ""
            if "data" not in agent_result:
                agent_result["data"] = None
            if "action" not in agent_result:
                agent_result["action"] = None
            trace.log_event("agent_dispatched", {
                "agent_id": agent.agent_id,
                "agent_name": agent.agent_name,
                "has_reply": bool(agent_result.get("reply")),
            })
            return agent_result
        except Exception as e:
            logger.error("[dispatcher] Agent 执行失败: %s", e, exc_info=True)
            return {"reply": f"处理失败：{e}", "intent": intent, "_trace": trace.to_dict()}
        finally:
            trace.activate()  # 恢复父 span

    # ── 兜底：未匹配任何 Agent ──
    logger.warning("[dispatcher] 未找到匹配 Agent: intent=%s", intent)
    
    # 自动尝试联网搜索 + AI 合成：消息较长且像问题时
    if message and len(message.strip()) >= 4 and _looks_like_question(message):
        try:
            from backend.web_search import search
            results = search(message.strip(), max_results=5)
            if results:
                # 组装搜索上下文
                context_parts = []
                for i, r in enumerate(results, 1):
                    line = f"[{i}] {r['title']}\n{r['snippet'][:300]}\n来源：{r['url']}"
                    context_parts.append(line)
                context_text = "\n\n".join(context_parts)

                prompt = (
                    "你是书斋V66的AI创作助手，请根据以下联网搜索结果回答用户问题。\n\n"
                    "要求：用简洁清晰的语言直接回答问题；如果搜索结果充分，提炼关键信息作答；"
                    "如果搜索结果不足或不相关，如实说明，不要编造；回答末尾列出参考来源。\n\n"
                    f"用户问题：{message}\n\n"
                    f"联网搜索结果：\n{context_text}\n\n"
                    "请回答："
                )
                reply = call_ai(prompt)
                return {
                    "intent": "search",
                    "reply": reply,
                    "data": results,
                    "action": "show_search_results",
                    "_trace": trace.to_dict(),
                }
        except Exception as e:
            logger.debug("[dispatcher] 自动搜索失败: %s", e)
    
    result = {
        "intent": intent,
        "reply": "我暂时还不支持这个操作。你可以试试：\n- 打开任意页面（如“打开时间线”“去写作页”）\n- 检查连贯性/完整性/偏差/风格\n- 生成大纲/续写/优化\n- 导出txt/epub\n- 列出角色/查看时间线/搜索记忆\n- 选中文字后输入修改要求（选段修复）\n- 分析章节/总结故事主线\n- 全文查找替换\n- 新建/删除章节\n- 五感描写/角色对话/头脑风暴",
        "data": None,
        "action": None,
        "_trace": trace.to_dict(),
    }
    return result
