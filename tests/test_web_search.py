# -*- coding: utf-8 -*-
"""web_search + ai_composer 联网调研链路契约测试（全程 mock，不发真实网络请求）

覆盖目标：
1. Bing HTML 解析结构（b_algo 块）改版时能被发现，而非静默降级
2. GitHub → jsDelivr URL 映射
3. fetch_content 对仓库主页路由到 fetch_github_readme
4. fetch_github_readme 候选顺序（README.md@main 优先）
5. ai_composer._search_api_docs 的三路搜索、去重与降级行为
"""
import asyncio

import pytest

from backend import web_search as ws
from backend.flow_engine import ai_composer as ac


# ═══════════════════════════════════════════
# Bing HTML 解析
# ═══════════════════════════════════════════

_FAKE_BING_HTML = """
<html><body><ol id="b_results">
<li class="b_algo">
  <h2><a href="https://github.com/MiniMax-AI/MiniMax-H3">MiniMax H3 GitHub 开源</a></h2>
  <div class="b_caption"><p>开源视频生成模型，支持 API 调用与本地部署。</p></div>
</li>
<li class="b_algo">
  <h2><a href="https://docs.minimax.io/video">MiniMax 视频 API 文档</a></h2>
  <p class="b_lineclamp2">官方 API 使用指南，含鉴权与任务轮询说明。</p>
</li>
<li class="b_algo">
  <h2><a href="https://baike.example.com/x">龙（中国神话传说中生物）_某百科</a></h2>
  <div class="b_caption"><p>神话生物条目，应被词典过滤器放行（非单字词典格式）。</p></div>
</li>
</ol></body></html>
"""


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


def test_search_parses_bing_algo_blocks(monkeypatch):
    """正常 Bing HTML → 解析出 title/url/snippet。"""
    monkeypatch.setattr(ws.httpx, "get", lambda *a, **k: _FakeResponse(_FAKE_BING_HTML))
    results = ws.search("MiniMax H3", max_results=5)
    assert len(results) >= 2
    assert results[0]["url"] == "https://github.com/MiniMax-AI/MiniMax-H3"
    assert "MiniMax H3 GitHub" in results[0]["title"]
    assert "开源视频生成模型" in results[0]["snippet"]
    assert results[1]["url"] == "https://docs.minimax.io/video"
    assert "官方 API 使用指南" in results[1]["snippet"]


def test_search_filters_single_char_dict_entries(monkeypatch):
    """单字词典条目（'X（...字...）_百度百科'）应被过滤。"""
    html = """
<li class="b_algo">
  <h2><a href="https://baike.baidu.com/item/x">龙（汉字）_百度百科</a></h2>
  <div class="b_caption"><p>汉字条目。</p></div>
</li>
<li class="b_algo">
  <h2><a href="https://keep.example.com/ok">保留的普通结果</a></h2>
  <div class="b_caption"><p>普通摘要。</p></div>
</li>
"""
    monkeypatch.setattr(ws.httpx, "get", lambda *a, **k: _FakeResponse(html))
    results = ws.search("龙", max_results=5)
    urls = [r["url"] for r in results]
    assert "https://baike.baidu.com/item/x" not in urls
    assert "https://keep.example.com/ok" in urls


def test_search_http_error_returns_empty(monkeypatch):
    """HTTP 非 200 → 返回空列表（不抛异常）。"""
    monkeypatch.setattr(ws.httpx, "get", lambda *a, **k: _FakeResponse("", status_code=503))
    assert ws.search("anything") == []


def test_search_network_exception_returns_empty(monkeypatch):
    """网络异常 → 返回空列表（不抛异常）。"""
    def _raise(*a, **k):
        raise ConnectionError("DNS fail")
    monkeypatch.setattr(ws.httpx, "get", _raise)
    assert ws.search("anything") == []


# ═══════════════════════════════════════════
# GitHub → jsDelivr URL 映射
# ═══════════════════════════════════════════

@pytest.mark.parametrize("url,expected", [
    (
        "https://github.com/user/repo",
        "https://cdn.jsdelivr.net/gh/user/repo@HEAD/README.md",
    ),
    (
        "https://github.com/user/repo/blob/main/README.md",
        "https://cdn.jsdelivr.net/gh/user/repo@main/README.md",
    ),
    (
        "https://raw.githubusercontent.com/user/repo/main/docs/a.md",
        "https://cdn.jsdelivr.net/gh/user/repo@main/docs/a.md",
    ),
])
def test_github_to_jsdelivr(url, expected):
    assert ws._github_to_jsdelivr(url) == expected


def test_github_to_jsdelivr_non_github():
    assert ws._github_to_jsdelivr("https://example.com/docs") is None


# ═══════════════════════════════════════════
# fetch_content / fetch_github_readme
# ═══════════════════════════════════════════

def test_fetch_content_routes_repo_home_to_readme(monkeypatch):
    """GitHub 仓库主页必须走 fetch_github_readme 多候选逻辑（避开 @HEAD 直连）。"""
    called = {}

    def fake_readme(repo_url, timeout=15, max_chars=6000):
        called["args"] = (repo_url, timeout, max_chars)
        return "README-BODY"

    monkeypatch.setattr(ws, "fetch_github_readme", fake_readme)
    text = ws.fetch_content("https://github.com/user/repo", timeout=15, max_chars=3000)
    assert text == "README-BODY"
    assert called["args"] == ("https://github.com/user/repo", 15, 3000)


def test_fetch_github_readme_candidate_order(monkeypatch):
    """候选顺序：README.md@main 必须排第一，正常仓库 1-2 个候选内命中。"""
    captured = {}

    def fake_fetch_first(urls, timeout, max_chars):
        captured["urls"] = urls
        return "OK"

    monkeypatch.setattr(ws, "_fetch_first", fake_fetch_first)
    ws.fetch_github_readme("https://github.com/user/repo")
    urls = captured["urls"]
    assert urls[0] == "https://cdn.jsdelivr.net/gh/user/repo@main/README.md"
    assert urls[1] == "https://cdn.jsdelivr.net/gh/user/repo@master/README.md"
    # 变体名（readme.md 等）排在 README.md 三分支之后
    assert "readme.md" not in urls[0] and "readme.md" not in urls[1] and "readme.md" not in urls[2]


def test_fetch_content_empty_url():
    assert ws.fetch_content("") == ""


# ═══════════════════════════════════════════
# ai_composer._search_api_docs
# ═══════════════════════════════════════════

def test_search_api_docs_empty_results(monkeypatch):
    """三路搜索全无结果 → 返回空串（compose 走知识兜底分支）。"""
    monkeypatch.setattr(ws, "search", lambda *a, **k: [])
    assert asyncio.run(ac._search_api_docs("MiniMax H3")) == ""


def test_search_api_docs_dedup_and_snippet_degrade(monkeypatch):
    """跨路重复 URL 去重；抓取全失败时仍有摘要保底。"""
    monkeypatch.setattr(ws, "search", lambda q, max_results=5: [
        {"title": "repo", "url": "https://github.com/u/r", "snippet": "snip-gh"},
        {"title": "repo dup", "url": "https://github.com/u/r", "snippet": "dup"},
        {"title": "doc", "url": "https://example.com/a", "snippet": "snip-doc"},
    ])
    monkeypatch.setattr(ws, "fetch_content", lambda *a, **k: "")
    ctx = asyncio.run(ac._search_api_docs("MiniMax H3"))
    assert ctx.count("github.com/u/r") == 1
    assert "snip-gh" in ctx and "snip-doc" in ctx
    assert "详细文档" not in ctx  # 抓取失败，无正文段


def test_search_api_docs_fetch_body_appended(monkeypatch):
    """抓取成功时正文进上下文，且 GitHub 链接优先抓取。"""
    fetch_urls = []

    monkeypatch.setattr(ws, "search", lambda q, max_results=5: [
        {"title": "doc", "url": "https://example.com/a", "snippet": "s1"},
        {"title": "repo", "url": "https://github.com/u/r", "snippet": "s2"},
    ])

    def fake_fetch(url, timeout, max_chars):
        fetch_urls.append((url, timeout))
        return "X" * 200 if "github.com" in url else ""

    monkeypatch.setattr(ws, "fetch_content", fake_fetch)
    ctx = asyncio.run(ac._search_api_docs("MiniMax H3"))
    assert "X" * 200 in ctx
    # GitHub 链接优先 + 15s 超时
    assert fetch_urls[0] == ("https://github.com/u/r", 15)


def test_search_api_docs_three_queries_issued(monkeypatch):
    """三路搜索各发一次查询，关键词分别覆盖 GitHub / ComfyUI / API 文档。"""
    queries = []
    monkeypatch.setattr(ws, "search", lambda q, max_results=5: (queries.append(q), [])[1])
    asyncio.run(ac._search_api_docs("MiniMax H3"))
    assert len(queries) == 3
    joined = " | ".join(queries)
    assert "GitHub" in joined and "ComfyUI" in joined and "API 文档" in joined


# ═══════════════════════════════════════════
# compose_and_register 返回图与前端契约
# ═══════════════════════════════════════════

def _node_config(node_id, name, inputs, outputs):
    return {
        "node_id": node_id,
        "node_name": name,
        "node_category": "工具",
        "inputs": [{"name": n, "type": "text"} for n in inputs],
        "outputs": [{"name": n, "type": "text"} for n in outputs],
        "steps": [],
        "output_map": {},
    }


@pytest.fixture
def composer_env(monkeypatch):
    """隔离的 compose 测试环境：无网络、无 AI、无持久化副作用。"""
    from backend.flow_engine.registry import NodeRegistry
    from backend.flow_engine.nodes import store as node_store

    async def no_search(target):
        return ""

    monkeypatch.setattr(ac, "_search_api_docs", no_search)
    monkeypatch.setattr(node_store, "save_config", lambda config: True)
    return NodeRegistry()


def test_compose_graph_node_port_format(composer_env, monkeypatch):
    """返回图新节点 inputs/outputs 必须是端口定义数组（前端靠 .length/findIndex 渲染）。"""
    import json
    resp = json.dumps({
        "node_config": _node_config("demo.tts", "朗读", ["text"], ["audio"]),
        "connections": [],
        "explanation": "ok",
    })

    async def fake_ai(prompt):
        return resp

    monkeypatch.setattr(ac, "_call_ai_safe", fake_ai)
    r = asyncio.run(ac.compose_and_register("加朗读", registry=composer_env))
    assert r["ok"]
    nd = r["graph"]["nodes"][0]
    assert isinstance(nd["inputs"], list) and nd["inputs"][0]["name"] == "text"
    assert isinstance(nd["outputs"], list) and nd["outputs"][0]["name"] == "audio"
    assert "values" in nd  # 前端参数字段兼容


def test_compose_graph_append_and_flat_edges(composer_env, monkeypatch):
    """二次追加：旧节点保留、新节点追加、边为扁平 from_node/to_node 格式。"""
    import json
    resp1 = json.dumps({
        "node_config": _node_config("demo.tts", "朗读", ["text"], ["audio"]),
        "connections": [], "explanation": "ok",
    })
    resp2 = json.dumps({
        "node_config": _node_config("demo.video", "合成", ["audio"], ["video"]),
        "connections": [{"from_node": "demo.tts", "from_port": "audio",
                          "to_node": "demo.video", "to_port": "audio"}],
        "explanation": "ok",
    })
    calls = [resp1, resp2]

    async def fake_ai(prompt):
        return calls.pop(0)

    monkeypatch.setattr(ac, "_call_ai_safe", fake_ai)
    r1 = asyncio.run(ac.compose_and_register("加朗读", registry=composer_env))
    r2 = asyncio.run(ac.compose_and_register(
        "再合成", registry=composer_env, existing_graph=r1["graph"]))
    ids = [n["instance_id"] for n in r2["graph"]["nodes"]]
    assert ids == ["demo.tts", "demo.video"]
    assert r2["graph"]["edges"] == [
        {"from_node": "demo.tts", "from_port": "audio",
         "to_node": "demo.video", "to_port": "audio", "label": ""}
    ]


def test_compose_graph_conflict_suffix_and_multi_node(composer_env, monkeypatch):
    """instance_id 冲突自动加后缀；node_configs 数组多节点返回。"""
    import json
    resp1 = json.dumps({
        "node_config": _node_config("demo.tts", "朗读", ["text"], ["audio"]),
        "connections": [], "explanation": "ok",
    })
    resp2 = json.dumps({
        "node_configs": [
            _node_config("demo.tts", "朗读2", ["text"], ["audio"]),
            _node_config("demo.mix", "混音", ["audio"], ["out"]),
        ],
        "connections": [{"from_node": "demo.tts", "from_port": "audio",
                          "to_node": "demo.mix", "to_port": "audio"}],
        "explanation": "ok",
    })
    calls = [resp1, resp2]

    async def fake_ai(prompt):
        return calls.pop(0)

    monkeypatch.setattr(ac, "_call_ai_safe", fake_ai)
    r1 = asyncio.run(ac.compose_and_register("加朗读", registry=composer_env))
    r2 = asyncio.run(ac.compose_and_register(
        "再加一套", registry=composer_env, existing_graph=r1["graph"]))
    ids = [n["instance_id"] for n in r2["graph"]["nodes"]]
    assert ids == ["demo.tts", "demo.tts_2", "demo.mix"]
    # AI 用 node_id 指代新节点 → 映射到实际 instance_id
    assert any(e["from_node"] == "demo.tts_2" and e["to_node"] == "demo.mix"
               for e in r2["graph"]["edges"])
