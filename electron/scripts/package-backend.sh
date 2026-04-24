#!/bin/bash
# ============================================================
# 将 Python 后端打包为独立可执行文件（使用 PyInstaller）
# 打包后放入 backend-bin/ 目录，随 Electron 应用一起分发
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ELECTRON_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$(dirname "$ELECTRON_DIR")/backend"
OUTPUT_DIR="$ELECTRON_DIR/backend-bin"

echo "🐍 打包 Python 后端..."
echo "后端目录: $BACKEND_DIR"
echo "输出目录: $OUTPUT_DIR"

# 检查 PyInstaller
if ! command -v pyinstaller &> /dev/null; then
  echo "安装 PyInstaller..."
  pip3 install pyinstaller
fi

# 安装后端依赖
cd "$BACKEND_DIR"
pip3 install -r requirements.txt

# 清理旧的打包产物
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# 使用 PyInstaller 打包
pyinstaller \
  --onefile \
  --name "ai-class-backend" \
  --distpath "$OUTPUT_DIR" \
  --workpath "$BACKEND_DIR/build" \
  --specpath "$BACKEND_DIR" \
  --hidden-import="uvicorn.logging" \
  --hidden-import="uvicorn.loops" \
  --hidden-import="uvicorn.loops.auto" \
  --hidden-import="uvicorn.protocols" \
  --hidden-import="uvicorn.protocols.http" \
  --hidden-import="uvicorn.protocols.http.auto" \
  --hidden-import="uvicorn.protocols.websockets" \
  --hidden-import="uvicorn.protocols.websockets.auto" \
  --hidden-import="uvicorn.lifespan" \
  --hidden-import="uvicorn.lifespan.on" \
  --hidden-import="fastapi" \
  --hidden-import="openai" \
  --add-data "app:app" \
  "$BACKEND_DIR/main.py"

echo ""
echo "✅ 后端打包完成: $OUTPUT_DIR/ai-class-backend"
echo ""
echo "注意：打包后的可执行文件需要系统环境变量 LLM_API_KEY"
