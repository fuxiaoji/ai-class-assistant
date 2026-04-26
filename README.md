# 🎓 AI Class Assistant (AI 听课助手)

> **实时捕捉课堂灵感，AI 助你成为学霸。**
>
> 这是一个利用 AI 技术实时监听课堂、自动识别问题并生成参考答案的智能助手。无论是面对老师的突击提问，还是需要整理课堂重点，它都能成为你最可靠的"数字大脑"。

---

## 🌟 核心亮点

- **🎙️ 实时语音监听**：基于 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 本地离线 ASR，毫秒级捕捉老师的每一句话，**无需 API Key，完全离线运行**。
- **🧠 智能问题识别**：自动检测老师的提问或语速停顿，智能判断回答时机。
- **📚 知识库增强 (RAG)**：支持上传课件（PDF/DOCX/MD），AI 会结合课程内容给出最精准的回答。
- **⚡ 流式答案生成**：答案实时"蹦出"，无需漫长等待。
- **💻 全平台覆盖**：
  - **网站端**：✅ 已完成。轻量化，随时随地打开即用。
  - **桌面端 (Electron)**：✅ 已完成。支持全局快捷键、窗口置顶，上课更专注。
  - **小程序端**：🔜 规划中。手机在手，听课无忧。

---

## 🛠️ 技术架构

项目采用模块化设计，方便功能剥离与二次开发：


| 层级                 | 技术栈                                                                                           |
| -------------------- | ------------------------------------------------------------------------------------------------ |
| **后端 (Backend)**   | Python 3.11 + FastAPI + WebSocket + uvicorn                                                      |
| **ASR 语音识别**     | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — 本地离线，CPU int8 量化，内置 VAD |
| **LLM 大模型**       | OpenAI 兼容接口（默认 MiniMax，支持 DeepSeek / OpenAI / Moonshot / 智谱 / Qwen）                 |
| **前端 (Frontend)**  | React 18 + Vite + TypeScript + TailwindCSS                                                       |
| **桌面端 (Desktop)** | Electron + IPC 桥接 + 全局快捷键                                                                 |
| **打包 (Build)**     | electron-builder（macOS .dmg）+ PyInstaller（后端二进制）                                        |

---

## 📦 开源依赖致谢

### faster-whisper

> **项目地址**：[https://github.com/SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper)
> **Stars**：22.4k+ | **License**：MIT

本项目的 ASR（自动语音识别）模块基于 **faster-whisper** 实现。faster-whisper 是 OpenAI Whisper 模型的高性能重实现，使用 [CTranslate2](https://github.com/OpenNMT/CTranslate2) 推理引擎，在 CPU 上比原版 Whisper 快 4 倍，内存占用减少 50%，并内置 Silero VAD 静音过滤，非常适合在本地设备上实时运行。

```bash
# 安装 ASR 依赖
pip install faster-whisper

# 首次运行时会自动下载模型（约 500MB，仅需一次）
# 之后完全离线运行，无需任何 API Key
```

可通过环境变量 `WHISPER_MODEL_SIZE` 调整模型大小：

- `tiny`（~75MB）：速度最快，精度较低
- `base`（~145MB）：均衡选择
- `small`（~500MB）：**默认**，精度与速度平衡
- `medium`（~1.5GB）：精度更高，需要更多内存

---

## 🚀 快速开始

本地端 1.0 安装包

下载入口（GitHub）：

- 最新发布页：[`Releases / latest`](https://github.com/fuxiaoji/ai-class-assistant/releases/latest)
- 固定版本页：[`v1.0.0`](https://github.com/fuxiaoji/ai-class-assistant/releases/tag/v1.0.0)

当前构建出的安装包文件（位于 `electron/release/`）：

- `AI听课助手-1.0.0-arm64.dmg`
- `AI听课助手-1.0.0-arm64-mac.zip`
- `AI听课助手-1.0.0.dmg`
- `AI听课助手-1.0.0-mac.zip`

直链下载（GitHub Release Assets）：

- [下载 `AI听课助手-1.0.0-arm64.dmg`](https://github.com/fuxiaoji/ai-class-assistant/releases/download/v1.0.0/AI听课助手-1.0.0-arm64.dmg)
- [下载 `AI听课助手-1.0.0-arm64-mac.zip`](https://github.com/fuxiaoji/ai-class-assistant/releases/download/v1.0.0/AI听课助手-1.0.0-arm64-mac.zip)
- [下载 `AI听课助手-1.0.0.dmg`](https://github.com/fuxiaoji/ai-class-assistant/releases/download/v1.0.0/AI听课助手-1.0.0.dmg)
- [下载 `AI听课助手-1.0.0-mac.zip`](https://github.com/fuxiaoji/ai-class-assistant/releases/download/v1.0.0/AI听课助手-1.0.0-mac.zip)

> 如果点击直链是 `404`，说明该版本的 Release 里还没有上传对应资产文件，需要在 GitHub `Releases` 页面上传后才可下载。

macOS 安装与启动：

```bash
open /Users/Zhuanz1/Desktop/code/helper/electron/release/AI听课助手-1.0.0-arm64.dmg
open -a "/Applications/AI听课助手.app"
```


### 1. 环境准备

确保已安装 Node.js (v18+) 和 Python (3.9+)。

### 2. 后端配置

```bash
cd backend
cp .env.example .env
# 在 .env 中填入你的 LLM_API_KEY（用于 AI 答案生成，ASR 无需 Key）
pip install -r requirements.txt
python main.py
```

后端启动后，**faster-whisper 会在后台自动下载并加载模型**（首次约需 1-2 分钟）。

### 3. 启动应用

**网站端**：

```bash
cd frontend
npm install
npm run dev
```

**桌面端（Electron）**：

```bash
cd electron
npm install
npm run dev
```

### 4. 配置 LLM API Key

打开应用后，点击右上角「⚙️ 课程配置」，在「AI 服务配置」区域填入你的 API Key。

支持快速切换服务商：

- **MiniMax**（默认）：[https://api.minimax.chat/v1](https://api.minimax.chat/v1)
- **DeepSeek**：[https://api.deepseek.com/v1](https://api.deepseek.com/v1)
- **OpenAI**：[https://api.openai.com/v1](https://api.openai.com/v1)
- **Moonshot**：[https://api.moonshot.cn/v1](https://api.moonshot.cn/v1)
- **智谱 GLM**：[https://open.bigmodel.cn/api/paas/v4](https://open.bigmodel.cn/api/paas/v4)
- **通义 Qwen**：[https://dashscope.aliyuncs.com/compatible-mode/v1](https://dashscope.aliyuncs.com/compatible-mode/v1)

---

## ⌨️ 桌面端快捷键


| 快捷键                 | 功能                                       |
| ---------------------- | ------------------------------------------ |
| `Cmd/Ctrl + Shift + L` | **一键监听**：开启/关闭麦克风采集          |
| `Cmd/Ctrl + Shift + H` | **手动求助**：强制 AI 针对当前内容生成答案 |
| `Cmd/Ctrl + Shift + W` | **隐身模式**：快速显示或隐藏助手窗口       |

---

## 📂 项目目录

```text
.
├── backend/            # FastAPI 后端，处理 ASR 与 LLM 逻辑
│   └── app/
│       ├── core/
│       │   ├── asr.py      # faster-whisper 本地离线 ASR
│       │   └── llm.py      # LLM 模块，支持多服务商
│       └── api/
│           └── websocket.py # WebSocket 实时通信
├── frontend/           # React 网站端源码
├── electron/           # Electron 桌面端源码
│   └── src/
│       └── hooks/
│           ├── useAudioCapture.ts  # 麦克风录音 + 发送音频块
│           └── useWebSocket.ts     # WebSocket 连接管理
├── scripts/            # 一键构建与部署脚本
├── docker-compose.yml  # Docker 容器化配置
└── nginx.conf          # 生产环境反向代理配置
```

---

## 🤝 贡献与反馈

欢迎提交 Issue 或 Pull Request 来完善这个项目！

---

**立即开启你的智能听课之旅吧！🚀**
