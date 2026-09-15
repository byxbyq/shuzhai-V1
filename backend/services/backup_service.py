# -*- coding: utf-8 -*-
"""数据滚动备份服务

书稿数据（data/ 下 novel_projects 等）不入版本控制，本服务提供唯一的安全网：

- 快照式备份：data/_backups/YYYYMMDD-HHMMSS/ 内保存关键目录与根级 JSON 配置
- SQLite 一致性：.db/.sqlite/.sqlite3 走 sqlite3 backup API，避免拷到脏页
- 滚动保留：默认保留最近 7 份，超出的旧快照自动删除
- 启动节流：自动模式下当天已有快照则跳过（每天至多一份）；--force 不受限

用法：
  python backend/services/backup_service.py            自动模式（当天已备份则跳过）
  python backend/services/backup_service.py --force    立即备份一份
  from backend.services.backup_service import run_backup; run_backup()
"""
import os
import re
import sys
import shutil
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, 'data')
BACKUP_ROOT = os.path.join(DATA_DIR, '_backups')

# 备份范围：书稿与用户数据目录 + 根级 JSON 配置
BACKUP_DIRS = ['novel_projects', 'users', 'auth', 'skills',
               'storyboard_history', 'ranking']
BACKUP_ROOT_GLOBS = ['.json']  # data/ 根下所有 .json（ai_config/ai_usage/sanitizer 等）

KEEP_SNAPSHOTS = 7
_SNAPSHOT_RE = re.compile(r'^\d{8}-\d{6}$')


def _copy_sqlite(src, dst):
    """用 sqlite3 backup API 复制数据库，失败时回退普通拷贝"""
    try:
        s = sqlite3.connect(f'file:{src}?mode=ro', uri=True)
        try:
            d = sqlite3.connect(dst)
            try:
                s.backup(d)
            finally:
                d.close()
        finally:
            s.close()
        return True
    except Exception:
        try:
            shutil.copy2(src, dst)
        except Exception:
            return False
        return True


def _list_snapshots():
    """按名称升序返回现有快照目录名（时间戳命名，字典序即时间序）"""
    if not os.path.isdir(BACKUP_ROOT):
        return []
    return sorted(d for d in os.listdir(BACKUP_ROOT)
                  if _SNAPSHOT_RE.match(d) and os.path.isdir(os.path.join(BACKUP_ROOT, d)))


def run_backup(force=False, keep=KEEP_SNAPSHOTS):
    """执行一次滚动备份。

    返回 dict：{'created': 快照名或 None, 'skipped': 原因或 None,
                'files': 文件数, 'size_mb': 大小}
    任何异常都会被捕获并以 skipped 返回——备份失败绝不阻塞主流程。
    """
    result = {'created': None, 'skipped': None, 'files': 0, 'size_mb': 0.0}
    try:
        if not os.path.isdir(DATA_DIR):
            result['skipped'] = 'data 目录不存在'
            return result
        existing = _list_snapshots()
        today = datetime.now().strftime('%Y%m%d')
        if not force and existing and existing[-1].startswith(today):
            result['skipped'] = f'今天已有备份（{existing[-1]}），跳过'
            return result

        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        dest = os.path.join(BACKUP_ROOT, stamp)
        os.makedirs(dest, exist_ok=True)

        count = 0
        for name in BACKUP_DIRS:
            src = os.path.join(DATA_DIR, name)
            if not os.path.isdir(src):
                continue
            dst = os.path.join(dest, name)
            for dp, dns, fns in os.walk(src):
                rel = os.path.relpath(dp, DATA_DIR)
                out = os.path.join(dest, rel)
                os.makedirs(out, exist_ok=True)
                for fn in fns:
                    s, t = os.path.join(dp, fn), os.path.join(out, fn)
                    if fn.endswith(('.db', '.sqlite', '.sqlite3')):
                        if _copy_sqlite(s, t):
                            count += 1
                    else:
                        try:
                            shutil.copy2(s, t)
                            count += 1
                        except Exception as e:
                            logger.warning('备份跳过文件 %s: %s', s, e)
        for fn in os.listdir(DATA_DIR):
            if fn.endswith('.json') and os.path.isfile(os.path.join(DATA_DIR, fn)):
                try:
                    shutil.copy2(os.path.join(DATA_DIR, fn), os.path.join(dest, fn))
                    count += 1
                except Exception as e:
                    logger.warning('备份跳过配置 %s: %s', fn, e)

        size = sum(os.path.getsize(os.path.join(dp, f))
                   for dp, _, fns in os.walk(dest) for f in fns)
        result.update(created=stamp, files=count, size_mb=round(size / 1048576, 1))

        # 滚动清理：保留最近 keep 份
        for old in _list_snapshots()[:-keep]:
            shutil.rmtree(os.path.join(BACKUP_ROOT, old), ignore_errors=True)
        logger.info('数据备份完成: %s（%d 文件, %.1f MB）', stamp, count, result['size_mb'])
    except Exception as e:
        result['skipped'] = f'备份异常: {e}'
        logger.warning(result['skipped'])
    return result


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    r = run_backup(force='--force' in sys.argv)
    if r['created']:
        print(f"[backup] 已创建快照 data/_backups/{r['created']}"
              f"（{r['files']} 文件, {r['size_mb']} MB）")
    else:
        print(f"[backup] {r['skipped']}")
