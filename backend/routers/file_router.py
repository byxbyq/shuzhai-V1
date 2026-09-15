# -*- coding: utf-8 -*-
"""文件路由 - /api/file/*"""
import os, tempfile, shutil, csv, logging
from fastapi import APIRouter, Request

from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/file")

@router.post("/parse")
async def parse_uploaded_file(request: Request):
    """解析上传的文件，返回文本内容。支持 txt/md/docx/xlsx/csv/pdf"""
    try:
        form = await request.form()
        files = form.getlist("files")
        if not files:
            return err(ErrorCode.INTERNAL_ERROR, "没有文件")
        results = []
        for f in files:
            ext = os.path.splitext(f.filename or "")[1].lower()
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            shutil.copyfileobj(f.file, tmp)
            tmp.close()
            try:
                text = _extract_text(tmp.name, ext)
                if text:
                    results.append({"name": f.filename, "text": text, "size": len(text)})
                else:
                    results.append({"name": f.filename, "error": "无法提取文本"})
            finally:
                os.unlink(tmp.name)
        combined = "\n\n".join(r["text"] for r in results if "text" in r)
        return {"ok": True, "results": results, "combined": combined}
    except Exception as e:
        logger.warning(f"File parse error: {e}")
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")

def _detect_encoding(filepath):
    """自动检测文件编码（分块读取，避免大文件OOM）"""
    # 先尝试UTF-8（含BOM）
    with open(filepath, 'rb') as f:
        raw = f.read(8192)  # 只读前8KB检测编码
    # UTF-8 BOM
    if raw[:3] == b'\xef\xbb\xbf':
        return 'utf-8-sig'
    # UTF-16 BOM
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return 'utf-16'
    # 尝试UTF-8严格解码
    try:
        raw.decode('utf-8')
        return 'utf-8'
    except UnicodeDecodeError:
        pass
    # 尝试GBK
    try:
        raw.decode('gbk')
        return 'gbk'
    except UnicodeDecodeError:
        pass
    # 尝试GB2312
    try:
        raw.decode('gb2312')
        return 'gb2312'
    except UnicodeDecodeError:
        pass
    # 尝试Big5（繁体）
    try:
        raw.decode('big5')
        return 'big5'
    except UnicodeDecodeError:
        pass
    # 兜底
    return 'utf-8'


def _extract_text(filepath, ext):
    try:
        if ext in ('.txt', '.md', '.text', '.markdown'):
            enc = _detect_encoding(filepath)
            with open(filepath, 'r', encoding=enc, errors='replace') as f:
                return f.read()
        elif ext == '.csv':
            rows = []
            enc = _detect_encoding(filepath)
            with open(filepath, 'r', encoding=enc, errors='replace') as f:
                reader = csv.reader(f)
                for row in reader:
                    rows.append('\t'.join(row))
            return '\n'.join(rows)
        elif ext == '.docx':
            try:
                import docx
                doc = docx.Document(filepath)
                return '\n'.join(p.text for p in doc.paragraphs)
            except ImportError:
                import zipfile, xml.etree.ElementTree as ET
                with zipfile.ZipFile(filepath) as z:
                    # 尝试标准路径，失败则遍历查找
                        doc_xml = None
                        for name in z.namelist():
                            if name.endswith('document.xml') and 'word' in name:
                                doc_xml = name
                                break
                        if not doc_xml:
                            return ''
                        with z.open(doc_xml) as xf:
                            tree = ET.parse(xf)
                        texts = [t.text for t in tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t') if t.text]
                        return ''.join(texts)
        elif ext == '.xlsx':
            try:
                import openpyxl
                wb = openpyxl.load_workbook(filepath, read_only=True)
                sheets = []
                for ws in wb.worksheets:
                    rows = []
                    for row in ws.iter_rows(values_only=True):
                        rows.append('\t'.join(str(c) if c else '' for c in row))
                    if rows:
                        sheets.append(f"[{ws.title}]\n" + '\n'.join(rows))
                wb.close()
                return '\n\n'.join(sheets)
            except ImportError:
                return "[需要安装openpyxl: pip install openpyxl]"
        elif ext == '.pdf':
            try:
                import PyPDF2
                reader = PyPDF2.PdfReader(filepath)
                pages = []
                for page in reader.pages:
                    t = page.extract_text()
                    if t: pages.append(t)
                return '\n\n'.join(pages)
            except ImportError:
                return "[需要安装PyPDF2: pip install PyPDF2]"
        else:
            return None
    except Exception as e:
        logger.warning(f"Extract text error for {ext}: {e}")
        return None
