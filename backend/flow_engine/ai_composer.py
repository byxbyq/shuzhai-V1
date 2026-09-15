# -*- coding: utf-8 -*-
"""
白城主 AI Composer — 自然语言 → 节点配置 + 自动连线

输入：自然语言描述 + 现有注册表
输出：新节点 JSON 配置 + 连线建议

流程：
    1. 理解用户意图（需要什么类型的节点）
    2. 联网搜索目标 API 文档
    3. 生成 MiniPipelineNode 配置
    4. 分析现有节点端口，生成连线建议
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# 项目根：backend/flow_engine/ai_composer.py → parents[2]
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ── AI 调用 ──

try:
    from backend.agents.intent_classifier import call_ai as _call_ai
except ImportError:
    _call_ai = None


_COMPOSE_SYSTEM_PROMPT = """你是白城主 AI 编排引擎，负责根据用户的自然语言描述生成可执行的节点配置。

你需要输出一个 JSON，包含：
1. "node_configs": 节点配置数组，可包含 1 到多个节点（每个是 MiniPipelineNode DSL）；若只生成 1 个节点，也可用单个对象 "node_config" 代替数组
2. "connections": 建议连线列表 [{from_node, from_port, to_node, to_port}]
3. "explanation": 一段简短解释

节点配置规范（必须严格遵守）：
- node_id: 唯一标识，格式为 "provider.功能"，例如 "hailuo.video", "kling.image"
- node_name: 中文名称
- node_category: 分类，如 "视频模型", "图像模型", "工具"
- inputs: 输入端口列表 [{name, type(text/number/boolean/any), description, required?}]
- outputs: 输出端口列表 [{name, type, description}]
- run_mode: 执行模式，三选一，按优先级选择：
    - "sdk_local": 官方 Python SDK 本地推理（首选，默认；RTX 4090 24GB 本地可跑主流开源模型）
    - "comfyui_bridge": 桥接本地 ComfyUI（仅当用户明确要求使用 ComfyUI 时）
    - "http_api": 调用第三方 HTTP API（末选；必须同时标注 need_network: true, possible_cost: true）
- run_code: 仅 run_mode=sdk_local 时需要，Python 代码，固定 IO 契约：
    - 输入：sys.argv[1] 指向临时 JSON 文件路径，内容为 {"inputs": {...}, "params": {...}}，用 json.load 读取
    - 输出：仅向 stdout 打印一个 JSON 结构体 {"ok": true, "outputs": {...}}；失败打印 {"ok": false, "error": "..."}
    - 禁止使用 os.system / subprocess / socket 等危险调用；本地推理优先用官方 SDK
- dependencies: 依赖清单（AI 生成节点时必须尽量给出，供依赖检测弹窗使用）
    - pip: 字符串数组，如 ["torch>=2.1", "huggingface_hub", "hailuo-h3"]，格式 "包名[>=版本]"
    - models: 数组，每项 {"repo_id": "HuggingFace仓库ID", "path": "models/相对路径", "size_approx": "15GB"}
    - system: 字符串数组，系统二进制依赖，如 ["ffmpeg"]（仅检测提示，不自动安装）
- 兼容旧字段：steps（HTTP API 链）仅在 run_mode=http_api 时使用：
  - api 步骤: {name, api: {url, method, headers, body, extract: {key: json_path}}}
  - poll 步骤: {name, poll: {url, until, interval_ms, timeout_ms}, extract: {key: json_path}}
- output_map: {output_port_name: "${step:step_name.key}"}（http_api 模式使用）

模板变量：
- ${input:port_name} — 从输入端口取值
- ${step:step_name.key} — 从前序步骤结果取值
- ${env:VAR_NAME} — 从环境变量取值（敏感信息如 API Key 必须用 env）

json_path 格式：$.data.field 或 data.field

连线规范：
- 根据类型匹配：text → text, any → 任意
- from_node 使用"现有可用节点"中列出的 instance_id，或本次新建节点的 node_id
- to_node 使用本次新建节点的 node_id（或现有节点 instance_id）
- 仅在类型兼容时连线

生成策略（重要）：
1. 优先分析目标模型/工具是否有官方 Python SDK，有则生成 run_mode=sdk_local + run_code + dependencies 的节点
2. 无官方 SDK 时才降级为 http_api steps 链
3. 生成的每个节点都要附上尽可能准确的 dependencies，模型大小按实际权重估算

请严格遵守 JSON 格式，不要输出 Markdown 代码块包裹。"""


async def _call_ai_safe(prompt: str) -> str:
    """安全调用 AI"""
    if _call_ai is None:
        raise RuntimeError("call_ai 不可用，请检查 intent_classifier 模块")
    # call_ai 是同步的，包装一下
    import asyncio
    return await asyncio.to_thread(_call_ai, prompt)


def _strip_ai_json_wrapper(raw: str) -> str:
    """剥离 AI 输出中的 think 标签与 markdown 代码块，返回可解析 JSON 文本。"""
    raw = re.sub(r"<think\b.*?</think\b\s*>", "", raw, flags=re.DOTALL)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    return cleaned


# ── 联网搜索 ──

_GITHUB_QUERIES = (
    "{target} GitHub 开源",
    "{target} ComfyUI 节点",
    "{target} API 文档 使用指南",
)

# 搜索上下文注入上限（字符），防止无关/超长内容淹没指令
_SEARCH_CONTEXT_MAX = 2500


def _extract_search_target(prompt: str) -> str:
    """从自然语言请求中提取核心搜索实体（模型/工具名）。

    直接整句搜索会被 Bing 拆词命中无关内容（如"加"字释义、手机官网），
    这里去掉命令前缀、括号说明和通用词，只留下疑似实体名。
    """
    s = re.sub(r"[（(][^）)]*[)）]", "", prompt)      # 去掉括号说明
    s = re.sub(r"[，。！？、,.;:：]", " ", s)
    # 去掉命令性前缀
    for w in ("帮我加", "请帮我加", "加一个", "添加一个", "新建", "创建一个", "创建",
              "生成", "新增", "做一个", "搞一个", "接入", "添加", "加", "请"):
        if s.strip().startswith(w):
            s = s.strip()[len(w):].lstrip()
            break
    # 去掉功能描述与连接词（"节点"、"输入…输出…"、"并自动连线"等）
    s = re.split(r"(节点|模型|工具|插件|接口|API|输入|输出|并自动|然后|最后|以及|和自动|自动连线)", s)[0]
    # 去掉尾部通用词
    s = re.sub(r"(视频|图像|图片|音频|语音|文字|文本|生成|转换|合成)$", "", s.strip()).strip()
    if not s or len(s) < 2:
        s = prompt.strip()
    return s[:30]


def _result_relevant(r: dict, target: str) -> bool:
    """搜索结果与目标实体的相关性过滤：标题/摘要/URL 至少命中一个实体词。"""
    text = f"{r.get('title', '')} {r.get('snippet', '')} {r.get('url', '')}".lower()
    toks = [t for t in re.split(r"[\s,，。.、/\\()（）\-_:：|]+", target) if len(t) >= 2]
    if not toks:
        return True
    return any(t.lower() in text for t in toks)


async def _search_api_docs(target: str) -> str:
    """
    调研目标模型/API 的适配情况（多路搜索 + 正文抓取）。

    策略：
    1. 从请求中提取核心实体作为搜索词，避免整句搜索命中无关内容
    2. 多路关键词搜索（GitHub / ComfyUI / API 文档），结果按 URL 去重 + 相关性过滤
    3. 所有相关结果的标题+摘要进上下文（不依赖抓取，保底可用）
    4. 优先抓取 GitHub 链接正文（自动走 jsDelivr CDN，免梯子）
    5. 抓取失败静默降级，只用摘要继续；总上下文限制 _SEARCH_CONTEXT_MAX 字符

    Returns:
        Markdown 格式的调研上下文
    """
    try:
        from backend.web_search import search, fetch_content
    except Exception:
        return ""

    search_term = _extract_search_target(target)
    if not search_term:
        return ""

    # 1. 多路搜索 + 去重（search 为同步阻塞调用，放线程池避免阻塞事件循环）
    seen: dict = {}
    for q in _GITHUB_QUERIES:
        try:
            results = await asyncio.to_thread(search, q.format(target=search_term), 5)
            for r in results:
                url = r.get("url", "")
                if url and url not in seen and _result_relevant(r, search_term):
                    seen[url] = r
        except Exception:
            continue

    if not seen:
        return ""

    # 2. 摘要进上下文
    context_parts = []
    total_len = 0
    for i, r in enumerate(seen.values(), 1):
        part = f"[{i}] {r.get('title', '')}\n{r.get('snippet', '')}\n来源：{r.get('url', '')}"
        if total_len + len(part) > _SEARCH_CONTEXT_MAX:
            break
        context_parts.append(part)
        total_len += len(part)

    # 3. 抓正文：GitHub 链接优先，最多抓 1 个（保底摘要已够用）
    gh_results = [r for r in seen.values() if "github.com" in r.get("url", "")]
    other_results = [r for r in seen.values() if "github.com" not in r.get("url", "")]
    for r in (gh_results + other_results)[:1]:
        url = r.get("url", "")
        if not url:
            continue
        try:
            # fetch_content 为同步函数，放线程池避免阻塞事件循环
            # GitHub 链接走 jsDelivr CDN 给足超时；普通网页 8s 兜底防卡死
            to = 15 if "github.com" in url else 8
            text = await asyncio.to_thread(fetch_content, url, to, 3000)
            if text and len(text) > 100:
                part = f"\n--- 详细文档（{r.get('title', '')}） ---\n{text[:1500]}"
                if total_len + len(part) <= _SEARCH_CONTEXT_MAX + 2000:
                    context_parts.append(part)
                    total_len += len(part)
        except Exception:
            continue

    return "\n\n".join(context_parts)


# ── 端口类型推断 ──

def _port_type_name(pt) -> str:
    """PortType → 字符串"""
    try:
        return pt.value
    except AttributeError:
        return str(pt)


def _types_compatible(src: str, dst: str) -> bool:
    """两个类型名是否兼容"""
    if src == dst:
        return True
    if "any" in (src, dst):
        return True
    # text ↔ string
    if {src, dst} <= {"text", "string"}:
        return True
    return False


# ── 核心编排 ──

async def compose(
    prompt: str,
    registry=None,
    existing_node_ids: Optional[List[str]] = None,
    existing_graph: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    根据自然语言描述生成节点配置和连线方案。

    Args:
        prompt: 用户自然语言描述，如 "加一个海螺视频生成节点，参考图用固定人物图的输出"
        registry: NodeRegistry 实例，默认全局
        existing_node_ids: 用户可能引用的现有节点 ID 列表，为空时使用全部
        existing_graph: 画布当前完整图 {"nodes": [...], "edges": [...]}，
            节点含 instance_id/node_id/inputs/outputs，用于 AI 感知画布已有实例

    Returns:
        {
            "ok": True/False,
            "node_configs": [...],       # MiniPipelineNode 配置列表（1~N 个）
            "connections": [...],        # 连线建议
            "explanation": "...",        # 解释
            "search_context": "...",     # 搜索到的 API 文档（调试用）
        }
    """
    from backend.flow_engine.registry import registry as global_registry

    reg = registry or global_registry

    # 1. 收集现有节点元信息（未注册的 ID 容错跳过，避免整体崩溃）
    existing_info = []
    if existing_graph and existing_graph.get("nodes"):
        # 画布实例优先：带 instance_id，AI 可直接引用连线
        for nd in existing_graph["nodes"]:
            nid = nd.get("node_id", "")
            iid = nd.get("instance_id", "")
            try:
                meta = reg.get_metadata(nid) if nid else None
            except Exception:
                meta = None
            name = (meta or {}).get("node_name") or nd.get("node_name") or nid or iid
            inputs = [(meta or {}).get("inputs") or nd.get("inputs") or []]
            outputs = [(meta or {}).get("outputs") or nd.get("outputs") or []]
            in_txt = ", ".join(f"{p['name']}({p.get('type', 'text')})" for p in inputs[0])
            out_txt = ", ".join(f"{p['name']}({p.get('type', 'text')})" for p in outputs[0])
            existing_info.append(f"- {iid} ({name}): 输入=[{in_txt}], 输出=[{out_txt}]")
    else:
        node_ids = existing_node_ids or reg.list_all()
        for nid in node_ids:
            try:
                meta = reg.get_metadata(nid)
            except Exception:
                logger.warning("[AIComposer] existing_node_ids 含未注册节点，已跳过: %s", nid)
                continue
            if meta:
                inputs = [f"{p['name']}({p.get('type','text')})" for p in meta.get("inputs", [])]
                outputs = [f"{p['name']}({p.get('type','text')})" for p in meta.get("outputs", [])]
                existing_info.append(
                    f"- {nid} ({meta.get('node_name','')}): 输入=[{', '.join(inputs)}], 输出=[{', '.join(outputs)}]"
                )

    existing_text = "\n".join(existing_info) if existing_info else "(空)"

    # 2. 联网搜索 API 文档
    logger.info("[AIComposer] 搜索 API 文档: %s", prompt)
    search_context = await _search_api_docs(prompt)

    # 3. 构建 AI 提示词
    compose_prompt = f"""{_COMPOSE_SYSTEM_PROMPT}

现有可用节点（输入/输出端口）：
{existing_text}

{ "以下是从网络搜索到的 API 文档参考：" if search_context else "(未找到 API 文档，请根据你对目标 API 的知识生成配置)" }
{search_context if search_context else ""}

用户请求：{prompt}

请生成 JSON："""

    # 4. 调用 AI
    ai_raw = await _call_ai_safe(compose_prompt)
    logger.info("[AIComposer] AI 响应长度: %d", len(ai_raw))

    # 5. 解析 JSON（多重兜底：剥离 think 标签 / markdown 包裹 / 贪婪提取大括号）
    result = None
    parse_error = None
    try:
        cleaned = _strip_ai_json_wrapper(ai_raw)
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        parse_error = e
        # 模型偶发输出"思考文本 + JSON"混合，贪婪提取最外层 {...} 兜底
        m = re.search(r"\{[\s\S]*\}", ai_raw)
        if m:
            try:
                result = json.loads(m.group())
            except json.JSONDecodeError:
                result = None

    if result is None:
        logger.warning("[AIComposer] JSON 解析失败: %s", parse_error)
        return {
            "ok": False,
            "error": f"AI 返回无法解析为 JSON: {parse_error}",
            "raw_response": ai_raw[:1000],
            "search_context": search_context,
        }

    # 6. 验证必要字段：兼容 node_configs 数组与单个 node_config
    node_configs = result.get("node_configs") or []
    if not node_configs and result.get("node_config"):
        node_configs = [result["node_config"]]
    node_configs = [nc for nc in node_configs if nc and nc.get("node_id")]
    if not node_configs:
        return {
            "ok": False,
            "error": "AI 生成的配置缺少 node_id / node_configs",
            "raw_response": ai_raw[:1000],
        }

    # 7. 生成即校验：Schema 校验 + 依赖检测（只读操作，不阻断生成）
    #    依赖检测结果随返回交给前端确认弹窗，用户可一次性看到缺失项。
    dependency_checks = await _check_node_dependencies(node_configs)

    return {
        "ok": True,
        "node_configs": node_configs,
        "connections": result.get("connections", []),
        "explanation": result.get("explanation", ""),
        "search_context": search_context,
        "dependency_checks": dependency_checks,
    }


async def _check_node_dependencies(node_configs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    对生成的节点配置做 Schema 校验 + 全量依赖检测。

    只读操作（importlib.metadata / shutil.which / 目录 stat / 磁盘空间），
    不安装、不下载、不改外部环境；结果供前端确认弹窗渲染。

    Returns:
        {node_id: {"schema_ok": bool, "schema_errors": [...], **verify_all 结果}}
    """
    from backend.flow_engine.deps.schema import validate_node_config
    from backend.flow_engine.deps.dependency_manager import DependencyManager
    from backend.flow_engine.deps.ast_scanner import scan_code_risks

    dm = DependencyManager(project_root=str(_PROJECT_ROOT))
    checks: Dict[str, Any] = {}

    for nc in node_configs:
        node_id = nc.get("node_id", "?")
        entry: Dict[str, Any] = {}

        # Schema 校验
        schema_ok, schema_errors = validate_node_config(nc)
        entry["schema_ok"] = schema_ok
        entry["schema_errors"] = schema_errors

        # AST 静态扫描（对 run_code 只读解析，不执行）
        run_code = nc.get("run_code")
        entry["ast_risks"] = scan_code_risks(run_code) if isinstance(run_code, str) and run_code.strip() else []

        # 依赖检测（仅当声明了 dependencies 且 schema 结构合法时）
        deps = nc.get("dependencies")
        if deps and isinstance(deps, dict):
            try:
                # 模型目录 stat 可能较慢（大目录 rglob），放线程池
                entry.update(await asyncio.to_thread(dm.verify_all, deps))
            except Exception as e:
                logger.warning("[AIComposer] 依赖检测失败 %s: %s", node_id, e)
                entry["error"] = str(e)
        else:
            entry["all_ok"] = True
            entry["note"] = "未声明依赖"

        checks[node_id] = entry

    return checks


async def compose_and_register(
    prompt: str,
    registry=None,
    existing_node_ids: Optional[List[str]] = None,
    existing_graph: Optional[dict] = None,
    rewrite_reason: str = "",
) -> Dict[str, Any]:
    """
    compose() + 自动注册 + 在画布现有图上追加生成 FlowGraph。

    这是给 API 层调用的完整方法。支持：
    - 单/多节点返回（node_configs 兼容）
    - existing_graph 传入画布当前图，返回"旧节点 + 新节点 + 全部连线"的完整图
    - rewrite_reason 传入用户驳回原因时，追加到 prompt 后重新生成（前端"驳回重写"）

    Returns:
        {
            "ok": True/False,
            "node_ids": [...],       # 新注册节点 node_id 列表
            "node_configs": [...],
            "graph": {...},          # 完整 FlowGraph.to_dict()
            "explanation": "...",
        }
    """
    from backend.flow_engine.registry import registry as global_registry
    from backend.flow_engine.graph import FlowGraph
    from backend.flow_engine.nodes.configurable import register_config_node

    reg = registry or global_registry

    # 驳回重写：把用户驳回原因拼进 prompt，引导 AI 针对性修正
    if rewrite_reason:
        prompt = (
            prompt
            + "\n\n【用户驳回原因，请针对性修正后重新输出全部节点配置】：\n"
            + rewrite_reason
        )

    # 1. AI 编排
    result = await compose(prompt, reg, existing_node_ids, existing_graph)
    if not result["ok"]:
        return result

    node_configs = result["node_configs"]
    node_ids = [nc["node_id"] for nc in node_configs]

    # 2. 注册节点（幂等）
    for nc in node_configs:
        try:
            register_config_node(nc, reg)
        except Exception as e:
            logger.warning("[AIComposer] 节点注册失败（可能已存在）: %s", e)

    # 3. 构建图：已有节点/边 → 新节点 → 连线
    g = FlowGraph()

    # 3.1 载入画布已有节点实例
    existing_instance_ids = set()
    old_meta = {}
    for nd in (existing_graph or {}).get("nodes", []):
        iid = nd.get("instance_id") or nd.get("node_id")
        nid = nd.get("node_id")
        if not iid or not nid:
            continue
        try:
            node = reg.create(nid, instance_id=iid)
            g.add_node(node)
            existing_instance_ids.add(iid)
            old_meta[iid] = nd
        except Exception as e:
            logger.warning("[AIComposer] 载入画布节点失败 %s: %s", iid, e)

    # 3.2 载入画布已有连线
    for ed in (existing_graph or {}).get("edges", []):
        try:
            g.connect(
                ed["from_node"], ed["from_port"],
                ed["to_node"], ed["to_port"],
                ed.get("label", ""),
            )
        except Exception as e:
            logger.warning("[AIComposer] 载入画布连线失败: %s", e)

    # 3.3 注册并添加新节点
    new_id_map = {}   # node_id -> instance_id（AI 连线里用 node_id 指代新节点）
    for nc in node_configs:
        nid = nc["node_id"]
        # instance_id 优先用 node_id；与画布冲突时加后缀
        iid = nid
        suffix = 2
        while iid in existing_instance_ids:
            iid = f"{nid}_{suffix}"
            suffix += 1
        try:
            new_node = reg.create(nid, instance_id=iid)
            g.add_node(new_node)
            existing_instance_ids.add(iid)
            new_id_map[nid] = iid
        except Exception as e:
            logger.warning("[AIComposer] 新节点创建失败 %s: %s", nid, e)

    # 3.4 添加 AI 建议连线（新节点引用 node_id → 映射到 instance_id）
    for conn in result.get("connections", []):
        src = conn.get("from_node")
        dst = conn.get("to_node")
        if not src or not dst:
            continue
        src_iid = new_id_map.get(src, src)
        dst_iid = new_id_map.get(dst, dst)
        try:
            g.connect(
                src_iid,
                conn.get("from_port", "reply"),
                dst_iid,
                conn.get("to_port", conn.get("from_port", "message")),
            )
        except Exception as e:
            logger.warning("[AIComposer] 连线失败: %s → %s: %s", src_iid, dst_iid, e)

    # 4. 输出格式适配前端：
    #    - edges：graph.to_dict 输出嵌套 from/to，前端需要扁平 from_node/to_node
    #    - nodes：to_dict 的 inputs/outputs 是运行时值字典，前端需要端口定义数组（含 name/type）
    graph_dict = g.to_dict()
    port_defs = {
        node.instance_id: {
            "inputs": [p.to_dict() for p in node.get_input_defs()],
            "outputs": [p.to_dict() for p in node.get_output_defs()],
        }
        for node in g.nodes
    }
    for nd in graph_dict.get("nodes", []):
        defs = port_defs.get(nd.get("instance_id"))
        if defs:
            nd["inputs"] = defs["inputs"]
            nd["outputs"] = defs["outputs"]
            # 前端节点携带 values（参数值），后端字段名为 params，双字段兼容
            nd["values"] = nd.get("params") or {}
    flat_edges = []
    for ed in graph_dict.get("edges", []):
        fr = ed.get("from", {})
        to = ed.get("to", {})
        flat_edges.append({
            "from_node": fr.get("node"),
            "from_port": fr.get("port"),
            "to_node": to.get("node"),
            "to_port": to.get("port"),
            "label": ed.get("label", ""),
        })
    graph_dict["edges"] = flat_edges

    return {
        "ok": True,
        "node_ids": node_ids,
        "node_configs": node_configs,
        "graph": graph_dict,
        "connections": result.get("connections", []),
        "explanation": result.get("explanation", ""),
        "dependency_checks": result.get("dependency_checks", {}),
    }
