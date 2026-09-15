# -*- coding: utf-8 -*-
"""分析统计路由 - /api/audit-log/* + /api/stats/*"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional, List

import os, json, datetime, collections

from backend.services.project_service import state
from backend.api_models import err, ErrorCode


# ═══════════════════════════════════════════════════════════════════
# 事件审计链路由 - /api/audit-log/*  (原 audit_log.py)
# ═══════════════════════════════════════════════════════════════════
audit_log_router = APIRouter(prefix="/api/audit-log")


# -- 内部工具 --
def _log_path() -> Optional[str]:
    """获取当前项目的审计日志文件路径"""
    if not state.project:
        return None
    return os.path.join(state.project.project_dir, "audit_log.json")


def _load_logs() -> List[dict]:
    """读取全部审计日志（按时间倒序）"""
    path = _log_path()
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def _save_logs(logs: List[dict]):
    """保存审计日志到文件"""
    path = _log_path()
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class AuditEvent(BaseModel):
    """审计事件模型"""
    action: str                 # 事件类型：generate / save / deai / continue / export 等
    target: str = ""            # 操作目标：章节名/项目名等
    detail: str = ""            # 详细描述


@audit_log_router.post("/log")
def add_log(ev: AuditEvent):
    """记录一条审计事件"""
    logs = _load_logs()
    record = {
        "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": ev.action,
        "target": ev.target,
        "detail": ev.detail,
    }
    # 插入到头部（最新在前），上限保留 1000 条避免文件过大
    logs.insert(0, record)
    if len(logs) > 1000:
        logs = logs[:1000]
    _save_logs(logs)
    return {"ok": True, "record": record}


@audit_log_router.get("/list")
def list_logs(limit: int = Query(50, ge=1, le=1000)):
    """获取审计日志列表（默认最近50条）"""
    logs = _load_logs()
    return {"ok": True, "logs": logs[:limit], "total": len(logs)}


@audit_log_router.get("/stats")
def log_stats():
    """按 action 类型分组统计"""
    logs = _load_logs()
    stats = {}
    for item in logs:
        act = item.get("action", "unknown")
        stats[act] = stats.get(act, 0) + 1
    return {"ok": True, "stats": stats, "total": len(logs)}


# ═══════════════════════════════════════════════════════════════════
# 写作统计路由 - /api/stats/*  (原 stats.py)
# ═══════════════════════════════════════════════════════════════════
stats_router = APIRouter(prefix="/api/stats")


# -- 内部工具 --
def _stats_path() -> Optional[str]:
    if not state.project:
        return None
    return os.path.join(state.project.project_dir, "writing_stats.json")


def _load_stats() -> dict:
    path = _stats_path()
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_stats(stats: dict):
    path = _stats_path()
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _backfill_from_project() -> dict:
    """从 project.json 的 chapters 数据回填统计（用 modified 时间戳和 word_count 估算）"""
    if not state.project:
        return {}
    stats = {}
    for i, ch in enumerate(state.project.chapters):
        wc = ch.get("word_count", 0)
        modified = ch.get("modified", "")
        if not modified or wc <= 0:
            continue
        # modified 格式："YYYY-MM-DD HH:MM"
        date_str = modified.split(" ")[0]
        try:
            datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        day = stats.setdefault(date_str, {"words_added": 0, "words_total": 0, "chapters_touched": []})
        day["words_added"] += wc
        if i not in day["chapters_touched"]:
            day["chapters_touched"].append(i)
    # 重新计算每天的 words_total：按日期排序后累计
    cumulative = 0
    for date_str in sorted(stats.keys()):
        cumulative += stats[date_str]["words_added"]
        stats[date_str]["words_total"] = cumulative
    return stats


def _ensure_stats() -> dict:
    """加载统计；若文件不存在则从项目数据回填并持久化"""
    path = _stats_path()
    if not path:
        return {}
    if not os.path.exists(path):
        stats = _backfill_from_project()
        if stats:
            _save_stats(stats)
        return stats
    return _load_stats()


# ═══════════════════════════════════════════════════════════════════
# 每日统计
# ═══════════════════════════════════════════════════════════════════

@stats_router.get("/daily")
def stats_daily(range_days: int = Query(30, alias="range")):
    """返回近 N 天每日字数数组"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "未打开项目")
    stats = _ensure_stats()
    today = datetime.date.today()
    data = []
    for i in range(range_days):
        d = today - datetime.timedelta(days=range_days - 1 - i)
        ds = d.strftime("%Y-%m-%d")
        day = stats.get(ds, {})
        data.append({
            "date": ds,
            "words_added": day.get("words_added", 0),
            "words_total": day.get("words_total", 0),
        })
    return {"ok": True, "data": data}


# ═══════════════════════════════════════════════════════════════════
# 周统计
# ═══════════════════════════════════════════════════════════════════

@stats_router.get("/weekly")
def stats_weekly():
    """聚合为周统计（以周一为起点）"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "未打开项目")
    stats = _ensure_stats()
    weekly = collections.OrderedDict()
    for date_str, day in sorted(stats.items()):
        try:
            d = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        monday = d - datetime.timedelta(days=d.weekday())
        key = monday.strftime("%Y-%m-%d")
        w = weekly.setdefault(key, {"week_start": key, "words_added": 0, "days": 0})
        w["words_added"] += day.get("words_added", 0)
        w["days"] += 1
    data = []
    for w in weekly.values():
        data.append({
            "week_start": w["week_start"],
            "words_added": w["words_added"],
            "avg_daily": round(w["words_added"] / w["days"], 1) if w["days"] else 0,
        })
    return {"ok": True, "data": data}


# ═══════════════════════════════════════════════════════════════════
# 月统计
# ═══════════════════════════════════════════════════════════════════

@stats_router.get("/monthly")
def stats_monthly():
    """聚合为月统计"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "未打开项目")
    stats = _ensure_stats()
    monthly = collections.OrderedDict()
    for date_str, day in sorted(stats.items()):
        try:
            d = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        key = d.strftime("%Y-%m")
        m = monthly.setdefault(key, {"month": key, "words_added": 0, "days": 0})
        m["words_added"] += day.get("words_added", 0)
        m["days"] += 1
    data = []
    for m in monthly.values():
        data.append({
            "month": m["month"],
            "words_added": m["words_added"],
            "avg_daily": round(m["words_added"] / m["days"], 1) if m["days"] else 0,
        })
    return {"ok": True, "data": data}


# ═══════════════════════════════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════════════════════════════

@stats_router.get("/summary")
def stats_summary():
    """返回写作汇总：总字数/章节数/平均每章字数/写作天数/最佳一天/连续天数"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "未打开项目")
    stats = _ensure_stats()

    total_words = sum(ch.get("word_count", 0) for ch in state.project.chapters)
    total_chapters = len(state.project.chapters)
    avg_chapter_words = round(total_words / total_chapters) if total_chapters else 0
    writing_days = len(stats)

    # 最佳一天（words_added 最大）
    best_day = {"date": "", "words": 0}
    for date_str, day in stats.items():
        wa = day.get("words_added", 0)
        if wa > best_day["words"]:
            best_day = {"date": date_str, "words": wa}

    # 连续写作天数（从今天/昨天往前数）
    streak_days = 0
    if stats:
        today = datetime.date.today()
        d = today
        if d.strftime("%Y-%m-%d") not in stats:
            d = d - datetime.timedelta(days=1)  # 今天还没写则从昨天起算
        while d.strftime("%Y-%m-%d") in stats:
            streak_days += 1
            d = d - datetime.timedelta(days=1)

    return {
        "ok": True,
        "total_words": total_words,
        "total_chapters": total_chapters,
        "avg_chapter_words": avg_chapter_words,
        "writing_days": writing_days,
        "best_day": best_day,
        "streak_days": streak_days,
    }


# ═══════════════════════════════════════════════════════════════════
# Token 用量统计（第5批：对接 ai_client.usage_log / ai_usage.json）
# ═══════════════════════════════════════════════════════════════════

def _usage_path() -> Optional[str]:
    """ai_usage.json 位于 data/ 目录（与 ai_config.json 同级）"""
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "data")
    return os.path.join(base, "ai_usage.json")


def _load_usage_log() -> List[dict]:
    path = _usage_path()
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


@stats_router.get("/usage")
def stats_usage(days: int = Query(7, ge=1, le=90), group_by: str = Query("day")):
    """Token 用量统计：按天/按任务类型/按模型聚合。

    Args:
        days: 回溯天数（默认 7）
        group_by: day / task_type / model / provider

    Returns:
        total_calls / total_tokens / total_cost_cny / data / recent
    """
    log = _load_usage_log()
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    recent = []
    for e in log:
        ts = e.get("timestamp", "")
        if ts[:10] >= cutoff_str:
            recent.append(e)

    agg = collections.defaultdict(lambda: {
        "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
        "total_tokens": 0, "cost_cny": 0.0,
    })
    for e in recent:
        key = {
            "day": e.get("timestamp", "")[:10],
            "task_type": e.get("task_type", "general"),
            "model": e.get("model", "unknown"),
            "provider": e.get("provider", "unknown"),
        }.get(group_by, e.get("timestamp", "")[:10])
        a = agg[key]
        a["calls"] += 1
        a["prompt_tokens"] += e.get("prompt_tokens", 0)
        a["completion_tokens"] += e.get("completion_tokens", 0)
        a["total_tokens"] += e.get("total_tokens", 0)
        a["cost_cny"] += e.get("cost_cny", 0.0)

    data = []
    for key in sorted(agg.keys()):
        a = agg[key]
        data.append({
            "key": key,
            **a,
            "cost_cny": round(a["cost_cny"], 4),
        })

    total = {
        "calls": sum(a["calls"] for a in agg.values()),
        "prompt_tokens": sum(a["prompt_tokens"] for a in agg.values()),
        "completion_tokens": sum(a["completion_tokens"] for a in agg.values()),
        "total_tokens": sum(a["total_tokens"] for a in agg.values()),
        "cost_cny": round(sum(a["cost_cny"] for a in agg.values()), 4),
    }
    return {
        "ok": True,
        "group_by": group_by,
        "days": days,
        "total": total,
        "data": data,
        "recent": recent[-20:][::-1],
    }


# ═══════════════════════════════════════════════════════════════════
# 上下文透视（第5批：对接 context_inspector）
# ═══════════════════════════════════════════════════════════════════

@stats_router.get("/context")
def stats_context(limit: int = Query(50, ge=1, le=200)):
    """获取最近 AI 调用的上下文结构快照（透视面板数据源）"""
    from backend.services.context_inspector import get_recent
    records = get_recent(limit=limit)
    return {"ok": True, "total": len(records), "records": records}


@stats_router.get("/context/summary")
def stats_context_summary(days: int = Query(7, ge=1, le=90)):
    """上下文透视聚合：来源分布 / 任务类型分布 / 平均 prompt token"""
    from backend.services.context_inspector import get_summary
    return get_summary(days=days)


# ═══════════════════════════════════════════════════════════════════
# 模型元数据注册表（第5批：真实窗口 / 思考档位 / 输出预算 透明化）
# ═══════════════════════════════════════════════════════════════════

@stats_router.get("/models")
def stats_models():
    """返回模型注册表概览：provider / model / 真实上下文窗口 / 思考档位 / 输出预算"""
    from backend.services.model_registry import get_registry_overview
    return {"ok": True, "models": get_registry_overview()}


@stats_router.get("/models/{provider}")
def stats_models_provider(provider: str):
    """查询指定 provider 的模型清单与元数据"""
    from backend.services.model_registry import get_provider_models
    data = get_provider_models(provider)
    if data is None:
        return err(ErrorCode.NOT_FOUND, f"未知 provider: {provider}")
    return {"ok": True, "provider": provider, "models": data}
