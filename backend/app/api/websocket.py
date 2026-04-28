"""
WebSocket 路由 - 核心实时通信
处理音频流、ASR 识别、问题检测和 LLM 答案生成

修复记录：
  - 增加详细日志，便于调试 ASR 识别流程
  - 翻译使用 asyncio.create_task 并行执行，不阻塞字幕显示
  - 音频块接收后立即推送到识别队列，识别完成立即推送字幕
"""
import json
import base64
import logging
import asyncio
import time
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


async def _translate_and_send(websocket: WebSocket, text: str, transcript_id: str, session):
    """并行翻译并推送结果（不阻塞字幕显示）"""
    if not session.translate_enabled:
        return
    try:
        translation = await llm_service.translate_text(
            text=text,
            target_lang=session.translate_target_lang,
            source_lang=session.asr_language,
        )
        if not translation:
            return
        await send_json(websocket, {
            "type": "transcript_translation",
            "id": transcript_id,
            "translation": translation,
        })
        logger.debug(f"[翻译] {transcript_id}: {translation[:50]}")
    except Exception as e:
        logger.warning(f"[翻译] 翻译任务异常: {e}")


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket 主端点

    客户端消息类型：
    - audio_chunk: 音频数据块（base64，WebM/Opus 格式）
    - transcript: 前端 Web Speech API 识别结果（直接文字，推荐）
    - manual_ask: 手动触发提问
    - config_update: 更新配置
    - start_listening / stop_listening: 控制监听状态
    - clear_history: 清空历史
    - ping: 心跳

    服务端消息类型：
    - connected: 连接成功
    - transcript: ASR 识别结果（立即推送，不等翻译）
    - transcript_translation: 翻译结果（并行推送）
    - question_detected: 检测到问题
    - answer_start / answer_chunk / answer_done: 流式答案
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
                    logger.info(f"ASR 语言设置: {session.asr_language}")
                if "translate_enabled" in msg:
                    session.translate_enabled = bool(msg.get("translate_enabled"))
                    logger.info(f"翻译功能: {'开启' if session.translate_enabled else '关闭'}")
                if "translate_target_lang" in msg:
                    target_lang = str(msg.get("translate_target_lang") or "").strip().lower()
                    session.translate_target_lang = target_lang if target_lang else "en"
                await send_json(websocket, {"type": "config_updated", "message": "配置已更新"})

            # ── 开始/停止监听 ──────────────────────────────────
            elif msg_type == "start_listening":
                session.is_listening = True
                logger.info(f"[{session_id[:8]}] 开始监听")
                await send_json(websocket, {"type": "listening_started"})

            elif msg_type == "stop_listening":
                session.is_listening = False
                logger.info(f"[{session_id[:8]}] 停止监听")
                await send_json(websocket, {"type": "listening_stopped"})

            # ── 前端 Web Speech API 识别文字（推荐，低延迟）──
            elif msg_type == "transcript":
                if not session.is_listening:
                    continue
                text = msg.get("text", "").strip()
                is_final = msg.get("is_final", True)
                if not text:
                    continue
                
                transcript_id = f"t-{int(time.time() * 1000)}"
                
                # 中间结果也立即推送（is_final=False 时作为临时字幕）
                await send_json(websocket, {
                    "type": "transcript",
                    "id": transcript_id,
                    "text": text,
                    "is_final": is_final,
                    "buffer_length": len(session.transcript_buffer),
                })
                
                if is_final:
                    session.add_transcript(text)
                    logger.info(f"[WebSpeech] 最终结果: {text[:60]}")
                    # 并行翻译（不阻塞主流程）
                    asyncio.create_task(_translate_and_send(websocket, text, transcript_id, session))
                    # 问题检测
                    if not session.is_generating:
                        asyncio.create_task(
                            _detect_and_answer(websocket, session, text)
                        )
                else:
                    logger.debug(f"[WebSpeech] 中间结果: {text[:40]}")

            # ── 音频数据块（faster-whisper 本地离线识别）──────
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

                logger.debug(f"[AudioChunk] 收到音频块: {len(audio_bytes)} bytes")
                
                # 异步 ASR 识别（不阻塞消息接收循环）
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
            logger.info(f"[问题检测] 检测到问题: {text[:50]}")
            await send_json(websocket, {
                "type": "question_detected",
                "text": text
            })
            await _generate_answer(websocket, session, text)
    except Exception as e:
        logger.error(f"问题检测异常: {e}")


async def _process_audio(websocket: WebSocket, session, audio_bytes: bytes):
    """
    处理音频块：
    1. faster-whisper ASR 识别（PyAV 先转换格式）
    2. 立即推送识别结果到前端（不等翻译）
    3. 并行执行翻译
    4. 问题检测 -> 生成答案
    """
    # ASR 识别（在线程池中执行，不阻塞事件循环）
    text = await asr_service.transcribe(audio_bytes, language=session.asr_language)
    if not text:
        logger.debug("[ASR] 无识别结果（静音或识别失败）")
        return

    transcript_id = f"t-{int(time.time() * 1000)}"
    session.add_transcript(text)

    # 立即推送识别结果到前端（字幕立即显示）
    await send_json(websocket, {
        "type": "transcript",
        "id": transcript_id,
        "text": text,
        "is_final": True,
        "buffer_length": len(session.transcript_buffer)
    })
    logger.info(f"[ASR] 推送字幕: {text[:60]}")

    # 并行翻译（不阻塞字幕显示）
    asyncio.create_task(_translate_and_send(websocket, text, transcript_id, session))

    # 问题检测（如果正在生成答案则跳过）
    if session.is_generating:
        return

    is_question = await llm_service.detect_question(text)
    if is_question:
        logger.info(f"[问题检测] 检测到问题: {text[:50]}")
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
