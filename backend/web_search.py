# -*- coding: utf-8 -*-
"""书斋 V66 - 网络搜索模块
使用 Bing 中国版 HTML 解析，无需 API Key。
支持正文抓取：普通网页直接抓取；GitHub 仓库自动走 jsDelivr CDN（免梯子）。
"""
import re
import httpx
import logging
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://cn.bing.com/search"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}
# jsDelivr CDN：GitHub 仓库文件免梯子镜像
_JSDELIVR_GH = "https://cdn.jsdelivr.net/gh"
_GITHUB_BRANCHES = ("main", "master", "HEAD")
_README_NAMES = ("README.md", "readme.md", "README.MD", "Readme.md", "readme.markdown", "README")


class _TextExtractor(HTMLParser):
    """提取 HTML 正文为纯文本（跳过 script/style/noscript）。"""

    def __init__(self):
        super().__init__()
        self.text = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip_depth > 0:
            self.skip_depth -= 1

    def handle_data(self, data):
        if self.skip_depth == 0:
            self.text.append(data.strip())

    def text_joined(self, max_chars: int = 0) -> str:
        raw = " ".join(t for t in self.text if t)
        raw = re.sub(r"\s+", " ", raw)
        if max_chars and len(raw) > max_chars:
            return raw[:max_chars]
        return raw


def _extract_text(html: str, max_chars: int = 3000) -> str:
    """HTML → 纯文本摘要"""
    try:
        ex = _TextExtractor()
        ex.feed(html)
        return ex.text_joined(max_chars)
    except Exception as e:
        logger.warning("HTML 提取失败: %s", e)
        return ""


def _github_to_jsdelivr(url: str):
    """GitHub 页面 URL → jsDelivr CDN 文件 URL；非 GitHub 链接返回 None。

    支持形态：
      github.com/user/repo                     → README.md
      github.com/user/repo/blob/branch/path    → 对应文件
      github.com/user/repo/raw/branch/path     → 对应文件
      raw.githubusercontent.com/user/repo/branch/path → 对应文件
    """
    url = url.strip()
    m = re.match(r"https?://github\.com/([^/]+)/([^/?#]+)(?:\.git)?(?:/(?:blob|raw)/([^/]+)/(.+))?", url)
    if m:
        user, repo = m.group(1), m.group(2)
        branch, path = m.group(3), m.group(4)
        if branch and path:
            return f"{_JSDELIVR_GH}/{user}/{repo}@{branch}/{path}"
        return f"{_JSDELIVR_GH}/{user}/{repo}@HEAD/README.md"
    m = re.match(r"https?://raw\.githubusercontent\.com/([^/]+)/([^/]+?)(?:\.git)?/([^/]+)/(.+)", url)
    if m:
        user, repo, branch, path = m.group(1), m.group(2), m.group(3), m.group(4)
        return f"{_JSDELIVR_GH}/{user}/{repo}@{branch}/{path}"
    return None


def _fetch_first(urls, timeout: int, max_chars: int) -> str:
    """依次抓取 URL 列表，返回第一个成功提取的正文；全部失败返回空串。"""
    for u in urls:
        try:
            r = httpx.get(u, headers=_HEADERS, timeout=timeout, follow_redirects=True)
            if r.status_code == 200 and len(r.text) > 100:
                text = _extract_text(r.text, max_chars)
                if text:
                    return text
            else:
                logger.warning("抓取状态异常 %s → %d", u, r.status_code)
        except Exception as e:
            logger.warning("抓取失败 %s: %s", u, e)
    return ""


def fetch_content(url: str, timeout: int = 15, max_chars: int = 3000) -> str:
    """抓取网页正文，返回纯文本。

    - GitHub 链接自动走 jsDelivr CDN（免梯子），CDN 失败再降级直连
    - 普通网页直接抓取
    - 失败返回空字符串

    Args:
        url: 目标 URL
        timeout: 超时秒数
        max_chars: 返回正文最大字符数
    """
    if not url:
        return ""
    # GitHub 仓库主页 → 走多候选 README（main/master/HEAD × 常见文件名），避开 @HEAD 直连超时
    if re.match(r"https?://github\.com/[^/]+/[^/?#]+/?$", url.strip()):
        text = fetch_github_readme(url, timeout, max_chars)
        if text:
            return text
        return ""
    cdn_url = _github_to_jsdelivr(url)
    if cdn_url:
        text = _fetch_first([cdn_url], timeout, max_chars)
        if text:
            return text
        logger.warning("jsDelivr CDN 失败，降级直连 GitHub: %s", url)
    return _fetch_first([url], timeout, max_chars)


def fetch_github_readme(repo_url: str, timeout: int = 15, max_chars: int = 6000) -> str:
    """抓取 GitHub 仓库 README（走 jsDelivr CDN，免梯子）。

    自动尝试 main/master/HEAD 分支与常见 README 文件名。
    失败返回空字符串。
    """
    m = re.match(r"https?://github\.com/([^/]+)/([^/?#]+)(?:\.git)?", repo_url)
    if not m:
        return ""
    user, repo = m.group(1), m.group(2)
    # 优先尝试各分支的 README.md（正常仓库 1-2 个候选内命中），再试其它变体名
    candidates = [
        f"{_JSDELIVR_GH}/{user}/{repo}@{branch}/{name}"
        for name in _README_NAMES
        for branch in _GITHUB_BRANCHES
    ]
    return _fetch_first(candidates, timeout, max_chars)


def search(query: str, max_results: int = 5, timeout: int = 15) -> list[dict]:
    """搜索网页，返回结果列表。

    Args:
        query: 搜索关键词
        max_results: 最大结果数（1-10）
        timeout: 超时秒数

    Returns:
        [{title, url, snippet}, ...]
    """
    if max_results < 1:
        max_results = 1
    if max_results > 10:
        max_results = 10

    # Request more results to filter out noise
    fetch_count = max(min(max_results * 3, 15), 10)
    
    try:
        r = httpx.get(
            _SEARCH_URL,
            params={"q": query, "count": fetch_count, "setmkt": "zh-CN"},
            headers=_HEADERS,
            timeout=timeout,
            follow_redirects=True,
        )
        if r.status_code != 200:
            logger.warning("Bing search returned %d", r.status_code)
            return []
    except Exception as e:
        logger.warning("Bing search failed: %s", e)
        return []

    results = []
    blocks = re.findall(r'<li class="b_algo"[^>]*>(.*?)</li>', r.text, re.DOTALL)

    for block in blocks:
        title_m = re.search(r'<h2[^>]*>.*?<a[^>]*>(.*?)</a>', block, re.DOTALL)
        url_m = re.search(r'<a[^>]*href="(https?://[^"]+)"', block)
        snippet_m = re.search(
            r'(?:class="b_caption"[^>]*>|class="b_lineclamp[^"]*"[^>]*>)(.*?)(?:</p>|</div>)',
            block,
            re.DOTALL,
        )

        title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else ""
        url = url_m.group(1) if url_m else ""
        snippet = re.sub(r'<[^>]+>', '', snippet_m.group(1)).strip() if snippet_m else ""
        snippet = snippet.replace("&ensp;", " ").replace("&#183;", "·").replace("&amp;", "&").strip()

        if not title or not url:
            continue
        
        # 过滤：单字词典条目
        if re.match(r'^.{1,2}（.*字.*）_百度百科$', title):
            continue
        # 过滤：纯拼音/笔画条目
        if re.search(r'拼音|部首|笔顺|的意思,', title) and len(title) < 30:
            continue
        # 过滤：神话传说词典条目（非创作类）
        if re.match(r'^.{1,3}（中国神话传说中人物）', title):
            continue

        results.append({"title": title, "url": url, "snippet": snippet[:300]})

        if len(results) >= max_results:
            break

    logger.info("Search '%s' → %d results", query[:40], len(results))
    return results


def search_for_context(query: str, max_results: int = 3) -> str:
    """搜索并返回格式化的上下文文本，直接注入 Agent prompt。

    Returns:
        格式化的搜索结果字符串，无结果时返回空字符串。
    """
    results = search(query, max_results)
    if not results:
        return ""

    parts = ["\n[网络搜索参考]"]
    for i, r in enumerate(results, 1):
        parts.append(f"{i}. {r['title']}\n   {r['snippet']}\n   来源: {r['url']}")
    return "\n".join(parts)
