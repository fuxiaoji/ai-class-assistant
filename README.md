# AI 实时听课助手 (AI Class Assistant)

实时监听课堂音频，智能识别教师提问，结合预设课件和提示词，通过 LLM 为学生即时生成参考答案。

## 项目结构

```
ai-class-assistant/
├── backend/          # Python FastAPI 后端
│   ├── app/
│   │   ├── api/      # REST & WebSocket 路由
│   │   ├── core/     # 配置、LLM、ASR 核心模块
│   │   ├── models/   # 数据模型
│   │   └── services/ # 业务逻辑服务
│   ├── requirements.txt
│   └── main.py
├── frontend/         # React + Vite + TailwindCSS 前端
│   ├── src/
│   │   ├── components/  # 可复用组件
│   │   ├── hooks/       # 自定义 Hooks（音频、WebSocket）
│   │   ├── pages/       # 页面
│   │   ├── services/    # API 调用封装
│   │   └── store/       # 全局状态
│   └── package.json
└── README.md
```

## 功能特性

- 🎤 **实时音频采集**：浏览器麦克风 + VAD 语音活动检测
- 🔤 **语音识别 (ASR)**：接入 OpenAI Whisper API
- 🤖 **智能问答**：LLM 结合预设课件和提示词生成答案
- 📚 **课件管理**：支持上传 PDF/文本课件，构建知识库
- ⚙️ **Prompt 预设**：可自定义系统提示词和课程背景
- 📡 **流式输出**：答案打字机效果实时展示

## 快速开始

### 后端
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # 填写 API Key
uvicorn main:app --reload --port 8000
```

### 前端
```bash
cd frontend
npm install
npm run dev
```

### 生产构建
```bash
cd frontend && npm run build
# dist/ 目录即为可部署的静态文件
```

## 部署说明

前端构建产物（`frontend/dist/`）为纯静态文件，可直接上传至个人服务器的网站目录。
后端需要 Python 3.9+ 环境，建议使用 `gunicorn + uvicorn` 部署。

## 平台规划

| 阶段 | 平台 | 状态 |
|------|------|------|
| 1 | 网站端 (Web) | ✅ 开发中 |
| 2 | 本地端 (Electron) | 🔜 规划中 |
| 3 | 小程序端 (WeChat) | 🔜 规划中 |
