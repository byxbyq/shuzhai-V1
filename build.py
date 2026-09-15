# -*- coding: utf-8 -*-
"""书斋V65 一键打包脚本"""
import os, sys, subprocess, shutil

ROOT = os.path.dirname(os.path.abspath(__file__))

def check_pyinstaller():
    """检查PyInstaller是否安装"""
    try:
        import PyInstaller
        return True
    except ImportError:
        return False

def install_pyinstaller():
    """安装PyInstaller"""
    print("正在安装 PyInstaller...")
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pyinstaller'])
    print("✅ PyInstaller 安装完成")

def check_dual_copy_consistency():
    """打包前闸门：APK 双副本必须一致（sync_apk_backend.py --verify）"""
    print("\n[闸门] 校验 backend/ 与 APK 内嵌副本一致性...")
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'sync_apk_backend.py'), '--verify'], cwd=ROOT)
    if r.returncode != 0:
        print("\n❌ 双副本漂移，打包中止；先运行 python sync_apk_backend.py 同步后重试")
        sys.exit(1)
    print("  ✅ 双副本一致")

def build():
    """执行打包"""
    check_dual_copy_consistency()
    if not check_pyinstaller():
        install_pyinstaller()

    print("\n" + "=" * 50)
    print("  开始打包 书斋V65")
    print("=" * 50)

    # 清理旧的构建文件
    for d in ['build', 'dist', '__pycache__']:
        p = os.path.join(ROOT, d)
        if os.path.exists(p):
            shutil.rmtree(p)
            print(f"  清理: {d}")

    # 运行PyInstaller
    spec_file = os.path.join(ROOT, 'shuzhai.spec')
    cmd = [sys.executable, '-m', 'PyInstaller', spec_file, '--noconfirm', '--clean']
    print(f"\n  执行: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=ROOT)

    if result.returncode == 0:
        dist_dir = os.path.join(ROOT, 'dist', '书斋V65')
        if os.path.exists(dist_dir):
            # 创建data目录
            data_dir = os.path.join(dist_dir, 'data')
            os.makedirs(data_dir, exist_ok=True)

            # 复制前端文件（PyInstaller datas对中文路径不友好，手动复制）
            frontend_src = os.path.join(ROOT, 'frontend')
            frontend_dst = os.path.join(dist_dir, 'frontend')
            if os.path.exists(frontend_dst):
                shutil.rmtree(frontend_dst)
            shutil.copytree(frontend_src, frontend_dst)
            print(f"  复制前端文件: {frontend_src} -> {frontend_dst}")

            # 复制说明文件
            readme = os.path.join(dist_dir, '使用说明.txt')
            with open(readme, 'w', encoding='utf-8') as f:
                f.write("""书斋 V65 - 使用说明
========================

1. 双击「书斋V65.exe」启动
2. 浏览器自动打开 http://127.0.0.1:8888
3. 首次使用请注册账号
4. 注册后登录即可使用全部功能

手机访问：
- 手机和电脑连同一WiFi
- 浏览器输入 http://电脑IP:8888

外网访问（可选）：
- 使用 Cloudflare Tunnel 配置外网访问
- 详情参考官方文档

数据存储：
- 所有数据存储在 exe 同目录的 data/ 文件夹
- 可随时备份整个 data 文件夹

技术支持：书斋 V65
""")

            size_mb = sum(os.path.getsize(os.path.join(dp, f)) for dp, dn, fn in os.walk(dist_dir) for f in fn) / 1024 / 1024
            print(f"\n✅ 打包完成！")
            print(f"   输出目录: {dist_dir}")
            print(f"   大小: {size_mb:.1f} MB")
            print(f"   启动文件: {os.path.join(dist_dir, '书斋V65.exe')}")
        else:
            print("\n❌ 打包失败：输出目录不存在")
            sys.exit(1)
    else:
        print(f"\n❌ 打包失败：PyInstaller 返回码 {result.returncode}")
        sys.exit(1)

if __name__ == '__main__':
    build()
