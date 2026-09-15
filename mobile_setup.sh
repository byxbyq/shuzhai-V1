#!/data/data/com.termux/files/usr/bin/bash
# 书斋手机端一键安装脚本 (Termux)
# 用法: bash mobile_setup.sh

set -e
echo "=========================================="
echo "  书斋 - 手机端安装"
echo "=========================================="

# 安装Python
pkg install -y python python-pip clang 2>/dev/null || true
pip install --upgrade pip

# 复制项目文件
SHUZHAI_DIR="$HOME/shuzhai"
if [ -d "$SHUZHAI_DIR" ]; then
    echo "目录已存在，跳过复制"
else
    echo "请将书斋项目文件夹复制到: $SHUZHAI_DIR"
    echo "方法1: 使用Termux的 'termux-setup-storage' 然后从内部存储复制"
    echo "方法2: 使用scp/sftp从电脑传输"
    mkdir -p "$SHUZHAI_DIR"
    echo "请先复制文件到 $SHUZHAI_DIR，然后重新运行此脚本"
    exit 1
fi

cd "$SHUZHAI_DIR"

# 安装轻量依赖
echo "安装Python依赖..."
pip install -r requirements-mobile.txt

# 创建数据目录
mkdir -p data/novel_projects

echo ""
echo "=========================================="
echo "  安装完成！"
echo "  启动命令: cd ~/shuzhai && python server.py"
echo "  然后手机浏览器访问: http://127.0.0.1:8894"
echo "=========================================="
