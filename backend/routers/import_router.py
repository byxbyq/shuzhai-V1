# -*- coding: utf-8 -*-
"""逆向导入路由 - /api/import/*
将已有小说反向解析为标准项目结构。自研 story-import 逻辑。
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
import re

from backend.services.project_service import create_project
from backend.api_models import err, ErrorCode

router = APIRouter(prefix="/api/import")


class ImportRequest(BaseModel):
    title: str = ""
    chapters: List[str] = []  # 按章分隔的文本列表
    auto_split: bool = True  # 如果传单个长文本，自动按章分割
    raw_text: str = ""  # 单个长文本（auto_split=True时使用）
    split_pattern: str = ""  # 自定义分割正则


class ImportResult(BaseModel):
    project_dir: str = ""
    chapter_count: int = 0
    extracted_characters: List[str] = []
    extracted_outline: str = ""
    warnings: List[str] = []


@router.post("/novel")
def import_novel(data: ImportRequest):
    """逆向导入已有小说 — 自动分章+提取角色+生成摘要大纲"""
    if not data.chapters and not data.raw_text:
        return err(ErrorCode.VALIDATION_ERROR, "缺少chapters或raw_text")

    # 1. 分章
    chapters = data.chapters
    if not chapters and data.raw_text and data.auto_split:
        # 默认按"第X章"分割
        pattern = data.split_pattern or r'第[一二三四五六七八九十百千零\d]+章[^\n]*'
        parts = re.split(pattern, data.raw_text)
        # 去掉第一个空串（分割符前的内容）
        chapters = [p.strip() for p in parts if p.strip()]
        if len(chapters) < 2:
            # 尝试按连续换行分割
            chapters = [p.strip() for p in data.raw_text.split('\n\n') if len(p.strip()) > 500]

    if not chapters:
        return err(ErrorCode.IMPORT_FAILED, "无法自动分章，请手动提供chapters列表")

    # 2. 创建项目
    title = data.title or f"导入小说_{len(chapters)}章"
    proj = create_project(title, "", len(chapters))

    # 3. 写入正文
    for i, content in enumerate(chapters):
        if i < len(proj.chapters):
            try:
                proj.set_content(content.strip(), i)
            except Exception:
                pass

    # 4. 提取角色名（简单启发式：频繁出现的2-4字人名）
    all_text = "\n".join(chapters[:10])  # 取前10章提取
    char_candidates = {}
    # 匹配引号内对话的说话人
    dialogue_pattern = r'([""「」『』])([^""「」『』]{2,4})[说道问答喊叫笑道怒道]'
    for m in re.finditer(dialogue_pattern, all_text):
        name = m.group(2)
        if 2 <= len(name) <= 4 and not any(c in name for c in '的了着过是有人在'):
            char_candidates[name] = char_candidates.get(name, 0) + 1
    extracted_chars = sorted([n for n, c in char_candidates.items() if c >= 3])[:20]

    # 写入人物档案
    if extracted_chars:
        proj.characters = [{"name": n, "role": "待补充"} for n in extracted_chars]

    # 5. 生成简要大纲（取每章前100字作为摘要）
    outline_parts = []
    for i, content in enumerate(chapters):
        summary = content[:100].replace('\n', ' ').strip()
        outline_parts.append(f"第{i+1}章: {summary}...")
    outline_text = "\n".join(outline_parts)
    try:
        proj.save_outline_text(outline_text)
    except Exception:
        pass

    # 6. 保存
    proj.save_all()

    return {
        "ok": True,
        "project_dir": proj.project_dir,
        "title": title,
        "chapter_count": len(chapters),
        "extracted_characters": extracted_chars,
        "outline_preview": outline_text[:500],
        "warnings": [] if len(chapters) >= 3 else ["分章数较少，建议检查分章结果"]
    }


@router.post("/extract-characters")
def extract_characters(data: dict):
    """从文本中提取候选角色名（零Token纯规则）"""
    text = data.get("text", "")
    if not text:
        return err(ErrorCode.VALIDATION_ERROR, "缺少text")

    # 对话标签提取
    dialogue_pattern = r'([""「」『』])([^""「」『』]{2,4})[说道问答喊叫笑道怒道冷道低声道]'
    candidates = {}
    for m in re.finditer(dialogue_pattern, text):
        name = m.group(2)
        if 2 <= len(name) <= 4 and not any(c in name for c in '的了着过是有人在和与'):
            candidates[name] = candidates.get(name, 0) + 1

    # 高频2-4字词组提取（补充）
    word_pattern = r'[\u4e00-\u9fa5]{2,3}(?:说|道|想|看|笑|走|来|去|站|坐|转)'
    for m in re.finditer(word_pattern, text):
        word = m.group()
        name = word[:-1]  # 去掉动词
        if 2 <= len(name) <= 4:
            candidates[name] = candidates.get(name, 0) + 1

    result = sorted(candidates.items(), key=lambda x: -x[1])[:30]
    return {
        "ok": True,
        "characters": [{"name": n, "count": c} for n, c in result],
        "total_candidates": len(candidates)
    }
