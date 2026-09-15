# -*- coding: utf-8 -*-
"""将主项目 backend/ 和 server.py 同步到 APK 的 Chaquopy Python 目录

用法：
  python sync_apk_backend.py              同步 backend/ + server.py（并清理目标侧陈旧 .py）
  python sync_apk_backend.py --frontend   额外同步 frontend/ 到 Capacitor public 目录
  python sync_apk_backend.py --verify     只校验两侧一致性（MD5），不同步；退出码 1 表示漂移
"""
import os, shutil, sys, hashlib

ROOT = os.path.dirname(os.path.abspath(__file__))
APK_PY = os.path.join(ROOT, 'apk', 'android', 'app', 'src', 'main', 'python')

def _md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def _walk_py_files(src):
    """返回 src 下所有 .py 文件的 {相对路径: 绝对路径}（排除 __pycache__）"""
    result = {}
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        rel = os.path.relpath(root, src)
        for f in files:
            if f.endswith('.py'):
                rel_path = f if rel == '.' else os.path.join(rel, f)
                result[rel_path] = os.path.join(root, f)
    return result

def sync_backend():
    """同步 backend/ 目录下所有 .py 文件，并清理目标侧已不存在的陈旧副本"""
    src = os.path.join(ROOT, 'backend')
    dst = os.path.join(APK_PY, 'backend')
    src_files = _walk_py_files(src)
    count = 0
    for rel_path, src_path in src_files.items():
        dst_path = os.path.join(dst, rel_path)
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        shutil.copy2(src_path, dst_path)
        count += 1
    # 清理目标侧陈旧 .py（源端已删除的文件），防止 APK 残留旧模块
    removed = 0
    for rel_path, dst_path in _walk_py_files(dst).items():
        if rel_path not in src_files:
            os.remove(dst_path)
            removed += 1
    print(f'[sync] backend/: {count} .py files, removed {removed} stale')
    return count

def sync_server():
    """同步 server.py"""
    src = os.path.join(ROOT, 'server.py')
    dst = os.path.join(APK_PY, 'server.py')
    shutil.copy2(src, dst)
    print(f'[sync] server.py')

def sync_frontend():
    """同步前端文件到 Capacitor public 目录"""
    src = os.path.join(ROOT, 'frontend')
    dst = os.path.join(ROOT, 'apk', 'android', 'app', 'src', 'main', 'assets', 'public')
    count = 0
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__')]
        rel = os.path.relpath(root, src)
        dst_dir = os.path.join(dst, rel) if rel != '.' else dst
        os.makedirs(dst_dir, exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(root, f), os.path.join(dst_dir, f))
            count += 1
    print(f'[sync] frontend/: {count} files')

def verify_backend():
    """校验 backend/ + server.py 与 APK 副本的 MD5 一致性；返回差异数"""
    diffs = []
    src_files = _walk_py_files(os.path.join(ROOT, 'backend'))
    dst_files = _walk_py_files(os.path.join(APK_PY, 'backend'))
    for rel_path, src_path in src_files.items():
        dst_path = dst_files.get(rel_path)
        if dst_path is None:
            diffs.append(f'missing-in-apk: backend/{rel_path}')
        elif _md5(src_path) != _md5(dst_path):
            diffs.append(f'content-drift: backend/{rel_path}')
    for rel_path in dst_files:
        if rel_path not in src_files:
            diffs.append(f'stale-in-apk: backend/{rel_path}')
    apk_server = os.path.join(APK_PY, 'server.py')
    if not os.path.exists(apk_server):
        diffs.append('missing-in-apk: server.py')
    elif _md5(os.path.join(ROOT, 'server.py')) != _md5(apk_server):
        diffs.append('content-drift: server.py')
    if diffs:
        print(f'[verify] 发现 {len(diffs)} 处漂移：')
        for d in diffs:
            print(f'  - {d}')
    else:
        print(f'[verify] 一致：backend/ {len(src_files)} 个 .py + server.py，与 APK 副本无漂移')
    return len(diffs)

if __name__ == '__main__':
    if '--verify' in sys.argv:
        sys.exit(1 if verify_backend() else 0)
    sync_backend()
    sync_server()
    if '--frontend' in sys.argv:
        sync_frontend()
    print('[verify] 同步后一致性校验：')
    if verify_backend():
        print('[sync] 警告：同步后仍存在漂移，请检查上方清单')
        sys.exit(1)
    print('[sync] Done. Rebuild with: cd apk/android && ./gradlew assembleDebug --no-daemon')
