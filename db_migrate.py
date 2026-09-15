# -*- coding: utf-8 -*-
"""书斋 V66 - JSON → SQLite 一次性迁移脚本

扫描所有项目目录，读取 project.json / truth_ledger.json / world_meta.json
灌入 project.db。迁移完成后 JSON 文件保留（不删除），但后续读写走 SQLite。

用法:
    python db_migrate.py              # 扫描默认用户目录
    python db_migrate.py --dir PATH   # 指定单个项目目录
    python db_migrate.py --all        # 扫描所有已知目录
"""

import os, sys, json, logging, shutil, time

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# 将 backend/ 加入 import path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend.db import ProjectDB, _j


def migrate_project(project_dir: str) -> bool:
    """迁移单个项目目录的 JSON → SQLite"""
    db_path = os.path.join(project_dir, "project.db")
    project_json = os.path.join(project_dir, "project.json")
    ledger_json = os.path.join(project_dir, "truth_ledger.json")
    world_json = os.path.join(project_dir, "world_meta.json")

    # 已经有 DB 且无 JSON → 不需要迁移
    if os.path.exists(db_path) and not os.path.exists(project_json):
        logger.info(f"[MIGRATE] 跳过（已有DB无JSON）: {project_dir}")
        return True

    # 无 JSON → 无法迁移
    if not os.path.exists(project_json):
        logger.warning(f"[MIGRATE] 跳过（无project.json）: {project_dir}")
        return False

    logger.info(f"[MIGRATE] 开始迁移: {project_dir}")

    # 备份 JSON 文件（迁移前安全网）
    for f in (project_json, ledger_json, world_json):
        if os.path.exists(f):
            try:
                shutil.copy2(f, f + '.pre_sqlite_bak')
            except Exception as e:
                logger.warning(f"[MIGRATE] 备份失败 {f}: {e}")

    # 如果已有 DB，检查是否已有数据（避免重复迁移）
    if os.path.exists(db_path):
        try:
            existing_db = ProjectDB(project_dir)
            existing_pid = existing_db.get_project_id()
            if existing_pid is not None:
                # 已有项目数据 → 跳过
                logger.info(f"[MIGRATE] 跳过（DB已有数据）: {project_dir}")
                existing_db.close()
                return True
            # DB 文件存在但无数据（部分迁移），继续用现有 DB
            existing_db.close()
            logger.info(f"[MIGRATE] DB 存在但无数据，继续覆盖")
        except Exception as e:
            logger.warning(f"[MIGRATE] DB 检查失败: {e}")

    db = ProjectDB(project_dir)

    try:
        # 1. 读取 project.json
        with open(project_json, 'r', encoding='utf-8') as f:
            project_data = json.load(f)

        # 2. 创建项目记录
        meta = project_data.get("meta", {})
        pid = db.create_project(
            title=meta.get("title", "未命名"),
            genre=meta.get("genre", ""),
        )

        # 3. 写入项目元数据（chapters/volumes/characters 等）
        db.save_project_meta(project_data)

        # 4. 读取并写入 TruthLedger
        if os.path.exists(ledger_json):
            with open(ledger_json, 'r', encoding='utf-8') as f:
                ledger_data = json.load(f)
            # 移除 "updated" 键（不属于 dataclass 字段）
            ledger_data.pop("updated", None)
            db.save_ledger(ledger_data)
            logger.info(f"[MIGRATE] Ledger 已迁移")
        else:
            logger.info(f"[MIGRATE] 无 ledger JSON，跳过")

        # 5. 读取并写入 WorldSettings
        if os.path.exists(world_json):
            with open(world_json, 'r', encoding='utf-8') as f:
                world_data = json.load(f)
            db.save_world(world_data)
            logger.info(f"[MIGRATE] WorldSettings 已迁移")
        else:
            logger.info(f"[MIGRATE] 无 world JSON，跳过")

        # 6. 写入 timeline.json（如果存在）
        timeline_json = os.path.join(project_dir, "timeline.json")
        if os.path.exists(timeline_json):
            try:
                with open(timeline_json, 'r', encoding='utf-8') as f:
                    timeline_data = json.load(f)
                _migrate_timeline(db, pid, timeline_data)
                logger.info(f"[MIGRATE] Timeline 已迁移")
            except Exception as e:
                logger.warning(f"[MIGRATE] Timeline 迁移失败: {e}")

        # 7. 写入 writing_stats.json（如果存在）
        stats_json = os.path.join(project_dir, "writing_stats.json")
        if os.path.exists(stats_json):
            try:
                with open(stats_json, 'r', encoding='utf-8') as f:
                    stats_data = json.load(f)
                _migrate_writing_stats(db, pid, stats_data)
                logger.info(f"[MIGRATE] WritingStats 已迁移")
            except Exception as e:
                logger.warning(f"[MIGRATE] WritingStats 迁移失败: {e}")

        # 8. 写入 workflow_state.json（如果存在）
        wf_json = os.path.join(project_dir, "workflow_state.json")
        if os.path.exists(wf_json):
            try:
                with open(wf_json, 'r', encoding='utf-8') as f:
                    wf_data = json.load(f)
                _migrate_workflow(db, pid, wf_data)
                logger.info(f"[MIGRATE] Workflow 已迁移")
            except Exception as e:
                logger.warning(f"[MIGRATE] Workflow 迁移失败: {e}")

        # 9. 写入 audit_log.json（如果存在）
        audit_json = os.path.join(project_dir, "audit_log.json")
        if os.path.exists(audit_json):
            try:
                with open(audit_json, 'r', encoding='utf-8') as f:
                    audit_data = json.load(f)
                _migrate_audit(db, pid, audit_data)
                logger.info(f"[MIGRATE] AuditLog 已迁移")
            except Exception as e:
                logger.warning(f"[MIGRATE] AuditLog 迁移失败: {e}")

        # 10. 写入 state_memory/_index.json（蒸馏摘要）
        sm_dir = os.path.join(project_dir, "state_memory")
        if os.path.isdir(sm_dir):
            _migrate_state_memory(db, pid, sm_dir)
            logger.info(f"[MIGRATE] StateMemory 已迁移")

        logger.info(f"[MIGRATE] ✅ 完成: {project_dir}")
        db.close()
        return True

    except Exception as e:
        logger.error(f"[MIGRATE] ❌ 失败: {project_dir}, 错误: {e}")
        db.close()
        # 恢复备份
        if os.path.exists(db_path):
            try:
                os.unlink(db_path)
            except Exception:
                pass
        return False


def _migrate_timeline(db: ProjectDB, pid: int, data: dict):
    """迁移 timeline.json → timeline 表"""
    volumes_data = data.get("volumes", {})
    rows = []
    for vi_str, vol in volumes_data.items():
        vi = int(vi_str)
        chapters_data = vol.get("chapters", {})
        for ci_str, ch in chapters_data.items():
            ci = int(ci_str)
            rows.append((
                pid, vi, ci,
                ch.get("planned", ""),
                ch.get("actual", ""),
                _j(ch.get("divergences", [])),
                ch.get("annotation", ""),
                ch.get("last_compared", ""),
                _j(ch.get("characters", [])),
                _j(ch.get("events", [])),
                _j(ch.get("foreshadowing", {})),
                _j(ch.get("new_settings", [])),
                _j(ch.get("bridge", {})),
            ))
    if rows:
        db.executemany(
            """INSERT INTO timeline(project_id, volume_index, chapter_index,
               planned, actual, divergences, annotation, last_compared,
               characters, events, foreshadowing, new_settings, bridge)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows
        )
        db.connect().commit()


def _migrate_writing_stats(db: ProjectDB, pid: int, data: dict):
    """迁移 writing_stats.json → writing_stats 表"""
    rows = []
    for date, stats in data.items():
        rows.append((
            pid, date,
            stats.get("words_added", 0),
            stats.get("words_total", 0),
            _j(stats.get("chapters_touched", [])),
        ))
    if rows:
        db.executemany(
            """INSERT INTO writing_stats(project_id, date, words_added,
               words_total, chapters_touched) VALUES(?,?,?,?,?)""",
            rows
        )
        db.connect().commit()


def _migrate_workflow(db: ProjectDB, pid: int, data: dict):
    """迁移 workflow_state.json → workflow_state 表"""
    db.execute(
        """UPDATE workflow_state SET current_step=?, completed_steps=?,
           step_status=?, updated=? WHERE project_id=?""",
        (
            data.get("currentStep", ""),
            _j(data.get("completedSteps", [])),
            _j(data.get("stepStatus", {})),
            time.strftime("%Y-%m-%d %H:%M"),
            pid,
        )
    )
    db.connect().commit()


def _migrate_audit(db: ProjectDB, pid: int, data: list):
    """迁移 audit_log.json → audit_log 表"""
    rows = []
    for entry in data:
        rows.append((
            pid,
            entry.get("ts", ""),
            entry.get("action", ""),
            entry.get("target", ""),
            _j(entry.get("detail", {})),
        ))
    if rows:
        db.executemany(
            """INSERT INTO audit_log(project_id, ts, action, target, detail)
               VALUES(?,?,?,?,?)""",
            rows
        )
        db.connect().commit()


def _migrate_state_memory(db: ProjectDB, pid: int, sm_dir: str):
    """迁移 state_memory/*.json → state_memory 表"""
    rows = []
    for fname in os.listdir(sm_dir):
        if fname.endswith('.json') and fname != '_index.json':
            fpath = os.path.join(sm_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    sm = json.load(f)
                rows.append((
                    pid,
                    sm.get("chapter_index", 0),
                    sm.get("distilled_at", ""),
                    _j(sm.get("characters", [])),
                    _j(sm.get("events", [])),
                    _j(sm.get("foreshadowing", {})),
                    _j(sm.get("new_settings", [])),
                    _j(sm.get("bridge", {})),
                ))
            except Exception:
                pass
    if rows:
        db.executemany(
            """INSERT INTO state_memory(project_id, chapter_index, distilled_at,
               characters, events, foreshadowing, new_settings, bridge)
               VALUES(?,?,?,?,?,?,?,?)""",
            rows
        )
        db.connect().commit()


def scan_projects(base_dir: str) -> list:
    """扫描目录下的所有项目（有 project.json 的子目录）"""
    projects = []
    if not os.path.exists(base_dir):
        return projects
    for name in os.listdir(base_dir):
        full = os.path.join(base_dir, name)
        pj = os.path.join(full, "project.json")
        if os.path.isdir(full) and os.path.exists(pj):
            projects.append(full)
    return projects


def main():
    import argparse
    parser = argparse.ArgumentParser(description="书斋 V66 JSON→SQLite 迁移")
    parser.add_argument("--dir", help="指定单个项目目录")
    parser.add_argument("--all", action="store_true", help="扫描所有已知目录")
    args = parser.parse_args()

    from backend.runtime_paths import get_data_dir, get_projects_dir

    if args.dir:
        dirs = [args.dir]
    else:
        dirs = []
        # 默认用户项目目录
        dirs.extend(scan_projects(get_projects_dir()))
        # 公共项目目录
        public = os.path.join(get_data_dir(), 'novel_projects')
        if os.path.exists(public) and os.path.abspath(public) != os.path.abspath(get_projects_dir()):
            dirs.extend(scan_projects(public))
        # 其他用户目录
        users_dir = os.path.join(get_data_dir(), 'users')
        if os.path.exists(users_dir):
            for user in os.listdir(users_dir):
                ud = os.path.join(users_dir, user, 'projects')
                if os.path.isdir(ud):
                    dirs.extend(scan_projects(ud))

    success = 0
    fail = 0
    for d in dirs:
        if migrate_project(d):
            success += 1
        else:
            fail += 1

    print(f"\n迁移完成: {success} 成功, {fail} 失败, 共 {len(dirs)} 个项目")
    if fail > 0:
        print("⚠️ 有失败的项目，JSON 备份文件保留在 .pre_sqlite_bak 中")


if __name__ == "__main__":
    main()
