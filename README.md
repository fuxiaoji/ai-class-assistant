# 🎓 AI Class Assistant (AI 听课助手)

> **实时捕捉课堂灵感，AI 助你成为学霸。**
> 
> 这是一个利用 AI 技术实时监听课堂、自动识别问题并生成参考答案的智能助手。无论是面对老师的突击提问，还是需要整理课堂重点，它都能成为你最可靠的“数字大脑”。

---

## 🌟 核心亮点

- **🎙️ 实时语音监听**：基于 Whisper ASR 技术，毫秒级捕捉老师的每一句话。
- **🧠 智能问题识别**：自动检测老师的提问或语速停顿，智能判断回答时机。
- **📚 知识库增强 (RAG)**：支持上传课件（PDF/DOCX/MD），AI 会结合课程内容给出最精准的回答。
- **⚡ 流式答案生成**：答案实时“蹦出”，无需漫长等待。
- **💻 全平台覆盖**：
  - **网站端**：✅ 已完成。轻量化，随时随地打开即用。
  - **桌面端 (Electron)**：✅ 已完成。支持全局快捷键、窗口置顶，上课更专注。
  - **小程序端**：🔜 规划中。手机在手，听课无忧。

---

## 🛠️ 技术架构

项目采用模块化设计，方便功能剥离与二次开发：

- **后端 (Backend)**: Python 3.11 + FastAPI + WebSocket + OpenAI/DeepSeek API
- **前端 (Frontend)**: React 19 + Vite + TypeScript + TailwindCSS
- **桌面端 (Desktop)**: Electron + IPC 桥接 + 全局快捷键
- **部署 (DevOps)**: Docker Compose + Nginx 反向代理

---

## 🚀 快速开始

### 1. 环境准备
确保已安装 Node.js (v18+) 和 Python (3.9+)。

### 2. 后端配置
```bash
cd backend
cp .env.example .env
# 在 .env 中填入你的 LLM_API_KEY
pip install -r requirements.txt
python main.py
```

### 3. 启动应用
- **网站端**:
  ```bash
  cd frontend
  npm install
  npm run dev
  ```
- **桌面端**:
  ```bash
  cd electron
  npm install
  npm run dev
  ```

---

## ⌨️ 桌面端快捷键

| 快捷键 | 功能 |
|--------|------|
| `Cmd/Ctrl + Shift + L` | **一键监听**：开启/关闭麦克风采集 |
| `Cmd/Ctrl + Shift + H` | **手动求助**：强制 AI 针对当前内容生成答案 |
| `Cmd/Ctrl + Shift + W` | **隐身模式**：快速显示或隐藏助手窗口 |

---

## 📂 项目目录

```text
.
├── backend/            # FastAPI 后端，处理 ASR 与 LLM 逻辑
├── frontend/           # React 网站端源码
├── electron/           # Electron 桌面端源码
├── scripts/            # 一键构建与部署脚本
├── docker-compose.yml  # Docker 容器化配置
└── nginx.conf          # 生产环境反向代理配置
```

---

## 🤝 贡献与反馈

欢迎提交 Issue 或 Pull Request 来完善这个项目！
如有疑问，请访问 [Manus](https://manus.im) 获取更多 AI 开发支持。

---

**立即开启你的智能听课之旅吧！🚀**
