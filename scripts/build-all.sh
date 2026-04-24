#!/bin/bash
# AI 听课助手 - 全平台一键打包脚本

set -e

PROJECT_ROOT=$(pwd)
BACKEND_DIR="$PROJECT_ROOT/backend"
ELECTRON_DIR="$PROJECT_ROOT/electron"

echo "🚀 开始全平台打包流程..."

# 1. 打包后端
echo "📦 [1/3] 正在打包 Python 后端..."
cd "$BACKEND_DIR"
# 确保依赖已安装
pip install -r requirements.txt
# 使用 PyInstaller 打包
pyinstaller --onefile --name ai-class-backend main.py
echo "✅ 后端打包完成: $BACKEND_DIR/dist/ai-class-backend"

# 2. 构建前端与 Electron
echo "🏗️ [2/3] 正在构建前端与 Electron 主进程..."
cd "$ELECTRON_DIR"
npm install
npm run build
echo "✅ 前端构建完成"

# 3. 封装安装包
echo "🎁 [3/3] 正在生成安装包..."
# 根据平台选择打包命令，默认打包当前平台
if [[ "$OSTYPE" == "darwin"* ]]; then
    npm run dist:mac
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    npm run dist:win
else
    npm run dist:linux
fi

echo "🎉 打包流程全部完成！"
echo "📂 安装包位置: $ELECTRON_DIR/release/"
