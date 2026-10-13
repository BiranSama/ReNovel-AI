#!/bin/bash

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║       Re:Novel 文境重塑 - 环境安装脚本                      ║"
echo "║       Re:Novel AI - Environment Setup Script               ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

if ! command -v python3 &> /dev/null; then
    echo "[错误] 未检测到 Python，请先安装 Python 3.11 或更高版本"
    echo "[Error] Python not found. Please install Python 3.11 or newer"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "[信息] 检测到 Python 版本: $PYTHON_VERSION"

# 依赖的 numpy 2.4 / onnxruntime 1.30 需要 3.11+
if ! python3 -c "import sys; sys.exit(sys.version_info < (3, 11))"; then
    echo "[警告] 需要 Python 3.11 或更高版本，当前版本无法安装部分依赖"
    echo "[Warning] Python 3.11 or newer is required"
    read -p "是否继续安装？ / Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
fi

echo ""
echo "[步骤 1/4] 创建虚拟环境..."
if [ -d "venv" ]; then
    echo "[信息] 虚拟环境已存在，跳过创建"
else
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "[错误] 创建虚拟环境失败"
        exit 1
    fi
    echo "[完成] 虚拟环境创建成功"
fi

echo ""
echo "[步骤 2/4] 激活虚拟环境..."
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "[错误] 激活虚拟环境失败"
    exit 1
fi
echo "[完成] 虚拟环境已激活"

echo ""
echo "[步骤 3/4] 升级 pip..."
pip install --upgrade pip -q
echo "[完成] pip 已升级"

echo ""
echo "[步骤 4/4] 安装项目依赖..."
echo "[信息] 这可能需要几分钟，请耐心等待..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "[错误] 依赖安装失败"
    exit 1
fi
echo "[完成] 依赖安装成功"

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    安装完成！                              ║"
echo "║                 Installation Complete!                     ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "使用方法 / Usage:"
echo "  1. 激活虚拟环境 / Activate venv:"
echo "     source venv/bin/activate"
echo ""
echo "  2. 启动程序 / Run the app:"
echo "     python main.py"
echo ""
echo "  3. 退出虚拟环境 / Deactivate:"
echo "     deactivate"
echo ""
