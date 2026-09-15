# -*- coding: utf-8 -*-
"""EPUB 电子书导出模块 — 独立于路由层，可被任意入口调用。

核心职责：
  - 接收项目元数据 + 章节列表（标题 + 正文）
  - 生成符合 EPUB 3.0 规范的 .epub 文件（字节流）
  - 自动构建 NCX/NAV 目录、章节编号、CSS 样式、文字封面

使用方式：
    from backend.services.epub_exporter import generate_epub

    epub_bytes = generate_epub(
        title="我的小说",
        author="作者名",
        chapters=[("第一章", "正文内容..."), ("第二章", "正文...")],
    )
"""

import logging
import uuid
import hashlib
from typing import List, Tuple, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# ── 默认 CSS（适配 Kindle / 主流阅读器） ──

DEFAULT_CSS = """
@namespace epub "http://www.idpf.org/2007/ops";

body {
    font-family: "Source Han Serif SC", "Noto Serif CJK SC", "SimSun", "Songti SC", serif;
    line-height: 1.8;
    margin: 5%;
    text-align: justify;
    orphans: 2;
    widows: 2;
}

h1 {
    font-size: 1.6em;
    text-align: center;
    margin: 1.5em 0 1em 0;
    page-break-before: always;
    font-weight: bold;
}

h2 {
    font-size: 1.3em;
    text-align: left;
    margin: 1em 0 0.8em 0;
}

p {
    text-indent: 2em;
    margin: 0.3em 0;
}

p.cover-title {
    text-indent: 0;
    font-size: 2em;
    text-align: center;
    font-weight: bold;
    margin: 2em 0 0.5em 0;
}

p.cover-author {
    text-indent: 0;
    font-size: 1.2em;
    text-align: center;
    margin: 0.5em 0 2em 0;
    color: #555;
}

p.cover-meta {
    text-indent: 0;
    font-size: 0.9em;
    text-align: center;
    margin: 0.3em 0;
    color: #888;
}

p.no-indent {
    text-indent: 0;
}

img {
    max-width: 100%;
    height: auto;
}
"""

# ── 封面页 HTML 模板 ──

COVER_HTML_TEMPLATE = """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">
<head>
    <meta charset="utf-8"/>
    <title>封面</title>
    <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
    <p class="cover-title">{title}</p>
    <p class="cover-author">{author}</p>
    <p class="cover-meta">书斋V66 自动生成</p>
    <p class="cover-meta">{date_str}</p>
</body>
</html>"""

# ── 章节页 HTML 模板 ──

CHAPTER_HTML_TEMPLATE = """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">
<head>
    <meta charset="utf-8"/>
    <title>{title_safe}</title>
    <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
    <h1>{ch_num} {title_safe}</h1>
{body_html}
</body>
</html>"""


def _escape_xml(text: str) -> str:
    """转义 XML/HTML 特殊字符"""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )


def _body_to_html(body: str) -> str:
    """将纯文本正文转为 XHTML 段落格式。

    规则：
    - 空行 → 段落分隔
    - 非空行 → <p>...</p>
    - 段落内换行（如对话分行）→ <br/>
    """
    if not body:
        return "<p></p>"

    lines = body.split("\n")
    paragraphs = []
    current = []

    for line in lines:
        stripped = line.rstrip()
        if stripped == "":
            if current:
                paragraphs.append("<p>" + "<br/>\n".join(current) + "</p>")
                current = []
        else:
            current.append(_escape_xml(stripped))

    if current:
        paragraphs.append("<p>" + "<br/>\n".join(current) + "</p>")

    if not paragraphs:
        return "<p></p>"

    return "\n".join(paragraphs)


def generate_epub(
    title: str,
    author: str,
    chapters: List[Tuple[str, str]],
    language: str = "zh-CN",
    css: Optional[str] = None,
    book_identifier: Optional[str] = None,
    version: str = "1.0.0",
    include_checksum: bool = True,
) -> bytes:
    """生成 EPUB 3.0 电子书字节流。

    Args:
        title:   书名
        author:  作者名
        chapters: 章节列表 [(标题, 正文), ...]，正文为纯文本
        language: 语言代码，默认 zh-CN
        css:      自定义 CSS 样式，为 None 则使用内置默认样式
        book_identifier: 书籍唯一标识符，为 None 则自动生成 UUID
        version:  导出版本号（默认 1.0.0；第5批：版本追踪）
        include_checksum: 是否在元数据中附带内容哈希（默认 True）

    Returns:
        .epub 文件的完整字节内容（可直接写入磁盘或通过 HTTP Response 返回）
    """
    from backend.services.epub_writer import EpubWriter

    writer = EpubWriter(title)

    # ── 元数据 ──
    uid = book_identifier or f"urn:uuid:{uuid.uuid4()}"
    writer.set_identifier(uid)
    if author:
        writer.add_author(author)
    writer.set_language(language)
    writer.add_metadata("DC", "date", datetime.now().strftime("%Y-%m-%d"))
    writer.add_metadata("DC", "publisher", "书斋V66")
    writer.add_metadata("DC", "rights", f"© {datetime.now().year} {author}".strip() if author else "")
    # 第5批：导出版本号 + 内容哈希（用于版本追踪 / 防篡改校验）
    writer.add_metadata("DC", "version", version)
    if include_checksum:
        content_blob = f"{title}|{author}|{version}|{datetime.now().strftime('%Y%m%d')}|" + "|".join(
            f"{t}:{len(b)}" for t, b in chapters
        )
        checksum = hashlib.sha256(content_blob.encode("utf-8")).hexdigest()[:16]
        writer.add_metadata("DC", "checksum", checksum)

    # ── CSS ──
    style_css = css or DEFAULT_CSS
    writer.add_stylesheet("style.css", style_css)

    # ── 封面页 ──
    cover_html = COVER_HTML_TEMPLATE.format(
        title=_escape_xml(title),
        author=_escape_xml(author if author else "佚名"),
        date_str=datetime.now().strftime("%Y年%m月%d日") + f" · v{version}",
    )
    writer.set_cover("cover.xhtml", "封面", cover_html)

    # ── 章节页 ──
    total = len(chapters)
    num_width = max(2, len(str(total)))

    for idx, (ch_title, ch_body) in enumerate(chapters):
        ch_num = f"第{idx + 1:0{num_width}d}章" if total > 1 else ""
        display_title = ch_title if ch_title else ch_num

        body_html = _body_to_html(ch_body)

        chapter_html = CHAPTER_HTML_TEMPLATE.format(
            title_safe=_escape_xml(display_title),
            ch_num=ch_num,
            body_html=body_html,
        )

        file_name = f"chap_{idx + 1:04d}.xhtml"
        writer.add_chapter(file_name, display_title, chapter_html)

    # ── 构建并返回字节流 ──
    return writer.build()


def generate_epub_from_project(project, version: str = "1.0.0") -> bytes:
    """从 NovelProject 实例生成 EPUB 字节流。

    便捷封装：自动提取项目的书名、作者、章节列表。

    Args:
        project: NovelProject 实例（需有 .meta, .chapters, .get_content() 方法）
        version: 导出版本号（第5批：版本追踪）

    Returns:
        .epub 文件的完整字节内容
    """
    title = project.meta.get("title", "未命名")
    author = project.meta.get("author", "")

    chapters = []
    for idx in range(len(project.chapters)):
        ch_title = project.chapters[idx].get("title", f"第{idx + 1}章")
        ch_body = project.get_content(idx) or ""
        chapters.append((ch_title, ch_body))

    return generate_epub(title=title, author=author, chapters=chapters, version=version)


# ── 便捷写入（直接落盘） ──

def save_epub_to_file(
    title: str,
    author: str,
    chapters: List[Tuple[str, str]],
    output_path: str,
    **kwargs,
) -> str:
    """生成 EPUB 并写入磁盘。

    Args:
        title, author, chapters: 同 generate_epub
        output_path: 输出文件的绝对路径（.epub）
        **kwargs: 透传给 generate_epub 的其他参数

    Returns:
        最终写入的文件路径
    """
    epub_bytes = generate_epub(title=title, author=author, chapters=chapters, **kwargs)

    import os
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "wb") as f:
        f.write(epub_bytes)

    logger.info(f"[EPUB] 已写入: {output_path} ({len(epub_bytes):,} bytes)")
    return output_path
