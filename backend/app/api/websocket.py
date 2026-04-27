"""
WebSocket 路由 - 核心实时通信
处理音频流、ASR 识别、问题检测和 LLM 答案生成
"""
import json
import base64
import logging
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.asr import asr_service
from ..core.llm import llm_service
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
    - audio_chunk: 音频数据块（base64）
    - manual_ask: 手动触发提问
    - config_update: 更新配置
    - ping: 心跳

    服务端消息类型：
    - connected: 连接成功
    - transcript: ASR 识别结果（faster-whisper 本地识别后推送）
    - question_detected: 检测到问题
    - answer_chunk: 答案流式片段
    - answer_done: 答案生成完成
    - error: 错误信息
    - pong: 心跳响应
    """
    await websocket.accept()
    session = session_manager.get_or_create(session_id)
    session.is_listening = False

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

            # ── 心跳 ──────────────────────────────────────────
            if msg_type == "ping":
                await send_json(websocket, {"type": "pong"})

            # ── 配置更新 ──────────────────────────────────────
            elif msg_type == "config_update":
                api_key = msg.get("api_key", "").strip()
                api_base_url = msg.get("api_base_url", "").strip()
                if api_key:
                    llm_service.configure(api_key=api_key, base_url=api_base_url)
                    logger.info(f"LLM API 已配置: base_url={api_base_url or llm_service._base_url}")
                if "system_prompt" in msg:
                    session.system_prompt = msg["system_prompt"]
                if "course_name" in msg:
                    session.course_name = msg["course_name"]
                if "course_materials" in msg:
                    session.course_materials = msg["course_materials"]
                if "asr_language" in msg:
                    language = str(msg.get("asr_language") or "").strip().lower()
                    session.asr_language = language if language else "zh"
                if "translate_enabled" in msg:
                    session.translate_enabled = bool(msg.get("translate_enabled"))
                if "translate_target_lang" in msg:
                    target_lang = str(msg.get("translate_target_lang") or "").strip().lower()
                    session.translate_target_lang = target_lang if target_lang else "en"
                await send_json(websocket, {"type": "config_updated", "message": "配置已更新"})

            # ── 开始/停止监听 ──────────────────────────────────
            elif msg_type == "start_listening":
                session.is_listening = True
                await send_json(websocket, {"type": "listening_started"})

            elif msg_type == "stop_listening":
                session.is_listening = False
                await send_json(websocket, {"type": "listening_stopped"})

            # ── 前端 Web Speech API 识别文字（推荐，无需 OpenAI Key）──
            elif msg_type == "transcript":
                if not session.is_listening:
                    continue
                text = msg.get("text", "").strip()
                is_final = msg.get("is_final", True)
                if not text or not is_final:
                    continue
                translation = None
                if session.translate_enabled:
                    translation = await llm_service.translate_text(
                        text=text,
                        target_lang=session.translate_target_lang,
                        source_lang=session.asr_language,
                    )
                session.add_transcript(text)
                logger.info(f"[ASR-Web] {text}")
                await send_json(websocket, {
                    "type": "transcript",
                    "text": text,
                    "translation": translation,
                    "buffer_length": len(session.transcript_buffer),
                })
                if not session.is_generating:
                    asyncio.create_task(
                        _detect_and_answer(websocket, session, text)
                    )

            # ── 音频数据块（faster-whisper 本地离线识别，无需 API Key）──────
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
                    _process_audio(websocket, session, audio_bytes)
                )

            # ── 手动触发提问 ──────────────────────────────────
            elif msg_type == "manual_ask":
                question = msg.get("question", "").strip()
                if not question:
                    # 使用最近的识别文本作为问题
                    recent = session.get_context()
                    question = " ".join(recent[-3:]) if recent else "请根据课程内容给出总结"

                asyncio.create_task(
                    _generate_answer(websocket, session, question, force=True)
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


async def _detect_and_answer(websocket: WebSocket, session, text: str):
    """问题检测 -> 生成答案（Web Speech API 模式）"""
    try:
        is_question = await llm_service.detect_question(text)
        if is_question:
            await send_json(websocket, {
                "type": "question_detected",
                "text": text
            })
            await _generate_answer(websocket, session, text)
    except Exception as e:
        logger.error(f"问题检测异常: {e}")


async def _process_audio(websocket: WebSocket, session, audio_bytes: bytes):
    """处理音频：ASR 识别 -> 问题检测 -> 生成答案"""
    # ASR 识别
    text = await asr_service.transcribe(audio_bytes, language=session.asr_language)
    if not text:
        return

    translation = None
    if session.translate_enabled:
        translation = await llm_service.translate_text(
            text=text,
            target_lang=session.translate_target_lang,
            source_lang=session.asr_language,
        )

    session.add_transcript(text)

    # 推送识别结果到前端
    await send_json(websocket, {
        "type": "transcript",
        "text": text,
        "translation": translation,
        "buffer_length": len(session.transcript_buffer)
    })

    # 问题检测（如果正在生成答案则跳过）
    if session.is_generating:
        return

    is_question = await llm_service.detect_question(text)
    if is_question:
        await send_json(websocket, {
            "type": "question_detected",
            "text": text
        })
        await _generate_answer(websocket, session, text)


async def _generate_answer(websocket: WebSocket, session, question: str, force: bool = False):
    """流式生成答案并推送到前端"""
    if session.is_generating and not force:
        return

    session.is_generating = True
    full_answer = []

    await send_json(websocket, {
        "type": "answer_start",
        "question": question
    })

    try:
        async for chunk in llm_service.generate_answer_stream(
            question_text=question,
            context_texts=session.get_context(),
            system_prompt=session.system_prompt,
            course_materials=session.course_materials,
            history=session.chat_history,
        ):
            full_answer.append(chunk)
            await send_json(websocket, {
                "type": "answer_chunk",
                "chunk": chunk
            })

        answer_text = "".join(full_answer)
        session.add_chat_turn(question, answer_text)

        await send_json(websocket, {
            "type": "answer_done",
            "full_answer": answer_text
        })

    except Exception as e:
        logger.error(f"答案生成异常: {e}")
        await send_json(websocket, {
            "type": "error",
            "message": f"答案生成失败: {str(e)}"
        })
    finally:
        session.is_generating = False
