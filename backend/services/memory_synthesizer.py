# -*- coding: utf-8 -*-
"""记忆合成器 - 从 state_memory 聚合生成上下文。

替代旧的 load_distilled_memory（读 distilled/*.json + 5000字符截断），
改为从 state_memory/*.json 分层压缩聚合，无硬上限，总字符数与章节数解耦。

数据来源：
- state_memory/*.json → 角色状态（滚动合并）+ 近期事件（分层）+ 未回收伏笔
- distilled/worldbuilding.json + writing-techniques.json → AI 跨章合成（保留）
- truth_ledger.json → 关系图谱 + 道具/势力（结构化数据）
"""
import os
import json
import logging
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 内存缓存（按 project_dir 键控）
# ═══════════════════════════════════════════
_state_memory_cache: Dict[str, Dict] = {}
# {
#   project_dir: {
#       "mtime": 目录最新修改时间,
#       "count": 文件数量,
#       "items": [已加载的items列表]
#   }
# }


def _get_cache_key(project_dir: str) -> str:
    return os.path.abspath(project_dir)


def _is_cache_valid(project_dir: str) -> bool:
    """检查缓存是否有效：目录存在且文件数量/最新mtime未变；
    目录不存在但缓存也是空的也算有效（项目还没开始写）"""
    key = _get_cache_key(project_dir)
    if key not in _state_memory_cache:
        return False
    cache = _state_memory_cache[key]
    mem_dir = os.path.join(project_dir, "state_memory")
    if not os.path.isdir(mem_dir):
        # 目录不存在，只有当缓存也是空的（count=0）时才算有效
        return cache["count"] == 0
    try:
        files = [f for f in os.listdir(mem_dir) if f.endswith('.json') and not f.startswith('_')]
        if len(files) != cache["count"]:
            return False
        # 检查最新文件的mtime
        latest_mtime = 0
        for f in files:
            fpath = os.path.join(mem_dir, f)
            try:
                mt = os.path.getmtime(fpath)
                if mt > latest_mtime:
                    latest_mtime = mt
            except OSError:
                pass
        return latest_mtime <= cache["mtime"]
    except OSError:
        return False


def _invalidate_cache(project_dir: str):
    """使缓存失效（外部写入新文件后调用）"""
    key = _get_cache_key(project_dir)
    if key in _state_memory_cache:
        del _state_memory_cache[key]


# ═══════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════

# 近期事件分层窗口
RECENT_WINDOW = 5        # 近 5 章完整事件摘要
MID_WINDOW = 15           # 中程 15 章只保留标题+一句核心事件
# 远期不输出事件（已被角色状态和伏笔覆盖）

# new_settings 聚合窗口（近 20 章）
SETTINGS_WINDOW = 20

# Ledger 关系图谱最大条数
MAX_RELATIONS = 20


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def _load_state_memory_files(project_dir: str) -> List[Dict]:
    """加载 state_memory/ 目录下所有章节蒸馏 JSON，按章节序排序。
    带内存缓存：文件数量和最新mtime不变时直接返回缓存结果。

    返回：[{chapter_index, characters, events, foreshadowing, new_settings, bridge, ...}, ...]
    """
    key = _get_cache_key(project_dir)
    if _is_cache_valid(project_dir):
        return _state_memory_cache[key]["items"]

    mem_dir = os.path.join(project_dir, "state_memory")
    if not os.path.isdir(mem_dir):
        # 空目录也缓存（避免每次都扫一遍）
        _state_memory_cache[key] = {"mtime": 0, "count": 0, "items": []}
        return []

    items = []
    latest_mtime = 0
    file_count = 0
    for fname in os.listdir(mem_dir):
        if not fname.endswith('.json') or fname.startswith('_'):
            continue
        file_count += 1
        path = os.path.join(mem_dir, fname)
        try:
            mt = os.path.getmtime(path)
            if mt > latest_mtime:
                latest_mtime = mt
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "chapter_index" in data:
                items.append(data)
        except Exception as e:
            logger.warning("读取 state_memory 文件失败 %s: %s", fname, e)

    # 按章节序升序
    items.sort(key=lambda x: x.get("chapter_index", 0))

    # 写入缓存
    _state_memory_cache[key] = {
        "mtime": latest_mtime,
        "count": file_count,
        "items": items,
    }
    return items


def _load_distilled_ai_file(project_dir: str, filename: str) -> Optional[Dict]:
    """读取 distilled/ 下的 AI 合成文件（worldbuilding / writing-techniques）。"""
    path = os.path.join(project_dir, "distilled", filename)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("读取 AI 合成文件失败 %s: %s", filename, e)
        return None


def _load_ledger(project_dir: str) -> Optional[Dict]:
    """读取 truth_ledger.json。"""
    path = os.path.join(project_dir, "truth_ledger.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("读取 ledger 失败: %s", e)
        return None


# ═══════════════════════════════════════════
# 聚合算法
# ═══════════════════════════════════════════

def _aggregate_characters(state_files: List[Dict]) -> List[Dict]:
    """滚动合并角色状态：新章节覆盖变化字段，alive=false 移除。

    返回当前存活角色的全貌列表。
    """
    running: Dict[str, Dict] = {}

    for sf in state_files:
        chars = sf.get("characters", [])
        if not isinstance(chars, list):
            continue
        for c in chars:
            if not isinstance(c, dict):
                continue
            name = c.get("name", "").strip()
            if not name:
                continue
            alive = c.get("alive", True)
            if alive is False:
                # 死亡角色移除
                running.pop(name, None)
                continue
            # 已有角色：覆盖变化的字段；新角色：插入
            if name in running:
                running[name].update({k: v for k, v in c.items() if v})
            else:
                running[name] = dict(c)

    return list(running.values())


def _aggregate_foreshadowing(state_files: List[Dict], current_chapter: int) -> List[Dict]:
    """伏笔追踪：只输出 status == pending 的，过期标注。

    分层策略：
    - 近期 RECENT_WINDOW 章种下的伏笔：完整输出
    - 更早种下且未回收的伏笔：合并为一条 "早期遗留" 摘要（避免线性膨胀）

    返回 [{content, planted_chapter, expected_chapter, status, expired, is_summary}, ...]
    """
    hooks: Dict[str, Dict] = {}

    for sf in state_files:
        ch_idx = sf.get("chapter_index", 0)
        ff = sf.get("foreshadowing", {})
        if not isinstance(ff, dict):
            continue

        # 种下的伏笔
        for planted in ff.get("planted", []):
            if not isinstance(planted, dict):
                continue
            content = planted.get("content", "").strip()
            if not content:
                continue
            key = _foreshadow_key(content)
            hooks[key] = {
                "content": content,
                "planted_chapter": ch_idx,
                "expected_chapter": planted.get("expected_chapter", 0),
                "status": "pending",
            }

        # 回收的伏笔
        for resolved in ff.get("resolved", []):
            if not isinstance(resolved, dict):
                continue
            content = resolved.get("content", "").strip()
            if not content:
                continue
            key = _foreshadow_key(content)
            if key in hooks:
                hooks[key]["status"] = "resolved"
                hooks[key]["resolved_method"] = resolved.get("method", "")

    # 过滤 pending 并标注过期
    pending = []
    for h in hooks.values():
        if h.get("status") != "pending":
            continue
        expected = h.get("expected_chapter", 0)
        if expected and current_chapter > expected:
            h["expired"] = True
        else:
            h["expired"] = False
        pending.append(h)

    # 分层：近期详细 + 远期合并为摘要
    max_chapter = current_chapter - 1
    recent_start = max_chapter - RECENT_WINDOW + 1

    recent = []
    older_expired = 0
    older_pending = 0
    for h in pending:
        if h.get("planted_chapter", 0) >= recent_start:
            recent.append(h)
        else:
            if h.get("expired", False):
                older_expired += 1
            else:
                older_pending += 1

    # 过期优先（提醒 AI 回收）
    recent.sort(key=lambda x: (not x.get("expired", False), x.get("planted_chapter", 0)))

    # 把早期统计作为一个特殊条目附加在末尾
    if older_expired > 0 or older_pending > 0:
        summary_parts = []
        if older_expired:
            summary_parts.append(f"⚠️{older_expired}条已过期")
        if older_pending:
            summary_parts.append(f"{older_pending}条未到期")
        recent.append({
            "content": f"（早期遗留伏笔：{'，'.join(summary_parts)}，建议回顾 state_memory/* 详情）",
            "planted_chapter": -1,  # 标记为摘要
            "expected_chapter": 0,
            "status": "pending",
            "expired": older_expired > 0,
            "is_summary": True,
        })

    return recent


def _foreshadow_key(content: str) -> str:
    """伏笔内容匹配键：去空白+取前20字。"""
    return "".join(content.split())[:20]


def _aggregate_recent_events(state_files: List[Dict], current_chapter: int) -> Tuple[List[str], List[str]]:
    """分层聚合近期事件。

    返回 (recent_lines, mid_lines)：
    - recent_lines: 近 RECENT_WINDOW 章的完整事件 + to_next 衔接（倒序，最新在前）
    - mid_lines: 中程 MID_WINDOW 章的标题 + 一句核心事件（倒序）
    """
    recent_lines = []
    mid_lines = []

    if not state_files:
        return recent_lines, mid_lines

    # current_chapter 是 1-based 的待生成章节号，已定稿章节 < current_chapter
    max_chapter = current_chapter - 1
    if max_chapter < 0:
        max_chapter = 0

    recent_start = max_chapter - RECENT_WINDOW + 1
    mid_start = max_chapter - RECENT_WINDOW - MID_WINDOW + 1

    # 倒序遍历，让最新章节排在前面
    for sf in reversed(state_files):
        ch = sf.get("chapter_index", 0)
        events = sf.get("events", [])
        bridge = sf.get("bridge", {}) or {}

        if ch >= recent_start and ch <= max_chapter:
            # 近期：完整事件 + to_next
            ch_display = ch + 1  # 显示为 1-based
            if events:
                ev_text = "；".join(events) if isinstance(events, list) else str(events)
            else:
                ev_text = "（无核心事件）"
            line = f"第{ch_display}章 {ev_text}"
            to_next = bridge.get("to_next", "").strip()
            if to_next:
                line += f"\n  └ 留下：{to_next}"
            recent_lines.append(line)

        elif ch >= mid_start and ch < recent_start:
            # 中程：标题 + 一句核心事件
            ch_display = ch + 1
            if events and isinstance(events, list) and events:
                ev_text = events[0]  # 只取第一条
            else:
                ev_text = "（无）"
            mid_lines.append(f"第{ch_display}章 {ev_text}")

    return recent_lines, mid_lines


def _aggregate_new_settings(state_files: List[Dict], current_chapter: int) -> List[str]:
    """聚合近 SETTINGS_WINDOW 章的 new_settings，去重。"""
    seen = set()
    result = []
    start_ch = current_chapter - SETTINGS_WINDOW

    for sf in state_files:
        ch = sf.get("chapter_index", 0)
        if ch < start_ch:
            continue
        settings = sf.get("new_settings", [])
        if not isinstance(settings, list):
            continue
        for s in settings:
            if not isinstance(s, str) or not s.strip():
                continue
            s = s.strip()
            if s not in seen:
                seen.add(s)
                result.append(s)

    return result


# ═══════════════════════════════════════════
# 格式化
# ═══════════════════════════════════════════

def _format_character_section(chars: List[Dict]) -> str:
    """格式化角色状态段。"""
    if not chars:
        return ""

    lines = ["## 当前角色状态"]
    for c in chars:
        name = c.get("name", "?")
        location = c.get("location", "")
        mood = c.get("mood", "")
        realm = c.get("realm", "")
        items = c.get("items", []) or []
        items_str = "、".join(items) if isinstance(items, list) else str(items)

        parts = [name]
        if location: parts.append(f"位置:{location}")
        if realm: parts.append(f"境界:{realm}")
        if mood: parts.append(f"心绪:{mood}")
        if items_str: parts.append(f"持有:{items_str}")
        lines.append("- " + " | ".join(parts))

    return "\n".join(lines)


def _format_foreshadow_section(hooks: List[Dict]) -> str:
    """格式化伏笔段。"""
    if not hooks:
        return ""

    lines = ["## 未回收伏笔"]
    for h in hooks:
        # 摘要条目直接输出内容
        if h.get("is_summary"):
            lines.append(f"- {h.get('content', '')}")
            continue

        planted = h.get("planted_chapter", 0) + 1
        content = h.get("content", "")
        expected = h.get("expected_chapter", 0)
        expired = h.get("expired", False)

        tag = " ⚠️已过期" if expired else ""
        exp_str = f"(预计第{expected}章回收)" if expected else ""
        lines.append(f"- [第{planted}章种]{tag} {content} {exp_str}".rstrip())

    return "\n".join(lines)


def _format_events_section(recent_lines: List[str], mid_lines: List[str]) -> str:
    """格式化近期事件段。"""
    if not recent_lines and not mid_lines:
        return ""

    lines = ["## 近期事件"]
    if recent_lines:
        lines.append("### 最近章节（详细）")
        lines.extend(recent_lines)
    if mid_lines:
        lines.append("### 中期章节（简略）")
        lines.extend(mid_lines)

    return "\n".join(lines)


def _format_settings_section(settings: List[str]) -> str:
    """格式化新设定段。"""
    if not settings:
        return ""
    lines = ["## 近期新设定"]
    for s in settings:
        lines.append(f"- {s}")
    return "\n".join(lines)


def _format_ai_distilled_section(label: str, data) -> str:
    """格式化 AI 合成的 distilled 文件（worldbuilding / writing-techniques）。"""
    if not data:
        return ""

    # data 可能是 list 或 dict
    if isinstance(data, list):
        if not data:
            return ""
        text = json.dumps(data, ensure_ascii=False, indent=0)
    elif isinstance(data, dict):
        text = json.dumps(data, ensure_ascii=False, indent=0)
    else:
        text = str(data)

    # 限制单段长度（避免过长）
    if len(text) > 2000:
        text = text[:2000] + "\n...（已截断）"

    return f"## {label}\n{text}"


def _format_ledger_relations(ledger: Dict) -> str:
    """从 Ledger 读取关系图谱。"""
    relations = ledger.get("relationships", []) or ledger.get("relation_graph", [])
    if not relations:
        # 从 character_states 推断不出关系，返回空
        return ""
    if not isinstance(relations, list):
        return ""

    lines = ["## 关系图谱"]
    for r in relations[:MAX_RELATIONS]:
        if not isinstance(r, dict):
            continue
        a = r.get("character_a", "") or r.get("a", "")
        b = r.get("character_b", "") or r.get("b", "")
        rel = r.get("relation", "") or r.get("type", "")
        if a and b:
            lines.append(f"- {a} ↔ {b}：{rel}")

    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def _format_ledger_artifacts(ledger: Dict) -> str:
    """从 Ledger 读取道具/功法。"""
    artifacts = ledger.get("artifacts", {})
    if not artifacts:
        return ""
    if isinstance(artifacts, dict):
        items = list(artifacts.values())
    elif isinstance(artifacts, list):
        items = artifacts
    else:
        return ""

    if not items:
        return ""

    lines = ["## 道具/功法"]
    for a in items:
        if isinstance(a, dict):
            name = a.get("name", "?")
            desc = a.get("description", "") or a.get("desc", "")
            lines.append(f"- {name}：{desc}" if desc else f"- {name}")
        elif isinstance(a, str):
            lines.append(f"- {a}")

    return "\n".join(lines)


def _format_ledger_factions(ledger: Dict) -> str:
    """从 Ledger 读取势力/组织。"""
    factions = ledger.get("factions", {})
    if not factions:
        return ""
    if isinstance(factions, dict):
        items = list(factions.values())
    elif isinstance(factions, list):
        items = factions
    else:
        return ""

    if not items:
        return ""

    lines = ["## 势力/组织"]
    for f in items:
        if isinstance(f, dict):
            name = f.get("name", "?")
            desc = f.get("description", "") or f.get("desc", "")
            lines.append(f"- {name}：{desc}" if desc else f"- {name}")
        elif isinstance(f, str):
            lines.append(f"- {f}")

    return "\n".join(lines)


# ═══════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════

def synthesize_memory_context(project_dir: str, current_chapter: int) -> Optional[str]:
    """从 state_memory 聚合生成记忆上下文文本。

    替代旧的 load_distilled_memory，无硬字符上限，分层压缩。

    Args:
        project_dir: 项目根目录路径
        current_chapter: 待生成章节号（1-based，即将要写第几章）

    Returns:
        格式化后的记忆上下文文本；若无数据返回 None
    """
    # 1. 加载 state_memory 所有章节
    state_files = _load_state_memory_files(project_dir)

    # 2. 加载 distilled 的 2 个 AI 合成文件
    worldbuilding = _load_distilled_ai_file(project_dir, "worldbuilding.json")
    writing_tech = _load_distilled_ai_file(project_dir, "writing-techniques.json")

    # 3. 加载 Ledger（关系/道具/势力）
    ledger = _load_ledger(project_dir)

    # 如果三者全空，返回 None
    if not state_files and not worldbuilding and not writing_tech and not ledger:
        return None

    # ── 聚合 ──
    chars = _aggregate_characters(state_files)
    hooks = _aggregate_foreshadowing(state_files, current_chapter)
    recent_lines, mid_lines = _aggregate_recent_events(state_files, current_chapter)
    settings = _aggregate_new_settings(state_files, current_chapter)

    # ── 格式化 ──
    parts = []

    # 头部
    parts.append("## 前文记忆摘要（state_memory 聚合 + AI 合成）")

    # 角色
    sec = _format_character_section(chars)
    if sec:
        parts.append(sec)

    # 近期事件
    sec = _format_events_section(recent_lines, mid_lines)
    if sec:
        parts.append(sec)

    # 伏笔
    sec = _format_foreshadow_section(hooks)
    if sec:
        parts.append(sec)

    # 新设定
    sec = _format_settings_section(settings)
    if sec:
        parts.append(sec)

    # 关系图谱
    if ledger:
        sec = _format_ledger_relations(ledger)
        if sec:
            parts.append(sec)

        sec = _format_ledger_artifacts(ledger)
        if sec:
            parts.append(sec)

        sec = _format_ledger_factions(ledger)
        if sec:
            parts.append(sec)

    # AI 合成文件
    sec = _format_ai_distilled_section("世界观全貌", worldbuilding)
    if sec:
        parts.append(sec)

    sec = _format_ai_distilled_section("写作技法", writing_tech)
    if sec:
        parts.append(sec)

    if len(parts) == 1:
        # 只有头部
        return None

    return "\n\n".join(parts)
