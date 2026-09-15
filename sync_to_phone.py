# -*- coding: utf-8 -*-
"""将书斋项目打包为zip，方便传输到手机

打包前自动运行 sync_apk_backend.py --verify 闸门；加 --skip-verify 可跳过。
"""
import os, sys, zipfile, subprocess
sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.abspath(__file__))
output = os.path.join(ROOT, 'shuzhai_mobile.zip')

if '--skip-verify' not in sys.argv:
    print("[闸门] 校验 backend/ 与 APK 内嵌副本一致性...")
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'sync_apk_backend.py'), '--verify'], cwd=ROOT)
    if r.returncode != 0:
        print("❌ 双副本漂移，打包中止；先运行 python sync_apk_backend.py 同步后重试")
        sys.exit(1)

print("正在打包书斋项目（移动端）...")
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
    skip_dirs = {'__pycache__', '.git', 'node_modules', 'dist', 'build', '.venv', 'venv', 'apk/android/.gradle', 'apk/android/app/build'}
    skip_exts = {'.pyc', '.pyo', '.exe', '.dll', '.so', '.dylib'}
    
    for root, dirs, files in os.walk(ROOT):
        # 跳过不需要的目录
        rel_root = os.path.relpath(root, ROOT)
        if any(rel_root.startswith(sd) or sd.split('/')[0] in rel_root.replace('\\','/').split('/') for sd in skip_dirs):
            continue
        dirs[:] = [d for d in dirs if d not in {s.split('/')[-1] for s in skip_dirs}]
        
        for fname in files:
            if any(fname.endswith(ext) for ext in skip_exts):
                continue
            fpath = os.path.join(root, fname)
            arcname = os.path.join('shuzhai', os.path.relpath(fpath, ROOT))
            try:
                zf.write(fpath, arcname)
            except Exception as e:
                print(f"  跳过: {fname} ({e})")

size_mb = os.path.getsize(output) / 1024 / 1024
print(f"\n打包完成: {output}")
print(f"大小: {size_mb:.1f} MB")
print(f"\n传输到手机方法:")
print(f"  1. USB: 直接复制zip到手机，用Termux解压")
print(f"  2. 微信/QQ: 发送文件到手机，用Termux解压")
print(f"  3. scp: scp {output} user@phone-ip:/sdcard/")
