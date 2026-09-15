# -*- coding: utf-8 -*-
"""章节记忆蒸馏路由 - /api/distill/*

将用户已写的章节蒸馏为结构化记忆单元，存储在当前小说项目目录下的 distilled/ 子目录。
这些记忆单元将在后续生成新章节时注入 AI prompt，替代原文灌入，实现约10倍上下文压缩。

提供的 API：
- POST /api/distill/chapters  蒸馏指定章节，生成结构化记忆
- GET  /api/distill/memory    读取当前项目的全部蒸馏记忆
- GET  /api/distill/status    返回各章节的蒸馏状态
"""
import os
import json
import re
import time
import logging
from typing import List, Dict, Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.project_service import state
from backend.ai_client import AIClient
from backend.api_models import err, ErrorCode
from backend.task_manager import task_manager

logger = logging.getLogger(__name__)

# 路由前缀设为 /api/distill，与项目中其他 router 风格一致
router = APIRouter(prefix="/api/distill", tags=["distill"])

# ═══════════════════════════════════════════
# 提取器配置表
# key -> (提取器prompt文件名, 输出json文件名, 中文标签, 是否启用)
# 改造后：
# - character / plot / foreshadowing / relationship 由 state_memory 替代（enabled=False）
# - worldbuilding / writing_technique 保留（AI 跨章合成，enabled=True）
# ═══════════════════════════════════════════
EXTRACTORS: Dict[str, Dict[str, Any]] = {
    "character": {
        "prompt": "character-state-extractor.md",
        "output": "character-states.json",
        "label": "人物状态",
        "enabled": False,  # 由 state_memory 替代
    },
    "plot": {
        "prompt": "plot-progress-extractor.md",
        "output": "plot-progress.json",
        "label": "情节进度",
        "enabled": False,  # 由 state_memory 替代
    },
    "foreshadowing": {
        "prompt": "foreshadowing-tracker.md",
        "output": "foreshadowing.json",
        "label": "伏笔追踪",
        "enabled": False,  # 由 state_memory 替代
    },
    "worldbuilding": {
        "prompt": "worldbuilding-snapshot.md",
        "output": "worldbuilding.json",
        "label": "世界观",
        "enabled": True,   # AI 跨章合成，保留
    },
    "relationship": {
        "prompt": "relationship-mapper.md",
        "output": "relationships.json",
        "label": "关系图谱",
        "enabled": False,  # 由 Ledger 替代
    },
    "writing_technique": {
        "prompt": "writing-technique-extractor.md",
        "output": "writing-techniques.json",
        "label": "写作技法",
        "enabled": True,   # AI 跨章合成，保留
    },
}

# 提取器 prompt 模板所在目录：backend/distill_extractors/
_EXTRACTOR_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "distill_extractors",
)


# ═══════════════════════════════════════════
# 请求模型
# ═══════════════════════════════════════════
class DistillRequest(BaseModel):
    """蒸馏请求体"""
    chapter_indices: List[int]                          # 要蒸馏的章节索引（0-based）
    options: Dict[str, Any] = {}                        # 选项，含 extractors 列表


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════
def _get_distilled_dir() -> Optional[str]:
    """获取当前项目的蒸馏记忆目录路径，不存在则创建。
    记忆文件存储在 项目目录/distilled/ 下。
    """
    if not state.project:
        return None
    d = os.path.join(state.project.project_dir, "distilled")
    os.makedirs(d, exist_ok=True)
    return d


def _load_extractor_prompt(prompt_file: str) -> str:
    """加载提取器 prompt 模板内容"""
    path = os.path.join(_EXTRACTOR_DIR, prompt_file)
    if not os.path.exists(path):
        logger.warning("提取器 prompt 文件不存在: %s", path)
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _build_chapters_text(chapter_indices: List[int]) -> str:
    """加载指定章节的内容，按顺序拼接成带标题的文本块。

    chapter_indices 为 0-based 索引，与 state.project.get_content(idx) 一致。
    """
    if not state.project:
        return ""
    parts: List[str] = []
    chapters = state.project.chapters or []
    for idx in chapter_indices:
        if 0 <= idx < len(chapters):
            ch = chapters[idx]
            title = ch.get("title", "第%d章" % (idx + 1))
            content = state.project.get_content(idx) or ""
            if content.strip():
                parts.append("### %s（第%d章）\n\n%s" % (title, idx + 1, content))
            else:
                # 空章节也标注一下，便于排查
                parts.append("### %s（第%d章）\n\n（本章无内容）" % (title, idx + 1))
    return "\n\n".join(parts)


def _parse_json_response(raw: str) -> Any:
    """从 AI 返回文本中解析 JSON。

    支持以下情况：
    1. ```json 代码块包裹（闭合）
    2. ```json 代码块未闭合（被截断）
    3. 裸 JSON 字符串
    4. 文本中混有前后说明文字，需提取首个 [/{ 到末尾 ]/}
    5. 尾随逗号等常见格式问题
    """
    if not raw:
        return None

    # 1. 闭合的 ```json 代码块
    m = re.search(r"```json\s*\n(.*?)\n```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 2. 未闭合的 ```json 代码块（AI 返回被截断时）
    m = re.search(r"```json\s*\n([\s\S]+)", raw)
    if m:
        candidate = m.group(1).rstrip("`").rstrip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 3. 直接解析整段文本
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 4. 提取首个 [ 到末尾 ] 或首个 { 到末尾 }
    for open_ch, close_ch in (("[", "]"), ("{", "}")):
        start = raw.find(open_ch)
        end = raw.rfind(close_ch)
        if start >= 0 and end > start:
            json_str = raw[start:end + 1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # 5. 尝试修复尾随逗号
                try:
                    fixed = re.sub(r",\s*([}\]])", r"\1", json_str)
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    continue

    return None


def _run_extractor(extractor_key: str, chapters_text: str) -> Optional[Any]:
    """运行单个提取器：加载 prompt 模板 → 拼接章节内容 → 调用 AI → 解析 JSON。

    返回解析后的 JSON 数据，失败返回 None。
    使用 AIClient.generate_for_task 并指定 task_type="summary"（摘要/提取任务），
    以自动选择合适的模型并采用较低温度保证输出稳定。
    """
    cfg = EXTRACTORS.get(extractor_key)
    if not cfg:
        logger.warning("未知提取器: %s", extractor_key)
        return None

    template = _load_extractor_prompt(cfg["prompt"])
    if not template:
        return None

    # 构建 prompt：模板 + 待分析章节内容 + 输出要求
    prompt = (
        "%s\n\n"
        "## 待分析的章节内容\n\n%s\n\n"
        "请严格按照上述 JSON 格式输出，只返回 JSON，不要任何额外解释文字。"
        % (template, chapters_text)
    )

    # 使用项目已配置的 AI 客户端调用（与 generator.py 中 self.ai 一致）
    ai = AIClient()
    # 蒸馏属于摘要/提取任务，用 summary 任务类型选模型；低温保证结构化输出稳定
    raw = ai.generate_for_task(prompt, task_type="summary", temperature=0.3, max_tokens=4096)

    if not raw or raw.startswith("[生成失败") or raw.startswith("[错误"):
        logger.warning("提取器 %s AI 调用失败: %s", extractor_key, (raw or "")[:200])
        return None

    return _parse_json_response(raw)


def _count_items(data: Any) -> int:
    """统计提取出的记忆单元数量。
    - 列表：元素个数
    - 字典：所有列表/字典子项数量之和
    - 其他：1
    """
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        total = 0
        for v in data.values():
            if isinstance(v, list):
                total += len(v)
            elif isinstance(v, dict):
                total += len(v)
            else:
                total += 1
        return total
    return 0


def _read_meta(distilled_dir: str) -> Dict[str, Any]:
    """读取蒸馏元信息 meta.json"""
    meta_path = os.path.join(distilled_dir, "meta.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _write_meta(distilled_dir: str, meta: Dict[str, Any]):
    """写入蒸馏元信息 meta.json"""
    meta_path = os.path.join(distilled_dir, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════
# API 路由
# ═══════════════════════════════════════════
@router.post("/chapters")
def distill_chapters(data: DistillRequest):
    """蒸馏指定章节，生成结构化记忆单元。

    请求体：
        {
            "chapter_indices": [0, 1, 2],
            "options": {"extractors": ["character","plot","foreshadowing","worldbuilding","relationship"]}
        }

    流程：
        1. 加载指定章节内容并拼接
        2. 对每个提取器，构建 prompt 调用 AI
        3. 解析 AI 返回的 JSON
        4. 写入项目目录下 distilled/*.json（覆盖旧记忆）
        5. 更新 distilled/meta.json 记录已蒸馏章节

    返回：
        {"ok": true, "extracted": {"character": N, "plot": N, ...}}
    """
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    if not data.chapter_indices:
        return err(ErrorCode.VALIDATION_ERROR, "未指定要蒸馏的章节")

    # 确定要运行的提取器（默认启用全部）
    requested = (data.options or {}).get("extractors") or list(EXTRACTORS.keys())
    extractors_to_run = [k for k in requested if k in EXTRACTORS]
    if not extractors_to_run:
        return err(ErrorCode.VALIDATION_ERROR, "未指定有效的提取器")

    # 按 enabled 标志过滤：禁用的提取器不运行 AI
    # character/plot/foreshadowing/relationship 已由 state_memory/Ledger 替代
    skipped = []
    ai_extractors = []
    for key in extractors_to_run:
        cfg = EXTRACTORS[key]
        if not cfg.get("enabled", True):
            skipped.append(key)
        else:
            ai_extractors.append(key)

    # 加载并拼接指定章节内容
    chapters_text = _build_chapters_text(data.chapter_indices)
    # 检查是否有实际内容（排除"无内容"标注）
    real_content = re.sub(r"（本章无内容）", "", chapters_text).strip()

    # 如果有AI提取器需要运行，检查是否有内容
    if ai_extractors and not real_content:
        return err(ErrorCode.INTERNAL_ERROR, "指定章节均无内容，无法蒸馏")

    # 逐个运行启用的 AI 提取器
    distilled_dir = _get_distilled_dir()
    extracted: Dict[str, int] = {}
    for key in ai_extractors:
        cfg = EXTRACTORS[key]
        try:
            result = _run_extractor(key, chapters_text)
            if result is None:
                logger.warning("提取器 %s 未产出有效 JSON", key)
                extracted[key] = 0
                continue
            out_path = os.path.join(distilled_dir, cfg["output"])
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            extracted[key] = _count_items(result)
            logger.info("提取器 %s 完成，产出 %d 条记忆 -> %s",
                        key, extracted[key], cfg["output"])
        except Exception as e:
            logger.exception("提取器 %s 运行异常", key)
            extracted[key] = 0

    # 统计已自动同步的维度
    for key in skipped:
        cfg = EXTRACTORS[key]
        try:
            out_path = os.path.join(distilled_dir, cfg["output"])
            if os.path.exists(out_path):
                with open(out_path, "r", encoding="utf-8") as f:
                    data_skipped = json.load(f)
                extracted[key] = _count_items(data_skipped)
        except Exception:
            extracted[key] = 0

    # 更新蒸馏元信息：记录本次蒸馏的章节（覆盖之前记录）
    meta = _read_meta(distilled_dir)
    meta["distilled_chapters"] = sorted(set(data.chapter_indices))
    meta["last_distilled"] = time.strftime("%Y-%m-%d %H:%M:%S")
    meta["extractors"] = extractors_to_run
    meta["skipped_auto"] = skipped
    meta["ai_extracted"] = ai_extractors
    meta["project"] = state.project.meta.get("title", "")
    _write_meta(distilled_dir, meta)

    return {"ok": True, "extracted": extracted, "skipped": skipped, "ai_extracted": ai_extractors}


# ═══════════════════════════════════════════
# 后台蒸馏执行函数（供 TaskManager 调用）
# ═══════════════════════════════════════════
def _do_distill(
    info: Any,            # TaskInfo
    cancel_event: Any,    # threading.Event
    chapter_indices: List[int],
    options: Dict[str, Any],
):
    """后台线程中执行的蒸馏逻辑，与 distill_chapters() 流程一致但增加进度上报与取消令牌。"""
    # 确定要运行的提取器
    requested = options.get("extractors") or list(EXTRACTORS.keys())
    extractors_to_run = [k for k in requested if k in EXTRACTORS]

    skipped = []
    ai_extractors = []
    for key in extractors_to_run:
        cfg = EXTRACTORS[key]
        if not cfg.get("enabled", True):
            skipped.append(key)
        else:
            ai_extractors.append(key)

    # 加载章节内容
    chapters_text = _build_chapters_text(chapter_indices)
    real_content = re.sub(r"（本章无内容）", "", chapters_text).strip()

    if ai_extractors and not real_content:
        task_manager.update_progress(info.task_id, 100, "指定章节均无内容，无法蒸馏")
        return {"ok": False, "error": "指定章节均无内容，无法蒸馏"}

    total_ai = len(ai_extractors)
    distilled_dir = _get_distilled_dir()
    extracted: Dict[str, int] = {}

    for i, key in enumerate(ai_extractors):
        # 检查取消令牌
        if cancel_event.is_set():
            task_manager.update_progress(info.task_id, int((i / max(total_ai, 1)) * 100), "已取消")
            return {"ok": False, "cancelled": True, "extracted": extracted}

        cfg = EXTRACTORS[key]
        task_manager.update_progress(
            info.task_id,
            int((i / max(total_ai, 1)) * 100),
            f"正在提取 {cfg['label']}...",
        )

        try:
            result = _run_extractor(key, chapters_text)
            if result is None:
                extracted[key] = 0
                continue
            out_path = os.path.join(distilled_dir, cfg["output"])
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            extracted[key] = _count_items(result)
        except Exception as e:
            logger.exception("提取器 %s 运行异常", key)
            extracted[key] = 0

    # 统计已禁用的维度
    for key in skipped:
        cfg = EXTRACTORS[key]
        try:
            out_path = os.path.join(distilled_dir, cfg["output"])
            if os.path.exists(out_path):
                with open(out_path, "r", encoding="utf-8") as f:
                    data_skipped = json.load(f)
                extracted[key] = _count_items(data_skipped)
        except Exception:
            extracted[key] = 0

    # 更新蒸馏元信息
    meta = _read_meta(distilled_dir)
    meta["distilled_chapters"] = sorted(set(chapter_indices))
    meta["last_distilled"] = time.strftime("%Y-%m-%d %H:%M:%S")
    meta["extractors"] = extractors_to_run
    meta["skipped_auto"] = skipped
    meta["ai_extracted"] = ai_extractors
    meta["project"] = state.project.meta.get("title", "")
    _write_meta(distilled_dir, meta)

    task_manager.update_progress(info.task_id, 100, "蒸馏完成")
    return {"ok": True, "extracted": extracted, "skipped": skipped, "ai_extracted": ai_extractors}


# ═══════════════════════════════════════════
# 后台任务 API（异步模式）
# ═══════════════════════════════════════════

@router.post("/start")
def distill_start(data: DistillRequest):
    """启动后台蒸馏任务，立即返回 task_id"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    if not data.chapter_indices:
        return err(ErrorCode.VALIDATION_ERROR, "未指定要蒸馏的章节")

    task_id = task_manager.submit(
        "distill",
        _do_distill,
        chapter_indices=data.chapter_indices,
        options=data.options or {},
    )
    return {"ok": True, "task_id": task_id}


@router.get("/status/{task_id}")
def distill_status_get(task_id: str):
    """查询蒸馏任务进度"""
    info = task_manager.get_status(task_id)
    if info is None:
        return err(ErrorCode.VALIDATION_ERROR, "任务不存在或已过期")
    return {"ok": True, "task": info.to_dict()}


@router.post("/cancel/{task_id}")
def distill_cancel(task_id: str):
    """取消正在执行的蒸馏任务"""
    ok = task_manager.cancel(task_id)
    if not ok:
        return err(ErrorCode.VALIDATION_ERROR, "任务不存在或已完成，无法取消")
    return {"ok": True, "message": "已发送取消信号，任务将尽快停止"}


@router.get("/memory")
def get_memory():
    """读取当前项目的全部蒸馏记忆单元。

    改造后：
    - state_memory/*.json：每章蒸馏结果（5维结构化摘要）
    - distilled/ 2个AI合成文件：worldbuilding.json + writing-techniques.json
    - 聚合角色状态/伏笔/事件/新设定供前端展示

    返回：
        {
            "ok": true,
            "memory": {
                "state_memory": [{chapter_index, characters, events, ...}, ...],
                "worldbuilding": {...},
                "writing_technique": {...}
            },
            "aggregated": {
                "characters": [...],      # 滚动合并后的当前角色状态
                "pending_foreshadowing": [...],  # 未回收伏笔
                "chapter_count": N
            },
            "meta": {"distilled_chapters": [0,1,2], "last_distilled": "..."}
        }
    """
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")

    project_dir = state.project.project_dir

    # 1. 读取 state_memory 所有章节
    state_mem_dir = os.path.join(project_dir, "state_memory")
    state_files = []
    if os.path.isdir(state_mem_dir):
        for fname in sorted(os.listdir(state_mem_dir)):
            if not fname.endswith('.json') or fname.startswith('_'):
                continue
            path = os.path.join(state_mem_dir, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    state_files.append(json.load(f))
            except Exception:
                continue

    # 2. 读取 distilled 的 2 个 AI 合成文件
    distilled_dir = _get_distilled_dir()
    ai_memory: Dict[str, Any] = {}
    for key in ("worldbuilding", "writing_technique"):
        cfg = EXTRACTORS.get(key)
        if not cfg or not cfg.get("enabled"):
            continue
        path = os.path.join(distilled_dir, cfg["output"])
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    ai_memory[key] = json.load(f)
            except Exception:
                ai_memory[key] = None
        else:
            ai_memory[key] = None

    # 3. 聚合角色状态和未回收伏笔（供前端展示全貌）
    from backend.services.memory_synthesizer import (
        _aggregate_characters, _aggregate_foreshadowing
    )
    # state_files 已按文件名排序，但聚合需要按 chapter_index 排序
    state_files.sort(key=lambda x: x.get("chapter_index", 0))
    current_ch = max((sf.get("chapter_index", 0) for sf in state_files), default=0) + 1
    chars = _aggregate_characters(state_files)
    hooks = _aggregate_foreshadowing(state_files, current_ch)

    meta = _read_meta(distilled_dir)
    return {
        "ok": True,
        "memory": {
            "state_memory": state_files,
            **ai_memory,
        },
        "aggregated": {
            "characters": chars,
            "pending_foreshadowing": hooks,
            "chapter_count": len(state_files),
        },
        "meta": meta,
    }


@router.get("/status")
def distill_status():
    """返回当前项目的蒸馏状态：哪些章节已蒸馏、哪些未蒸馏。

    改造后：通过 state_memory/{NNN}.json 是否存在判断蒸馏状态。

    返回：
        {
            "ok": true,
            "chapters": [
                {"index": 0, "title": "第1章", "has_content": true, "word_count": 3000, "distilled": true},
                ...
            ],
            "distilled_count": 3,
            "total_count": 10,
            "last_distilled": "2026-07-07 12:00:00"
        }
    """
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")

    chapters = state.project.chapters or []
    project_dir = state.project.project_dir
    state_mem_dir = os.path.join(project_dir, "state_memory")

    # 检查 state_memory/ 下存在哪些章节文件
    distilled_set = set()
    if os.path.isdir(state_mem_dir):
        for fname in os.listdir(state_mem_dir):
            if not fname.endswith('.json') or fname.startswith('_'):
                continue
            try:
                idx = int(fname.replace('.json', ''))
                distilled_set.add(idx)
            except ValueError:
                continue

    # 保留 last_distilled 字段（从 distilled/meta.json 读取，兼容旧数据）
    distilled_dir = _get_distilled_dir()
    meta = _read_meta(distilled_dir)
    last_distilled = meta.get("last_distilled", "")

    result: List[Dict[str, Any]] = []
    for i, ch in enumerate(chapters):
        content = state.project.get_content(i) or ""
        has_content = len(content.strip()) > 0
        result.append({
            "index": i,
            "title": ch.get("title", "第%d章" % (i + 1)),
            "has_content": has_content,
            "word_count": len(content),
            "distilled": i in distilled_set,
        })

    distilled_count = sum(1 for r in result if r["distilled"])
    return {
        "ok": True,
        "chapters": result,
        "distilled_count": distilled_count,
        "total_count": len(result),
        "last_distilled": last_distilled,
    }
