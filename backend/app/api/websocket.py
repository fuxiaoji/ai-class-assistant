"""
WebSocket 路由 - 核心实时通信
终极稳定版：
  - 修复增量提取算法：使用更稳健的后缀匹配
  - 增加 ASR 任务顺序保证
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
    """并行翻译并推送结果"""
    if not session.translate_enabled:
        return
    try:
        translation = await llm_service.translate_text(
            text=text,
            target_lang=session.translate_target_lang,
            source_lang=session.asr_language,
        )
        if translation:
            await send_json(websocket, {
                "type": "transcript_translation",
                "id": transcript_id,
                "translation": translation,
            })
    except Exception as e:
        logger.warning(f"[翻译] 异常: {e}")


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket 主端点"""
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
            except:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await send_json(websocket, {"type": "pong"})

            elif msg_type == "config_update":
                api_key = msg.get("api_key", "").strip()
                api_base_url = msg.get("api_base_url", "").strip()
                if api_key:
                    llm_service.configure(api_key=api_key, base_url=api_base_url)
                if "asr_language" in msg:
                    session.asr_language = str(msg.get("asr_language") or "zh").strip().lower()
                if "translate_enabled" in msg:
                    session.translate_enabled = bool(msg.get("translate_enabled"))
                if "translate_target_lang" in msg:
                    session.translate_target_lang = str(msg.get("translate_target_lang") or "en").strip().lower()
                await send_json(websocket, {"type": "config_updated", "message": "配置已更新"})

            elif msg_type == "start_listening":
                session.is_listening = True
                logger.info(f"[{session_id[:8]}] 开始监听")
                await send_json(websocket, {"type": "listening_started"})

            elif msg_type == "stop_listening":
                session.is_listening = False
                asr_service.clear_session(session_id)
                logger.info(f"[{session_id[:8]}] 停止监听")
                await send_json(websocket, {"type": "listening_stopped"})

            elif msg_type == "transcript":
                if not session.is_listening: continue
                text = msg.get("text", "").strip()
                is_final = msg.get("is_final", True)
                if not text: continue
                transcript_id = f"t-{int(time.time() * 1000)}"
                await send_json(websocket, {"type": "transcript", "id": transcript_id, "text": text, "is_final": is_final})
                if is_final:
                    session.add_transcript(text)
                    asyncio.create_task(_translate_and_send(websocket, text, transcript_id, session))

            elif msg_type == "audio_chunk":
                if not session.is_listening: continue
                audio_b64 = msg.get("data", "")
                chunk_index = msg.get("chunk_index", 0)
                if not audio_b64: continue
                try:
                    audio_bytes = base64.b64decode(audio_b64)
                    # 注意：transcribe 内部已有锁，这里可以直接 create_task
                    asyncio.create_task(_process_audio(websocket, session, session_id, audio_bytes, chunk_index))
                except:
                    continue

            elif msg_type == "manual_ask":
                question = msg.get("question", "").strip()
                asyncio.create_task(_generate_answer(websocket, session, question, force=True))

            elif msg_type == "clear_history":
                session.transcript_buffer.clear()
                asr_service.clear_session(session_id)
                await send_json(websocket, {"type": "history_cleared"})

    except WebSocketDisconnect:
        session.is_listening = False
        asr_service.clear_session(session_id)
    except Exception as e:
        logger.error(f"WebSocket 异常: {e}")


async def _process_audio(websocket: WebSocket, session, session_id: str, audio_bytes: bytes, chunk_index: int = 0):
    """处理音频块并推送增量字幕"""
    text = await asr_service.transcribe(audio_bytes, session_id=session_id, chunk_index=chunk_index, language=session.asr_language)
    
    if not text:
        return

    # 增量提取算法优化
    full_history = "".join(session.transcript_buffer)
    
    if not full_history:
        display_text = text
    else:
        # 寻找 text 中与 full_history 结尾重合的最长部分
        # 比如历史 "...今天天气"，当前识别 "今天天气不错" -> 匹配 "今天天气"，新增 "不错"
        max_overlap = 0
        for i in range(min(len(full_history), len(text), 50), 0, -1):
            if text.startswith(full_history[-i:]):
                max_overlap = i
                break
        
        if max_overlap > 0:
            display_text = text[max_overlap:].strip()
        else:
            # 如果完全没重合，可能是识别结果跳变，或者历史太长被滑动窗口切掉了
            # 这种情况下，我们只取 text 的后半部分，或者如果 text 较短就全取
            if len(text) > 20:
                display_text = text[-15:].strip()
            else:
                display_text = text
    
    if not display_text:
        return

    session.add_transcript(display_text)
    transcript_id = f"t-{chunk_index}-{int(time.time() * 1000)}"

    await send_json(websocket, {
        "type": "transcript",
        "id": transcript_id,
        "text": display_text,
        "is_final": True,
        "chunk_index": chunk_index
    })
    logger.info(f"[ASR] 块 #{chunk_index} 推送增量字幕: {display_text}")

    # 并行翻译
    asyncio.create_task(_translate_and_send(websocket, display_text, transcript_id, session))

    # 问题检测
    if not session.is_generating:
        asyncio.create_task(_detect_and_answer(websocket, session, display_text))


async def _detect_and_answer(websocket: WebSocket, session, text: str):
    """问题检测 -> 生成答案"""
    try:
        is_question = await llm_service.detect_question(text)
        if is_question:
            logger.info(f"[问题检测] 检测到问题: {text[:50]}")
            await send_json(websocket, {"type": "question_detected", "text": text})
            await _generate_answer(websocket, session, text)
    except Exception as e:
        logger.error(f"问题检测异常: {e}")


async def _generate_answer(websocket: WebSocket, session, question: str, force: bool = False):
    """流式生成答案"""
    if session.is_generating and not force: return
    session.is_generating = True
    await send_json(websocket, {"type": "answer_start", "question": question})
    try:
        full_answer = []
        async for chunk in llm_service.generate_answer_stream(question, session.get_context(), session.system_prompt, session.course_materials, session.chat_history):
            full_answer.append(chunk)
            await send_json(websocket, {"type": "answer_chunk", "chunk": chunk})
        session.add_chat_turn(question, "".join(full_answer))
        await send_json(websocket, {"type": "answer_done"})
    finally:
        session.is_generating = False
