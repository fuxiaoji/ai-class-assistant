"""
WebSocket 路由 - 核心实时通信
处理音频流、ASR 识别、问题检测和 LLM 答案生成
支持动态 API 配置（从前端传入）
"""
import json
import base64
import logging
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..core.asr import asr_service
from ..core.llm import LLMService
from ..services.session_service import session_manager

logger = logging.getLogger(__name__)
router = APIRouter()

async def send_json(ws: WebSocket, data: dict):
    """安全发送 JSON 消息"""
    try:
        await ws.send_text(json.dumps(data, ensure_ascii=False))
    except Exception as e:
        logger.debug(f"发送消息失败: {e}")

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket 主端点
    客户端消息类型：
    - audio_chunk: 音频数据块（base64）+ api_key + api_base_url
    - manual_ask: 手动触发提问
    - config_update: 更新配置 + api_key + api_base_url
    - ping: 心跳
    服务端消息类型：
    - connected: 连接成功
    - transcript: ASR 识别结果
    - question_detected: 检测到问题
    - answer_chunk: 答案流式片段
    - answer_done: 答案生成完成
    - error: 错误信息
    - pong: 心跳响应
    """
    await websocket.accept()
    session = session_manager.get_or_create(session_id)
    session.is_listening = False
    
    # 存储当前连接的 API 配置
    current_api_key = None
    current_api_base_url = None
    
    logger.info(f"WebSocket 已连接: {session_id}")
    await send_json(websocket, {
        "type": "connected",
        "session_id": session_id,
        "message": "连接成功，准备就绪"
    })
    
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await send_json(websocket, {"type": "error", "message": "无效的 JSON 格式"})
                continue
            
            msg_type = msg.get("type", "")
            
            # 从消息中提取 API 配置（如果有）
            if "api_key" in msg:
                current_api_key = msg.get("api_key")
            if "api_base_url" in msg:
                current_api_base_url = msg.get("api_base_url")
            
            # ── 心跳 ──────────────────────────────────────────
            if msg_type == "ping":
                await send_json(websocket, {"type": "pong"})
            
            # ── 配置更新 ──────────────────────────────────────
            elif msg_type == "config_update":
                if "system_prompt" in msg:
                    session.system_prompt = msg["system_prompt"]
                if "course_name" in msg:
                    session.course_name = msg["course_name"]
                if "course_materials" in msg:
                    session.course_materials = msg["course_materials"]
                await send_json(websocket, {"type": "config_updated", "message": "配置已更新"})
            
            # ── 开始/停止监听 ──────────────────────────────────
            elif msg_type == "start_listening":
                session.is_listening = True
                await send_json(websocket, {"type": "listening_started"})
            elif msg_type == "stop_listening":
                session.is_listening = False
                await send_json(websocket, {"type": "listening_stopped"})
            
            # ── 音频数据块 ────────────────────────────────────
            elif msg_type == "audio_chunk":
                if not session.is_listening:
                    continue
                audio_b64 = msg.get("data", "")
                if not audio_b64:
                    continue
                try:
                    audio_bytes = base64.b64decode(audio_b64)
                except Exception:
                    await send_json(websocket, {"type": "error", "message": "音频数据解码失败"})
                    continue
                
                # 异步 ASR 识别
                asyncio.create_task(
                    _process_audio(websocket, session, audio_bytes, current_api_key, current_api_base_url)
                )
            
            # ── 手动触发提问 ──────────────────────────────────
            elif msg_type == "manual_ask":
                question = msg.get("question", "").strip()
                if not question:
                    # 使用最近的识别文本作为问题
                    recent = session.get_context()
                    question = " ".join(recent[-3:]) if recent else "请根据课程内容给出总结"
                asyncio.create_task(
                    _generate_answer(websocket, session, question, current_api_key, current_api_base_url, force=True)
                )
            
            # ── 清空历史 ──────────────────────────────────────
            elif msg_type == "clear_history":
                session.transcript_buffer.clear()
                session.full_transcript.clear()
                session.chat_history.clear()
                await send_json(websocket, {"type": "history_cleared"})
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket 断开: {session_id}")
        session.is_listening = False
    except Exception as e:
        logger.error(f"WebSocket 异常 {session_id}: {e}")
        await send_json(websocket, {"type": "error", "message": str(e)})

async def _process_audio(websocket: WebSocket, session, audio_bytes: bytes, api_key: str = None, api_base_url: str = None):
    """处理音频：ASR 识别 -> 问题检测 -> 生成答案"""
    # ASR 识别
    text = await asr_service.transcribe(audio_bytes)
    if not text:
        return
    
    session.add_transcript(text)
    
    # 推送识别结果到前端
    await send_json(websocket, {
        "type": "transcript",
        "text": text,
        "timestamp": session.full_transcript[-1]["timestamp"] if session.full_transcript else 0
    })
    
    # 问题检测
    try:
        llm_service = LLMService(api_key=api_key, api_base_url=api_base_url)
        is_question = await llm_service.detect_question(text)
        
        if is_question:
            await send_json(websocket, {"type": "question_detected", "text": text})
            # 自动生成答案
            await _generate_answer(websocket, session, text, api_key, api_base_url)
    except Exception as e:
        logger.error(f"问题检测失败: {e}")
        await send_json(websocket, {"type": "error", "message": f"问题检测失败: {str(e)}"})

async def _generate_answer(websocket: WebSocket, session, question: str, api_key: str = None, api_base_url: str = None, force: bool = False):
    """生成答案（流式）"""
    try:
        llm_service = LLMService(api_key=api_key, api_base_url=api_base_url)
        
        # 发送答案开始信号
        answer_id = f"ans-{len(session.chat_history)}"
        await send_json(websocket, {
            "type": "answer_start",
            "question": question,
            "answer_id": answer_id
        })
        
        # 流式生成答案
        full_answer = ""
        async for chunk in llm_service.generate_answer_stream(
            question_text=question,
            context_texts=session.get_context(),
            system_prompt=session.system_prompt,
            course_materials=session.course_materials,
            history=session.chat_history[-10:] if session.chat_history else None,
        ):
            full_answer += chunk
            await send_json(websocket, {
                "type": "answer_chunk",
                "chunk": chunk,
                "answer_id": answer_id
            })
        
        # 答案生成完成
        await send_json(websocket, {
            "type": "answer_done",
            "full_answer": full_answer,
            "answer_id": answer_id
        })
        
        # 保存到聊天历史
        session.chat_history.append({"role": "user", "content": question})
        session.chat_history.append({"role": "assistant", "content": full_answer})
        
    except ValueError as e:
        # API Key 未配置
        await send_json(websocket, {
            "type": "error",
            "message": f"API 配置错误: {str(e)}"
        })
    except Exception as e:
        logger.error(f"答案生成失败: {e}")
        await send_json(websocket, {
            "type": "error",
            "message": f"答案生成失败: {str(e)}"
        })
