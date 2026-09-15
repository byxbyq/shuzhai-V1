# -*- coding: utf-8 -*-
"""导出路由 - /api/export/*
支持将当前项目导出为 TXT / EPUB / PDF / 平台模板
- GET  /api/export/txt          纯文本导出
- GET  /api/export/epub         EPUB 电子书
- GET  /api/export/pdf          PDF 文档
- POST /api/export/platform     平台模板导出（fanqie/qidian/qimao）
"""
import io
import logging
import math
from typing import List, Tuple
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from backend.services.project_service import state
from backend.api_models import err, ErrorCode
from backend.project import NovelProject

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/export")


# ── 工具函数 ──
def _book_title() -> str:
    """从项目 meta 获取书名"""
    if not state.project:
        return "未命名"
    return state.project.meta.get("title", "未命名")


def _book_author() -> str:
    """从项目 meta 获取作者"""
    if not state.project:
        return ""
    return state.project.meta.get("author", "")


def _content_disposition(filename: str) -> dict:
    """构建支持中文文件名的 Content-Disposition 头。
    同时提供 ASCII fallback（filename=）和 RFC 5987 编码（filename*=），
    兼容主流浏览器。
    """
    # 注意：str.isalnum() 对中文字符返回True，必须加 isascii() 判断
    ascii_safe = "".join(c if (c.isascii() and (c.isalnum() or c in "._-")) else "_" for c in filename)[:40] or "book"
    encoded = quote(filename)
    return {
        "Content-Disposition": (
            f'attachment; filename="{ascii_safe}"; filename*=UTF-8\'\'{encoded}'
        )
    }


def _no_project() -> dict:
    return err(ErrorCode.PROJECT_NOT_OPEN, "未打开项目")


def _iter_chapters():
    """遍历当前项目的所有章节，返回 (index, title, content)"""
    for idx in range(len(state.project.chapters)):
        title = state.project.chapters[idx].get("title", f"第{idx + 1}章")
        body = state.project.get_content(idx)
        yield idx, title, body


# ── TXT 导出 ──
@router.get("/txt")
def export_txt():
    """导出为纯文本：标题 + 空行 + 正文，章节间以空行分隔"""
    if not state.project:
        return _no_project()
    try:
        parts = []
        for _idx, title, body in _iter_chapters():
            parts.append(f"{title}\n\n{body}")
        full_text = "\n\n".join(parts)

        book_title = _book_title()
        return Response(
            content=full_text.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers=_content_disposition(f"{book_title}.txt"),
        )
    except Exception as e:
        logger.exception("[Export] txt 导出失败")
        return err(ErrorCode.EXPORT_FAILED, f"导出失败: {e}")


# ── EPUB 导出 ──
@router.get("/epub")
def export_epub(version: str = "1.0.0"):
    """导出为 EPUB：每章一个 EpubHtml，write_epub 到 BytesIO"""
    if not state.project:
        return _no_project()
    try:
        from backend.services.epub_writer import EpubWriter
        import hashlib

        book_title = _book_title()
        author = _book_author()

        writer = EpubWriter(book_title)
        writer.set_identifier(book_title)
        writer.add_author(author)
        writer.set_language("zh-CN")
        # 第5批：导出版本号 + 内容哈希（版本追踪 / 防篡改）
        writer.add_metadata("DC", "version", version)

        chapter_payload = []
        for idx, title, body in _iter_chapters():
            safe_body = (
                body.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace("\n", "<br/>")
            )
            safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            chapter_html = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE html>\n'
                '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">\n'
                '<head><meta charset="utf-8"/><title>' + safe_title + '</title></head>\n'
                '<body>\n'
                f'<h1>{safe_title}</h1>\n'
                f'<p>{safe_body}</p>\n'
                '</body>\n</html>'
            )
            chapter_payload.append((title, len(body)))
            writer.add_chapter(f"chap_{idx + 1}.xhtml", title, chapter_html)

        content_blob = f"{book_title}|{author}|{version}|" + "|".join(
            f"{t}:{n}" for t, n in chapter_payload
        )
        writer.add_metadata("DC", "checksum", hashlib.sha256(content_blob.encode("utf-8")).hexdigest()[:16])

        epub_bytes = writer.build()
        return Response(
            content=epub_bytes,
            media_type="application/epub+zip",
            headers=_content_disposition(f"{book_title}.epub"),
        )
    except Exception as e:
        logger.exception("[Export] epub 导出失败")
        return err(ErrorCode.EXPORT_FAILED, f"导出失败: {e}")


# ── EPUB 导出（按项目路径，不依赖当前打开状态） ──
@router.get("/epub/{project_path:path}")
def export_epub_by_path(project_path: str, version: str = "1.0.0"):
    """通过项目路径导出 EPUB：加载指定项目后调用 epub_exporter 生成。

    项目路径需 URL 编码（如 D%3A%5Cnovel_projects%5C我的小说）。
    支持项目中 chapters 目录下的 .txt 文件作为章节正文。
    """
    import os as _os

    # 项目路径可能以盘符开头（如 D:\...），URL 解码后直接使用
    if not _os.path.isdir(project_path):
        return err(ErrorCode.NOT_FOUND, f"项目路径不存在: {project_path}")

    try:
        proj = NovelProject.open(project_path)
    except Exception as e:
        logger.exception("[Export] 打开项目失败: %s", project_path)
        return err(ErrorCode.EXPORT_FAILED, f"无法打开项目: {e}")

    if not proj:
        return err(ErrorCode.NOT_FOUND, f"无法加载项目: {project_path}")

    try:
        from backend.services.epub_exporter import generate_epub_from_project

        epub_bytes = generate_epub_from_project(proj, version=version)

        book_title = proj.meta.get("title", "未命名")
        return Response(
            content=epub_bytes,
            media_type="application/epub+zip",
            headers=_content_disposition(f"{book_title}.epub"),
        )
    except ImportError:
        return err(ErrorCode.VALIDATION_ERROR, "无法加载 EPUB 导出模块")
    except Exception as e:
        logger.exception("[Export] epub 导出失败: %s", project_path)
        return err(ErrorCode.EXPORT_FAILED, f"导出失败: {e}")


# ── PDF 导出 ──
@router.get("/pdf")
def export_pdf():
    """导出为 PDF：注册中文字体，SimpleDocTemplate + Paragraph 逐章渲染，PageBreak 分页"""
    if not state.project:
        return _no_project()
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return err(ErrorCode.VALIDATION_ERROR, "缺少 reportlab 库，请先执行 pip install reportlab")
    try:
        # 注册中文字体：优先微软雅黑(msyh.ttc)，其次宋体(simsun.ttc)，再次黑体
        font_name = None
        for path, name in [
            ("C:/Windows/Fonts/msyh.ttc", "MSYH"),
            ("C:/Windows/Fonts/simsun.ttc", "SimSun"),
            ("C:/Windows/Fonts/simhei.ttf", "SimHei"),
            ("C:/Windows/Fonts/msyh.ttf", "MSYH2"),
        ]:
            try:
                # .ttc 是字体集合，需指定 subfontIndex=0 取第一个子集
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=0))
                font_name = name
                logger.info(f"[Export] 注册中文字体: {name} <- {path}")
                break
            except Exception:
                continue
        if not font_name:
            return err(ErrorCode.NOT_FOUND, "未找到可用的中文字体（msyh.ttc / simsun.ttc）")

        book_title = _book_title()
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=60, rightMargin=60,
            topMargin=60, bottomMargin=60,
            title=book_title, author=_book_author(),
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ZhTitle", parent=styles["Title"], fontName=font_name,
            fontSize=20, leading=30, spaceAfter=14, alignment=1,  # 居中
        )
        body_style = ParagraphStyle(
            "ZhBody", parent=styles["Normal"], fontName=font_name,
            fontSize=12, leading=22, firstLineIndent=24,
        )

        story = []
        for idx, title, body in _iter_chapters():
            safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe_title, title_style))
            for line in body.split("\n"):
                line = line.strip()
                if not line:
                    continue
                # 转义 XML 特殊字符
                safe = (
                    line.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                )
                story.append(Paragraph(safe, body_style))
            story.append(PageBreak())

        doc.build(story)
        return Response(
            content=buf.getvalue(),
            media_type="application/pdf",
            headers=_content_disposition(f"{book_title}.pdf"),
        )
    except Exception as e:
        logger.exception("[Export] pdf 导出失败")
        return err(ErrorCode.EXPORT_FAILED, f"导出失败: {e}")


# ═══════════════════════════════════════════════════════════════
# 平台模板导出
# ═══════════════════════════════════════════════════════════════

class PlatformExportRequest(BaseModel):
    """平台导出请求体"""
    platform: str = "generic"  # fanqie / qidian / qimao / generic


def _collect_all_chapters() -> List[Tuple[int, str, str]]:
    """收集所有章节，返回 [(index, title, content)]"""
    result = []
    for idx in range(len(state.project.chapters)):
        title = state.project.chapters[idx].get("title", f"第{idx + 1}章")
        body = state.project.get_content(idx) or ""
        result.append((idx, title, body))
    return result


def _generate_chapter_summary(content: str, max_len: int = 100) -> str:
    """根据章节正文生成简短的章节简介（取开头段落截取）。
    由于不依赖AI调用，采用智能截取方式：
    - 优先取第一段
    - 截取到 max_len 字符，在句号处断句
    """
    if not content:
        return ""
    # 按换行分段，取第一个非空段落
    paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
    if not paragraphs:
        return ""
    text = paragraphs[0]
    if len(text) <= max_len:
        return text
    # 在 max_len 范围内寻找最后一个句号/感叹号/问号，在该处断句
    cut = max_len
    for punct in ("。", "！", "？", ".", "!", "?"):
        pos = text.rfind(punct, 0, max_len)
        if pos > 0:
            cut = pos + 1
            break
    return text[:cut]


def _generate_book_blurb(chapters: List[Tuple[int, str, str]], max_len: int = 200) -> str:
    """生成作品文案（简介）：取前三章各取一段组合。
    由于不依赖AI调用，采用智能拼接方式。
    """
    parts = []
    for idx, title, body in chapters[:3]:
        if not body:
            continue
        paragraphs = [p.strip() for p in body.split("\n") if p.strip()]
        if paragraphs:
            # 取每章第一段的前60字
            chunk = paragraphs[0][:60]
            if len(paragraphs[0]) > 60:
                # 在标点处截断
                for punct in ("。", "！", "？"):
                    pos = chunk.rfind(punct)
                    if pos > 0:
                        chunk = chunk[:pos + 1]
                        break
            parts.append(chunk)
    combined = "".join(parts)
    if len(combined) <= max_len:
        return combined
    # 整体截断
    cut = max_len
    for punct in ("。", "！", "？"):
        pos = combined.rfind(punct, 0, max_len)
        if pos > 0:
            cut = pos + 1
            break
    return combined[:cut]


def _split_by_word_count(text: str, words_per_chapter: int = 3000) -> List[str]:
    """按字数分割文本为多个段落，尽量在段落边界处断开。"""
    if not text or len(text) <= words_per_chapter:
        return [text] if text else []
    paragraphs = text.split("\n")
    chunks = []
    current = ""
    for para in paragraphs:
        if not current:
            current = para
        elif len(current) + len(para) + 1 <= words_per_chapter:
            current += "\n" + para
        else:
            chunks.append(current)
            current = para
    if current:
        chunks.append(current)
    return chunks


def _export_fanqie() -> Response:
    """番茄小说平台导出：自动按3000字分章、生成每章简介、生成作品文案。
    输出格式为 TXT，包含平台要求的元数据头。
    """
    book_title = _book_title()
    author = _book_author()
    chapters = _collect_all_chapters()

    # 拼接所有正文用于按字数分章
    all_text_parts = []
    for idx, title, body in chapters:
        all_text_parts.append(body)
    all_text = "\n\n".join(all_text_parts)

    # 按3000字分章
    split_parts = _split_by_word_count(all_text, 3000)

    # 构建导出内容
    lines = []
    lines.append(f"【书名】{book_title}")
    lines.append(f"【作者】{author}" if author else "【作者】未设置")

    # 生成作品文案
    blurb = _generate_book_blurb(chapters, 200)
    lines.append(f"【作品文案】{blurb}")
    lines.append("")
    lines.append("=" * 40)

    for i, part in enumerate(split_parts):
        ch_title = f"第{i + 1}章"
        summary = _generate_chapter_summary(part, 100)
        lines.append("")
        lines.append(f"{ch_title}")
        if summary:
            lines.append(f"【本章简介】{summary}")
        lines.append("")
        lines.append(part)
        lines.append("")
        lines.append("=" * 40)

    full_text = "\n".join(lines)
    return Response(
        content=full_text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers=_content_disposition(f"{book_title}_番茄小说.txt"),
    )


def _export_qidian() -> Response:
    """起点平台导出：生成卷标（每10章一卷）、按卷组织。
    输出格式为 TXT，含卷标结构。
    """
    book_title = _book_title()
    author = _book_author()
    chapters = _collect_all_chapters()

    # 每卷章节数
    chapters_per_volume = 10
    total_volumes = math.ceil(len(chapters) / chapters_per_volume)

    lines = []
    lines.append(f"【书名】{book_title}")
    lines.append(f"【作者】{author}" if author else "【作者】未设置")
    lines.append("")

    for vol in range(total_volumes):
        start_idx = vol * chapters_per_volume
        end_idx = min(start_idx + chapters_per_volume, len(chapters))
        vol_title = f"第{vol + 1}卷"

        lines.append("")
        lines.append("=" * 50)
        lines.append(f"  {vol_title}")
        lines.append("=" * 50)
        lines.append("")

        for idx in range(start_idx, end_idx):
            ch_title = chapters[idx][1]
            ch_body = chapters[idx][2]
            lines.append(ch_title)
            lines.append("")
            lines.append(ch_body)
            lines.append("")

    full_text = "\n".join(lines)
    return Response(
        content=full_text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers=_content_disposition(f"{book_title}_起点.txt"),
    )


def _export_qimao() -> Response:
    """七猫平台导出：自动添加封面占位、按章导出。
    输出格式为 TXT，每章独立分隔，含封面占位标记。
    """
    book_title = _book_title()
    author = _book_author()
    chapters = _collect_all_chapters()

    lines = []
    # 封面占位区
    lines.append("=" * 50)
    lines.append("  [封面占位]")
    lines.append(f"  请将封面图片命名为: {book_title}_封面.png")
    lines.append("  尺寸建议: 600x800 像素")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"【书名】{book_title}")
    lines.append(f"【作者】{author}" if author else "【作者】未设置")
    lines.append("")

    for idx, title, body in chapters:
        lines.append("-" * 50)
        lines.append(f"第{idx + 1}章 {title}")
        lines.append("-" * 50)
        lines.append("")
        lines.append(body)
        lines.append("")

    full_text = "\n".join(lines)
    return Response(
        content=full_text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers=_content_disposition(f"{book_title}_七猫.txt"),
    )


# 支持的平台列表
PLATFORM_MAP = {
    "fanqie": ("番茄小说", _export_fanqie),
    "qidian": ("起点中文网", _export_qidian),
    "qimao":  ("七猫小说", _export_qimao),
}


@router.post("/platform")
def export_platform(data: PlatformExportRequest):
    """平台模板导出：根据 platform 参数选择不同平台的导出格式。

    支持平台：
    - fanqie（番茄小说）：自动按3000字分章、生成每章简介（100字）、生成作品文案（200字）
    - qidian（起点）：生成卷标（每10章一卷）、按卷组织
    - qimao（七猫）：自动添加封面占位、按章导出
    - generic：保持原有TXT导出行为

    请求体：{"platform": "fanqie"} | {"platform": "qidian"} | ...
    """
    if not state.project:
        return _no_project()

    platform = data.platform.lower().strip()

    # generic 走原有TXT导出逻辑
    if platform == "generic" or platform == "":
        return export_txt()

    if platform not in PLATFORM_MAP:
        supported = ", ".join(f"{k}（{v[0]}）" for k, v in PLATFORM_MAP.items())
        return err(ErrorCode.INTERNAL_ERROR, f"不支持的平台: {platform}。支持: {supported}, generic")

    try:
        platform_name, export_func = PLATFORM_MAP[platform]
        logger.info("[Export] 平台模板导出: %s (%s)", platform_name, platform)
        return export_func()
    except Exception as e:
        logger.exception("[Export] 平台导出失败: %s", platform)
        return err(ErrorCode.EXPORT_FAILED, f"平台导出失败: {e}")


# ── 8.1 短剧脚本导出 ──

class ScriptExportRequest(BaseModel):
    chapter_range: str = ""         # "1-5" 或 "3" 或 ""（全部）
    include_stage_direction: bool = True


@router.post("/script")
def export_script(data: ScriptExportRequest):
    """短剧脚本导出：将章节内容按镜头号|场景|角色|对话/动作指令|备注模板格式化"""
    if not state.project:
        return _no_project()
    chapters = state.project.chapters
    if not chapters:
        return err(ErrorCode.INTERNAL_ERROR, "没有可导出的章节")

    # 解析章节范围
    indices = list(range(len(chapters)))
    if data.chapter_range:
        parts = data.chapter_range.split("-")
        if len(parts) == 2:
            start, end = int(parts[0]) - 1, int(parts[1]) - 1
            indices = list(range(max(0, start), min(len(chapters), end + 1)))
        else:
            idx = int(parts[0]) - 1
            indices = [idx] if 0 <= idx < len(chapters) else []

    # 拼接章节内容
    combined = ""
    for i in indices:
        ch = chapters[i]
        title = ch.get("title", f"第{i+1}章")
        content = ch.get("content", "")
        combined += f"\n\n【{title}】\n{content}"

    if not combined.strip():
        return err(ErrorCode.INTERNAL_ERROR, "选定章节无内容")

    # 基础模板：镜头号 | 场景 | 角色 | 对话/动作指令 | 备注
    header = "镜头号 | 场景 | 角色 | 对话/动作指令 | 备注\n" + "-" * 60 + "\n"
    # 简单按段落拆分（无 AI 辅助时用朴素规则）
    lines = []
    shot_num = 1
    for para in combined.split("\n\n"):
        para = para.strip()
        if not para or para.startswith("【"):
            continue
        # 按换行分句
        sentences = [s.strip() for s in para.split("\n") if s.strip()]
        for s in sentences:
            scene = ""
            character = ""
            action = ""
            note = ""
            # 简单启发式：引号内容为对话
            if "「" in s or '"' in s or '\u201c' in s or '\u201d' in s:
                character = ""
                action = s
                note = "对话"
            elif "。" in s or "！" in s or "？" in s:
                action = s
                note = "叙述"
            else:
                action = s
            lines.append(f"{shot_num} | {scene} | {character} | {action} | {note}")
            shot_num += 1

    output = header + "\n".join(lines)

    # 写入文件
    proj_title = _book_title()
    filename = f"{proj_title}_短剧脚本.txt"
    headers = _content_disposition(filename)
    headers["Content-Type"] = "text/plain; charset=utf-8"
    return Response(content=output.encode("utf-8"), headers=headers)
