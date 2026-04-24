#!/bin/bash
# ============================================================
# AI 实时听课助手 - 一键构建脚本
# 构建前端并准备部署包
# ============================================================
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/deploy"

echo "🔨 开始构建 AI 听课助手..."
echo "项目根目录: $ROOT_DIR"

# 1. 构建前端
echo ""
echo "📦 [1/2] 构建前端..."
cd "$ROOT_DIR/frontend"
npm install --silent
npm run build
echo "✓ 前端构建完成 -> frontend/dist/"

# 2. 准备部署包
echo ""
echo "📁 [2/2] 准备部署包..."
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

# 复制前端构建产物
cp -r "$ROOT_DIR/frontend/dist" "$DIST_DIR/frontend"

# 复制后端
cp -r "$ROOT_DIR/backend" "$DIST_DIR/backend"
rm -rf "$DIST_DIR/backend/__pycache__" "$DIST_DIR/backend/**/__pycache__"
rm -rf "$DIST_DIR/backend/uploads" "$DIST_DIR/backend/vector_store"

# 复制配置文件
cp "$ROOT_DIR/README.md" "$DIST_DIR/"

echo ""
echo "✅ 构建完成！"
echo ""
echo "部署包位置: $DIST_DIR"
echo ""
echo "部署说明："
echo "  前端: 将 deploy/frontend/ 目录上传到服务器的网站根目录"
echo "  后端: 在服务器上运行 deploy/backend/ 中的 FastAPI 服务"
echo ""
echo "后端启动命令："
echo "  cd deploy/backend"
echo "  pip install -r requirements.txt"
echo "  cp .env.example .env  # 填写 API Key"
echo "  uvicorn main:app --host 0.0.0.0 --port 8000"
