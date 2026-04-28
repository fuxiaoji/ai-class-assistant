# AI 听课助手 - 桌面端（Electron）

基于 Electron + React + FastAPI 构建的本地桌面应用，在网站端基础上增加了桌面端专属功能。

## 桌面端专属功能

| 功能 | 说明 |
|------|------|
| **全局快捷键** | 无论焦点在哪个窗口，均可触发 |
| **系统托盘** | 最小化到托盘，不占用任务栏 |
| **窗口置顶** | 上课时保持在最前面 |
| **本地后端** | 内置 FastAPI 服务，无需单独启动 |
| **原生文件对话框** | 直接选择本地课件文件 |

## 全局快捷键

| 快捷键 | 功能 |
|--------|------|
| `Cmd/Ctrl + Shift + L` | 切换开始/停止监听 |
| `Cmd/Ctrl + Shift + H` | 手动触发求助（让 AI 生成答案） |
| `Cmd/Ctrl + Shift + W` | 显示/隐藏窗口 |

## 开发运行

```bash
# 1. 安装依赖
npm install

# 2. 启动后端（在另一个终端）
cd ../backend
pip install -r requirements.txt
cp .env.example .env  # 填写 LLM_API_KEY
uvicorn main:app --port 18765

# 3. 启动 Electron 开发模式
npm run dev
```

## 生产构建

```bash
# 构建前端 + 主进程
npm run build

# 打包为安装包（需要在目标平台上运行）
npm run dist:mac    # macOS (.dmg)
npm run dist:win    # Windows (.exe)
npm run dist:linux  # Linux (.AppImage)
```

## 本地端 1.0.2 安装包

下载入口（GitHub）：

- 最新发布页：[`Releases / latest`](https://github.com/fuxiaoji/ai-class-assistant/releases/latest)
- 固定版本页：[`v1.0.2`](https://github.com/fuxiaoji/ai-class-assistant/releases/tag/v1.0.2)

当前构建出的安装包文件（位于 `electron/release/`）：

- `AI.-1.0.2-arm64.dmg`
- `AI.-1.0.2-arm64-mac.zip`
- `AI.-1.0.2.dmg`
- `AI.-1.0.2-mac.zip`

直链下载（GitHub Release Assets）：

- [下载 `AI.-1.0.2-arm64.dmg`](https://github.com/fuxiaoji/ai-class-assistant/releases/download/v1.0.2/AI.-1.0.2-arm64.dmg)
- [下载 `AI.-1.0.2-arm64-mac.zip`](https://github.com/fuxiaoji/ai-class-assistant/releases/download/v1.0.2/AI.-1.0.2-arm64-mac.zip)
- [下载 `AI.-1.0.2.dmg`](https://github.com/fuxiaoji/ai-class-assistant/releases/download/v1.0.2/AI.-1.0.2.dmg)
- [下载 `AI.-1.0.2-mac.zip`](https://github.com/fuxiaoji/ai-class-assistant/releases/download/v1.0.2/AI.-1.0.2-mac.zip)

> 如果点击直链是 `404`，说明该版本的 Release 里还没有上传对应资产文件，需要在 GitHub `Releases` 页面上传后才可下载。

macOS 安装与启动：

```bash
open /Users/Zhuanz1/Desktop/code/helper/electron/release/AI听课助手-1.0.2-arm64.dmg
open -a "/Applications/AI听课助手.app"
```

## 项目结构

```
electron/
├── src-electron/          # Electron 主进程（Node.js 环境）
│   ├── main.ts            # 主进程入口：窗口、托盘、快捷键、IPC
│   └── preload.ts         # 预加载脚本：安全桥接主进程与渲染进程
├── src/                   # 渲染进程（React + TypeScript）
│   ├── utils/electron.ts  # Electron API 封装（优雅降级）
│   ├── components/
│   │   └── ElectronToolbar.tsx  # 桌面端专属工具栏
│   └── ...                # 其余组件复用自网站端
├── scripts/
│   └── package-backend.sh # 将 Python 后端打包为可执行文件
├── dist/                  # 前端构建产物
├── dist-electron/         # 主进程编译产物
└── release/               # 最终安装包输出目录
```

## 架构说明

```
┌─────────────────────────────────────────────┐
│              Electron 应用                   │
│                                             │
│  ┌─────────────────┐  ┌──────────────────┐  │
│  │   主进程 (Node)  │  │ 渲染进程 (React) │  │
│  │                 │  │                  │  │
│  │ • 窗口管理      │◄─►│ • UI 界面        │  │
│  │ • 系统托盘      │IPC│ • 音频采集       │  │
│  │ • 全局快捷键    │  │ • WebSocket      │  │
│  │ • 后端进程管理  │  │ • 状态管理       │  │
│  └────────┬────────┘  └──────────────────┘  │
│           │                                 │
│           ▼                                 │
│  ┌─────────────────┐                        │
│  │  FastAPI 后端   │                        │
│  │  (子进程)       │                        │
│  │ Port: 18765     │                        │
│  └─────────────────┘                        │
└─────────────────────────────────────────────┘
```
