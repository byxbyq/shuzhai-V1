# -*- coding: utf-8 -*-
import os
import json
import logging
from fastapi import APIRouter

from backend.services.project_service import state, get_ledger

logger = logging.getLogger(__name__)

"""全书优化诊断"""

router = APIRouter()

# ============================================================
# 全书优化诊断
# ============================================================
@router.post("/diagnosis")
def full_diagnosis():
    if not state.project: return {"ok": False, "error": "no project"}
    chapters = state.project.chapters or []
    worklist = []
    all_issues = []

    # 串联SkillPack：加载导入的技能包规则
    skill_rules = []
    try:
        skills_dir = os.path.join(state.project.project_dir, 'skills')
        if os.path.exists(skills_dir):
            for f in os.listdir(skills_dir):
                if f.endswith('.json'):
                    with open(os.path.join(skills_dir, f), 'r', encoding='utf-8') as sf:
                        sk = json.load(sf)
                        if sk.get('content'):
                            skill_rules.append(sk['content'])
    except Exception: pass

    # 加载用户偏好
    user_prefs = {}
    try:
        pref_file = os.path.join(state.project.project_dir, 'user_preferences.json')
        if os.path.exists(pref_file):
            with open(pref_file, 'r', encoding='utf-8') as pf:
                user_prefs = json.load(pf)
    except Exception: pass

    # 加载Truth Ledger数据用于跨章一致性诊断
    ledger = get_ledger()
    ledger_data = {}
    try:
        if ledger:
            char_states = {k: v for k, v in ledger.character_states.items()}
            hooks = [{"id": h.id, "content": h.content, "status": h.status, "deadline_chapter": h.deadline_chapter} for h in ledger.foreshadowing]
            chapter_logs = [{"chapter": l.chapter, "summary": l.summary} for l in ledger.chapter_logs]
        else:
            char_states = {}
            hooks = []
            chapter_logs = []
    except Exception:
        char_states = {}
        hooks = []
        chapter_logs = []
    timeline = []

    # 预计算：已死亡角色名列表
    dead_chars = []
    for name, st in char_states.items():
        status = st.get("status", "") if isinstance(st, dict) else ""
        if status in ("死亡", "dead", "阵亡", "牺牲"):
            dead_chars.append(name)

    for i, ch in enumerate(chapters):
        content = ch.get("content", "")
        outline = ch.get("outline", "")
        wc = ch.get("word_count", 0)
        issues = []

        # 技能包检查：AI高频词
        ai_words = ['首先', '其次', '最后', '总的来说', '综上所述', '值得注意的是', '显而易见']
        if content.strip():
            found = [w for w in ai_words if w in content]
            if found:
                issues.append({"type": "ai_pattern", "severity": "medium", "detail": f"AI高频词: {', '.join(found[:3])}"})

        # 技能包规则检查
        for rule_text in skill_rules:
            if isinstance(rule_text, str) and content.strip():
                # 从规则文本中提取关键禁止词
                rule_lines = [l.strip() for l in rule_text.split('\n') if l.strip().startswith('- 禁止')]
                for rl in rule_lines:
                    keyword = rl.replace('- 禁止', '').strip().strip('"').strip("'").strip('"').rstrip('，')
                    if keyword and len(keyword) > 1 and len(keyword) < 30 and keyword in content:
                        issues.append({"type": "skill_rule_violation", "severity": "medium", "detail": f"技能包规则违反: {keyword}"})

        # 偏好检查：字数达标
        target = user_prefs.get('word_count_target', 0) or ch.get('word_count_target', ch.get('target_words', 0))
        if target and wc > 0:
            if wc < target * 0.55:
                issues.append({"type": "wc_short", "severity": "high", "detail": f"目标{target}字，实际{wc}字(不足55%)"})
            elif wc > target * 1.8:
                issues.append({"type": "wc_long", "severity": "medium", "detail": f"目标{target}字，实际{wc}字(超出80%)"})

        # 基础检查
        if not content.strip() and i > 0:
            issues.append({"type": "empty", "severity": "high", "detail": f"无内容"})
        if wc > 0 and wc < 500:
            issues.append({"type": "short", "severity": "medium", "detail": f"仅{wc}字"})
        if outline.strip() and not content.strip():
            issues.append({"type": "unwritten", "severity": "medium", "detail": f"有大纲未写正文"})
        if i > 0 and content.strip():
            prev = chapters[i-1].get("content", "")
            if prev and content[:200] == prev[:200]:
                issues.append({"type": "duplicate", "severity": "high", "detail": f"开头与前一章相同"})

        # Ledger检查：已死亡角色再次出现
        if content.strip() and dead_chars:
            for name in dead_chars:
                if name in content:
                    issues.append({"type": "ledger_conflict", "severity": "high", "detail": f"角色'{name}'已在ledger标记为死亡，但第{i+1}章再次出现"})

        # Ledger检查：角色状态突变（无过渡）
        if content.strip() and char_states:
            for name, st in char_states.items():
                if not isinstance(st, dict):
                    continue
                last_ch = st.get("last_chapter", 0)
                if last_ch == i + 1:
                    continue  # 本章就是最新状态，跳过
                pos = st.get("position", "")
                if pos and len(str(pos)) > 3:
                    # 简单检测：如果角色位置大幅变化且本章没有移动描写
                    pass  # 留待更精细的NLP检测

        if issues:
            worklist.append({
                "chapter": i + 1,
                "title": ch.get("title", ""),
                "word_count": wc,
                "issues": issues,
                "status": "pending"
            })
            all_issues.extend(issues)

    # 全局Ledger检查：伏笔逾期
    total_written = sum(1 for ch in chapters if ch.get("word_count", 0) > 0)
    if hooks and total_written > 0:
        overdue = []
        for h in hooks:
            if h.get("deadline_chapter") and h.get("status") != "recovered":
                if total_written > h["deadline_chapter"]:
                    overdue.append(h.get("content", "未知伏笔"))
        if overdue:
            all_issues.append({"type": "hook_overdue", "severity": "high", "detail": f"逾期未回收伏笔({len(overdue)}个): {', '.join(overdue[:3])}"})
            worklist.append({
                "chapter": 0,
                "title": "全局",
                "word_count": 0,
                "issues": [{"type": "hook_overdue", "severity": "high", "detail": f"逾期未回收伏笔({len(overdue)}个): {', '.join(overdue[:3])}"}],
                "status": "pending"
            })

    # 全局Ledger检查：时间线断裂（连续两章时间倒流）
    if len(timeline) >= 2:
        for j in range(1, len(timeline)):
            prev_t = timeline[j-1].get("time", "")
            curr_t = timeline[j].get("time", "")
            if prev_t and curr_t and isinstance(prev_t, (int, float)) and isinstance(curr_t, (int, float)):
                if curr_t < prev_t:
                    all_issues.append({"type": "timeline_break", "severity": "high", "detail": f"时间线断裂: 第{timeline[j-1].get('chapter','?')}章时间{prev_t} → 第{timeline[j].get('chapter','?')}章时间{curr_t}"})
                    break

    import time
    result = {
        "ok": True,
        "summary": {
            "total_chapters": len(chapters),
            "written_chapters": sum(1 for ch in chapters if ch.get("word_count", 0) > 0),
            "total_words": sum(ch.get("word_count", 0) for ch in chapters),
            "total_issues": len(all_issues),
            "high_issues": sum(1 for i in all_issues if i["severity"] == "high"),
            "medium_issues": sum(1 for i in all_issues if i["severity"] == "medium"),
            "skill_rules_loaded": len(skill_rules),
            "prefs_loaded": bool(user_prefs),
        },
        "worklist": worklist,
    }

    # 存入真相账本（记忆持久化）
    try:
        ledger = get_ledger()
        if ledger:
            # 将诊断结果存入 validation_warnings
            ledger.validation_warnings.append({
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "summary": result["summary"],
                "worklist": result.get("worklist", []),
            })
            # 保留最近20条
            if len(ledger.validation_warnings) > 20:
                ledger.validation_warnings = ledger.validation_warnings[-20:]
            ledger.save()
    except Exception:
        pass

    return result

