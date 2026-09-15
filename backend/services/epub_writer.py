# -*- coding: utf-8 -*-
"""纯 Python stdlib EPUB 3.0 生成器 — 零外部依赖，MIT 兼容。

基于 zipfile + xml.etree.ElementTree 实现，精确覆盖原 EbookLib 的
全部调用模式，无需修改上层业务逻辑。

用法示例:
    writer = EpubWriter("我的小说")
    writer.set_identifier("urn:uuid:...")
    writer.add_author("作者名")
    writer.set_language("zh-CN")
    writer.add_metadata("DC", "date", "2026-01-01")
    writer.add_stylesheet("style.css", "body { margin: 5%; }")
    writer.set_cover("cover.xhtml", "封面", "<html>...</html>")
    writer.add_chapter("chap_0001.xhtml", "第一章", "<html>...</html>")
    epub_bytes = writer.build()
"""

import io
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Tuple, Dict

# ── 命名空间常量 ──

NS_OPF   = "http://www.idpf.org/2007/opf"
NS_DC    = "http://purl.org/dc/elements/1.1/"
NS_XHTML = "http://www.w3.org/1999/xhtml"
NS_NCX   = "http://www.daisy.org/z3986/2005/ncx/"
NS_CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"

ET.register_namespace("", NS_XHTML)
ET.register_namespace("epub", NS_OPF)

MIMETYPE = "application/epub+zip"


# ── 内部辅助 ──

class _ChapterProxy:
    """get_chapter() 返回的兼容对象：.add_item() 为 no-op
    （add_chapter / set_cover 已自动关联已注册样式表）
    """

    def __init__(self, file_name: str):
        self.file_name = file_name
        self.title = ""

    def add_item(self, _item):
        """no-op：add_chapter 时已自动关联所有已注册样式表"""
        pass


def _xml_element(tag: str, attrib: dict = None, text: str = None, tail: str = None) -> ET.Element:
    """创建 ElementTree 元素，自动设置 text/tail/attrib。"""
    el = ET.Element(tag, **(attrib or {}))
    if text is not None:
        el.text = text
    if tail is not None:
        el.tail = tail
    return el


def _dc_element(name: str, text: str) -> ET.Element:
    """创建 dc: 命名空间元数据元素。"""
    return _xml_element(f"{{{NS_DC}}}{name}", text=text)


def _meta_element(name: str, content: str) -> ET.Element:
    """创建 opf:meta 元素。"""
    return _xml_element("meta", {"name": name, "content": content})


def _xml_declaration() -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n'


def _escape_xml_entities(text: str) -> str:
    """对 XML 特殊字符进行转义（用于元数据文本）。"""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )


# ── EpubWriter ──

class EpubWriter:
    """纯 stdlib EPUB 3.0 生成器，零依赖，MIT 兼容。

    精确覆盖 EbookLib 的 epub.EpubBook / epub.EpubHtml / epub.EpubItem /
    epub.EpubNcx / epub.EpubNav / epub.write_epub 全部调用模式。
    """

    def __init__(self, title: str):
        """初始化 EPUB，创建 Book 容器。"""
        self._title = title
        self._identifier: str = f"urn:uuid:{uuid.uuid4()}"
        self._authors: List[str] = []
        self._language: str = "zh-CN"
        self._meta: List[Tuple[str, str, str]] = []  # (namespace, key, value)

        # 样式表: {name: css_content}
        self._stylesheets: Dict[str, str] = {}

        # 页面条目: 列表保持添加顺序
        # (file_name, title, html_content, is_cover)
        self._pages: List[Tuple[str, str, str, bool]] = []

        # 封面信息
        self._has_cover: bool = False

    # ── 元数据 API ──

    def set_identifier(self, uid: str):
        """设置唯一标识符（dc:identifier）。"""
        self._identifier = uid

    def set_title(self, title: str):
        """设置书名（dc:title）。"""
        self._title = title

    def add_author(self, author: str):
        """添加作者（dc:creator），支持多次调用。"""
        if author:
            self._authors.append(author)

    def set_language(self, lang: str):
        """设置语言（dc:language）。"""
        self._language = lang

    def add_metadata(self, namespace: str, key: str, value: str):
        """添加 DC 命名空间元数据（如 date / publisher / rights 等）。

        Args:
            namespace: 如 "DC"
            key: 如 "date"
            value: 对应的值
        """
        self._meta.append((namespace, key, value))

    # ── 资源注册 API ──

    def add_stylesheet(self, name: str, css_content: str):
        """添加 CSS 样式文件到 Manifest。

        后续调用 add_chapter / set_cover 时，会自动在 HTML <head>
        中注入 <link rel="stylesheet" href="{name}"/>。
        """
        self._stylesheets[name] = css_content

    def _inject_stylesheets(self, html: str) -> str:
        """在 HTML <head> 中注入已注册样式表的 <link> 标签。"""
        links = "\n".join(
            f'    <link rel="stylesheet" type="text/css" href="{name}"/>'
            for name in self._stylesheets
        )
        if not links:
            return html
        # 在 </head> 前插入
        return html.replace("</head>", f"\n{links}\n</head>", 1)

    def add_chapter(self, file_name: str, title: str, html_content: str):
        """添加章节 XHTML 页面，自动关联已注册的样式表。

        Args:
            file_name: 如 "chap_0001.xhtml"
            title: 章节标题
            html_content: 完整的 XHTML 页面内容
        """
        html_content = self._inject_stylesheets(html_content)
        self._pages.append((file_name, title, html_content, False))

    def set_cover(self, file_name: str, title: str, html_content: str):
        """设置封面页。

        内部实现：封面页在 spine 中紧随 nav 之后（作为第一个内容页），
        并在 content.opf metadata 中添加 cover meta 标记。

        Args:
            file_name: 如 "cover.xhtml"
            title: 封面标题
            html_content: 完整的 XHTML 页面内容
        """
        html_content = self._inject_stylesheets(html_content)
        self._pages.append((file_name, title, html_content, True))
        self._has_cover = True

    def get_chapter(self, file_name: str) -> _ChapterProxy:
        """获取已添加的章节对象（兼容 EbookLib 的 .add_item 模式）。

        返回代理对象，其 .add_item() 为 no-op——因为 add_chapter /
        set_cover 已自动关联所有已注册样式表。
        """
        return _ChapterProxy(file_name)

    # ── 构建 ──

    def build(self) -> bytes:
        """构建完整 EPUB 3.0 包，返回 ZIP 字节流。

        生成的文件结构:
            mimetype          (不压缩)
            META-INF/container.xml
            OEBPS/content.opf
            OEBPS/toc.ncx     (EPUB 2 兼容)
            OEBPS/nav.xhtml   (EPUB 3 目录)
            OEBPS/style.css   (样式表)
            OEBPS/cover.xhtml (封面)
            OEBPS/chap_*.xhtml(章节)
        """
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1) mimetype — 第一条目，不压缩
            zi = zipfile.ZipInfo("mimetype")
            zi.compress_type = zipfile.ZIP_STORED
            zf.writestr(zi, MIMETYPE)

            # 2) META-INF/container.xml
            zf.writestr("META-INF/container.xml", self._build_container_xml())

            # 3) OEBPS/content.opf
            zf.writestr("OEBPS/content.opf", self._build_opf())

            # 4) OEBPS/toc.ncx (EPUB 2 兼容)
            zf.writestr("OEBPS/toc.ncx", self._build_ncx())

            # 5) OEBPS/nav.xhtml (EPUB 3 目录)
            zf.writestr("OEBPS/nav.xhtml", self._build_nav())

            # 6) 样式表
            for name, content in self._stylesheets.items():
                zf.writestr(f"OEBPS/{name}", content)

            # 7) 页面 (封面 + 章节)
            for file_name, _title, html_content, _is_cover in self._pages:
                zf.writestr(f"OEBPS/{file_name}", html_content)

        return buf.getvalue()

    # ── 内部构建方法 ──

    def _build_container_xml(self) -> str:
        """构建 META-INF/container.xml。"""
        root = ET.Element("container", {"version": "1.0", "xmlns": NS_CONTAINER})
        rootfiles = ET.SubElement(root, "rootfiles")
        ET.SubElement(rootfiles, "rootfile", {
            "full-path": "OEBPS/content.opf",
            "media-type": "application/oebps-package+xml",
        })
        return _xml_declaration() + ET.tostring(root, encoding="unicode")

    def _build_opf(self) -> str:
        """构建 OEBPS/content.opf（EPUB 3.0 package document）。"""
        # 根元素
        root = ET.Element(
            "package",
            {
                "xmlns": NS_OPF,
                "version": "3.0",
                "unique-identifier": "book-id",
            },
        )

        # ── metadata ──
        metadata = ET.SubElement(root, "metadata", {"xmlns:dc": NS_DC})
        ET.SubElement(metadata, f"{{{NS_DC}}}identifier", {"id": "book-id"}).text = self._identifier
        ET.SubElement(metadata, f"{{{NS_DC}}}title").text = _escape_xml_entities(self._title)
        for author in self._authors:
            ET.SubElement(metadata, f"{{{NS_DC}}}creator", {
                f"{{{NS_OPF}}}role": "aut"
            }).text = _escape_xml_entities(author)
        ET.SubElement(metadata, f"{{{NS_DC}}}language").text = self._language

        # 自定义 DC 元数据
        for ns, key, value in self._meta:
            if ns.upper() == "DC":
                ET.SubElement(metadata, f"{{{NS_DC}}}{key}").text = _escape_xml_entities(value)

        # cover meta
        if self._has_cover:
            ET.SubElement(metadata, "meta", {"name": "cover", "content": "cover"})

        # 生成时间
        ET.SubElement(metadata, "meta", {
            "property": "dcterms:modified",
        }).text = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        # ── manifest ──
        manifest = ET.SubElement(root, "manifest")
        ET.SubElement(manifest, "item", {
            "id": "ncx",
            "href": "toc.ncx",
            "media-type": "application/x-dtbncx+xml",
        })
        ET.SubElement(manifest, "item", {
            "id": "nav",
            "href": "nav.xhtml",
            "media-type": "application/xhtml+xml",
            "properties": "nav",
        })

        # 样式表
        for name in self._stylesheets:
            style_id = name.replace(".", "-")
            ET.SubElement(manifest, "item", {
                "id": style_id,
                "href": name,
                "media-type": "text/css",
            })

        # 页面 (封面 + 章节)
        for file_name, title, _html, is_cover in self._pages:
            item_id = file_name.replace(".", "-")
            attrs = {
                "id": item_id,
                "href": file_name,
                "media-type": "application/xhtml+xml",
            }
            if is_cover:
                attrs["properties"] = "cover"  # EPUB 3 cover-image property alternative
            ET.SubElement(manifest, "item", attrs)

        # ── spine ──
        spine = ET.SubElement(root, "spine", {"toc": "ncx"})
        ET.SubElement(spine, "itemref", {"idref": "nav", "linear": "no"})

        # 封面
        for file_name, _title, _html, is_cover in self._pages:
            if is_cover:
                item_id = file_name.replace(".", "-")
                ET.SubElement(spine, "itemref", {"idref": item_id})
                break

        # 章节 (非封面)
        for file_name, _title, _html, is_cover in self._pages:
            if not is_cover:
                item_id = file_name.replace(".", "-")
                ET.SubElement(spine, "itemref", {"idref": item_id})

        return _xml_declaration() + ET.tostring(root, encoding="unicode")

    def _build_ncx(self) -> str:
        """构建 OEBPS/toc.ncx（EPUB 2 兼容导航文件）。"""
        root = ET.Element("ncx", {
            "xmlns": NS_NCX,
            "version": "2005-1",
        })

        head = ET.SubElement(root, "head")
        ET.SubElement(head, "meta", {"name": "dtb:uid", "content": self._identifier})
        ET.SubElement(head, "meta", {"name": "dtb:depth", "content": "1"})
        ET.SubElement(head, "meta", {"name": "dtb:totalPageCount", "content": "0"})
        ET.SubElement(head, "meta", {"name": "dtb:maxPageNumber", "content": "0"})

        doc_title = ET.SubElement(root, "docTitle")
        ET.SubElement(doc_title, "text").text = _escape_xml_entities(self._title)

        nav_map = ET.SubElement(root, "navMap")
        play_order = 1

        for file_name, title, _html, is_cover in self._pages:
            nav_point = ET.SubElement(nav_map, "navPoint", {
                "id": f"navpoint-{play_order}",
                "playOrder": str(play_order),
            })
            nav_label = ET.SubElement(nav_point, "navLabel")
            ET.SubElement(nav_label, "text").text = _escape_xml_entities(title)
            ET.SubElement(nav_point, "content", {"src": file_name})
            play_order += 1

        return _xml_declaration() + ET.tostring(root, encoding="unicode")

    def _build_nav(self) -> str:
        """构建 OEBPS/nav.xhtml（EPUB 3 导航文档）。"""
        # 使用原始字符串拼接，因为 nav.xhtml 结构简单且需要精确的 XHTML 输出
        items = []
        for file_name, title, _html, _is_cover in self._pages:
            safe_title = _escape_xml_entities(title)
            safe_file = _escape_xml_entities(file_name)
            items.append(f'        <li><a href="{safe_file}">{safe_title}</a></li>')

        nav_items = "\n".join(items) if items else "        <li><a href=\"cover.xhtml\">封面</a></li>"

        return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{self._language}">
<head>
    <meta charset="utf-8"/>
    <title>目录</title>
</head>
<body>
    <nav epub:type="toc" id="toc">
        <h1>目录</h1>
        <ol>
{nav_items}
        </ol>
    </nav>
</body>
</html>'''
