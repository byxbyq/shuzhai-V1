# -*- coding: utf-8 -*-
"""上下文透视（Context Inspector）— 书斋自研上下文透视面板

核心职责：
  - 记录每次 AI 调用的 prompt 结构快照：注入的块（章节标题行识别）、
    估计 token、来源标记（如 story_world / chapter / outline）
  - 持久化到 data/context_inspection.json，供前端面板展示
  - 提供查询接口：最近调用 / 按任务类型 / 按注入来源聚合

设计要点：
  - 零侵入：在 ai_client.generate() 入口处调用 capture() 即可
  - 块识别：以 Markdown 标题行（# / ## / ###）与常见分隔符划分 prompt 段落
  - 来源标记：调用方可传 meta["ctx_sources"]=[...] 显式标注注入来源，
    未标注时自动按段落标题推断
"""

from __future__ import annotations

import json
import os
import time
import logging
import threading
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_MAX_RECORDS = 500


def _inspection_path() -> str:
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "data")
    return os.path.join(base, "context_inspection.json")


def _load_records() -> List[dict]:
    path = _inspection_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_records(records: List[dict]):
    path = _inspection_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"保存上下文透视失败: {e}")


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数（与 model_registry.estimate_prompt_tokens 一致）"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return int(cjk * 0.6 + other * 0.25)


def _split_blocks(prompt: str) -> List[dict]:
    """将 prompt 按 Markdown 标题/分隔线划分为结构块。

    Returns:
        [{"title": str, "chars": int, "tokens_est": int, "lines": int}, ...]
    """
    if not prompt:
        return []
    lines = prompt.split("\n")
    blocks: List[dict] = []
    current_title = "(prompt 开头)"
    current_lines: List[str] = []

    def flush():
        if not current_lines:
            return
        text = "\n".join(current_lines)
        blocks.append({
            "title": current_title,
            "chars": len(text),
            "tokens_est": _estimate_tokens(text),
            "lines": len(current_lines),
        })

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("【") or \
           (stripped and set(stripped) <= {"-", "=", "_"} and len(stripped) >= 3):
            flush()
            current_title = stripped.strip("#").strip() or "(分隔线)"
            current_lines = []
        else:
            current_lines.append(line)
    flush()
    return blocks


_SOURCE_KEYWORDS = {
    "世界观": "world",
    "设定": "world",
    "人物": "character",
    "角色": "character",
    "大纲": "outline",
    "剧情": "plot",
    "章节": "chapter",
    "正文": "chapter",
    "分镜": "storyboard",
    "提示": "prompt",
    "技法": "technique",
    "纪律": "discipline",
    "回写": "rewrite",
    "承诺": "commitment",
    "示例": "example",
    "对话": "chat",
}


def _infer_sources(blocks: List[dict]) -> List[str]:
    """根据块标题推断注入来源（去重保序）"""
    sources: List[str] = []
    for b in blocks:
        title = b.get("title", "")
        for kw, src in _SOURCE_KEYWORDS.items():
            if kw in title and src not in sources:
                sources.append(src)
                break
    return sources


def capture(prompt: str, task: str = "", task_type: str = "general",
            provider: str = "", model: str = "", meta: Optional[dict] = None) -> dict:
    """记录一次 AI 调用的上下文结构快照。

    Args:
        prompt: 注入给 AI 的完整 prompt
        task: 任务描述
        task_type: 任务类型
        provider / model: 模型信息
        meta: 可选；meta["ctx_sources"] 显式标注注入来源

    Returns:
        本次记录 dict（已持久化）
    """
    try:
        blocks = _split_blocks(prompt)
        meta = meta or {}
        explicit_sources = meta.get("ctx_sources") or []
        sources = list(explicit_sources) if explicit_sources else _infer_sources(blocks)
        total_tokens = sum(b["tokens_est"] for b in blocks)
        record = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "task": task,
            "task_type": task_type,
            "provider": provider,
            "model": model,
            "prompt_chars": len(prompt),
            "prompt_tokens_est": total_tokens,
            "block_count": len(blocks),
            "blocks": blocks[:20],          # 最多保留前 20 块，避免文件过大
            "sources": sources,
        }
        with _lock:
            records = _load_records()
            records.insert(0, record)
            if len(records) > _MAX_RECORDS:
                records = records[:_MAX_RECORDS]
            _save_records(records)
        return record
    except Exception as e:
        logger.debug(f"上下文透视捕获失败: {e}")
        return {}


def get_recent(limit: int = 50) -> List[dict]:
    """获取最近 N 条透视记录"""
    return _load_records()[:limit]


def get_summary(days: int = 7) -> dict:
    """聚合统计：总调用 / 平均 prompt token / 来源分布 / 任务类型分布"""
    records = _load_records()
    if not records:
        return {"ok": True, "total": 0, "data": []}

    cutoff = time.time() - days * 86400
    recent = []
    for r in records:
        try:
            ts = time.mktime(time.strptime(r.get("timestamp", ""), "%Y-%m-%d %H:%M:%S"))
        except Exception:
            ts = time.time()
        if ts >= cutoff:
            recent.append(r)

    source_dist: Dict[str, int] = {}
    task_dist: Dict[str, int] = {}
    total_tokens = 0
    for r in recent:
        total_tokens += r.get("prompt_tokens_est", 0)
        for s in r.get("sources", []):
            source_dist[s] = source_dist.get(s, 0) + 1
        tt = r.get("task_type", "general")
        task_dist[tt] = task_dist.get(tt, 0) + 1

    return {
        "ok": True,
        "total": len(recent),
        "total_prompt_tokens_est": total_tokens,
        "avg_prompt_tokens_est": round(total_tokens / len(recent)) if recent else 0,
        "source_dist": source_dist,
        "task_type_dist": task_dist,
    }
