"""
WebSocket 端点 — 稳定版
- ASR 队列化顺序处理，防止乱序
- 增量文本提取：用 _session_last_full_text 记录上次 ASR 完整输出，精准对比
- 翻译并行执行
- 提问检测：每 3 条字幕检测一次，避免 LLM 调用过频
- 手动提问：manual_ask 消息直接触发 AI 回答
"""

import asyncio
import base64
import json
import logging
import time
from typing import Dict

from fastapi import APIRouter
from starlette.websockets import WebSocket, WebSocketDisconnect

from ..core.asr import asr_service
from ..core.llm import llm_service
from ..services.session_service import session_manager

logger = logging.getLogger(__name__)
router = APIRouter()

# 每个会话的 ASR 队列和 worker
_session_queues: Dict[str, asyncio.Queue] = {}
_session_workers: Dict[str, asyncio.Task] = {}

# 每个会话最后一次 ASR 输出的完整文本（用于增量对比）
_session_last_full_text: Dict[str, str] = {}

# 每个会话已推送的字幕计数（用于控制提问检测频率）
_session_transcript_count: Dict[str, int] = {}


async def send_json(websocket: WebSocket, data: dict):
    try:
        await websocket.send_text(json.dumps(data, ensure_ascii=False))
    except Exception as e:
        logger.debug(f"发送消息失败: {e}")


def _extract_new_text(full_text: str, last_full_text: str) -> str:
    """
    从 full_text 中提取相对于 last_full_text 的新增内容。
    
    last_full_text 是上一次 ASR 输出的完整文本（不是增量拼接）。
    这样对比更精准，不会出现格式不匹配的问题。
    
    策略（按优先级）：
    1. 如果 last_full_text 是 full_text 的前缀 → 截取后面的部分
    2. 如果 full_text 已经包含在 last_full_text 中 → 返回空（重复）
    3. 找到 full_text 与 last_full_text 末尾的最长公共后缀 → 截取其后的部分
    4. 在 full_text 中查找 last_full_text 末尾片段 → 截取其后的内容
    5. 否则返回 full_text（全新内容）
    """
    full_text = full_text.strip()
    last_full_text = last_full_text.strip()

    if not last_full_text:
        return full_text

    if not full_text:
        return ""

    # 策略 2：full_text 完全包含在 last_full_text 中（重复）
    if full_text in last_full_text:
        return ""

    # 策略 1：last_full_text 是 full_text 的前缀
    if full_text.startswith(last_full_text):
        return full_text[len(last_full_text):].strip()

    # 策略 3：找到 full_text 与 last_full_text 末尾的最长公共后缀匹配
    check_len = min(len(last_full_text), len(full_text), 300)
    for i in range(check_len, 4, -1):  # 至少匹配5个字符
        suffix = last_full_text[-i:].strip()
        if not suffix:
            continue
        if full_text.startswith(suffix):
            new_part = full_text[len(suffix):].strip()
            if new_part:
                return new_part

    # 策略 4：在 full_text 中查找 last_full_text 末尾片段（最多50个字符）
    tail = last_full_text[-50:].strip()
    if tail and tail in full_text:
        pos = full_text.rfind(tail)
        candidate = full_text[pos + len(tail):].strip()
        if candidate:
            return candidate

    # 策略 5：全新内容，直接返回
    return full_text


async def _asr_worker(session_id: str, websocket: WebSocket, session):
    """
    ASR 工作协程：从队列中取出音频块，顺序处理，推送字幕。
    """
    queue = _session_queues[session_id]
    loop = asyncio.get_event_loop()

    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=30)
        except asyncio.TimeoutError:
            continue

        if item is None:
            # 停止信号
            queue.task_done()
            break

        audio_bytes, chunk_index = item

        try:
            # 在线程池中运行同步 ASR（不阻塞事件循环）
            text = await loop.run_in_executor(
                None,
                lambda: asr_service.transcribe_sync(
                    audio_bytes,
                    session_id=session_id,
                    chunk_index=chunk_index,
                    language=session.asr_language,
                )
            )

            if text:
                # 增量提取：用上次 ASR 完整输出作为 history
                last_full = _session_last_full_text.get(session_id, "")
                new_text = _extract_new_text(text, last_full)

                # 更新最后一次完整文本
                _session_last_full_text[session_id] = text

                if new_text:
                    session.add_transcript(new_text)
                    transcript_id = f"t-{chunk_index}-{int(time.time() * 1000)}"
                    count = _session_transcript_count.get(session_id, 0) + 1
                    _session_transcript_count[session_id] = count

                    await send_json(websocket, {
                        "type": "transcript",
                        "id": transcript_id,
                        "text": new_text,
                        "is_final": True,
                        "chunk_index": chunk_index,
                    })
                    logger.info(f"[WS] 块 #{chunk_index} 推送字幕: {new_text[:60]}...")

                    # 并行翻译
                    asyncio.create_task(_translate_and_send(websocket, new_text, transcript_id, session))

                    # 提问检测：每 3 条字幕检测一次，避免 LLM 调用过频
                    if not session.is_generating and count % 3 == 0:
                        asyncio.create_task(_detect_and_answer(websocket, session, new_text))
                else:
                    logger.debug(f"[WS] 块 #{chunk_index} 无新增内容，跳过推送")
            else:
                logger.debug(f"[WS] 块 #{chunk_index} 识别结果为空")

        except Exception as e:
            logger.error(f"[WS] ASR 处理异常 (块 #{chunk_index}): {e}")
        finally:
            queue.task_done()


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
            logger.info(f"[翻译] 推送: {translation[:60]}...")
    except Exception as e:
        logger.warning(f"[翻译] 异常: {e}")


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket 主端点"""
    await websocket.accept()
    session = session_manager.get_or_create(session_id)
    session.is_listening = False

    # 创建该会话的 ASR 队列和 worker
    _session_queues[session_id] = asyncio.Queue()
    worker_task = asyncio.create_task(_asr_worker(session_id, websocket, session))
    _session_workers[session_id] = worker_task

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
            except Exception:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "config_update":
                api_key = msg.get("api_key", "")
                api_base_url = msg.get("api_base_url", "")
                if api_key:
                    llm_service.configure(api_key=api_key, base_url=api_base_url)
                session.asr_language = msg.get("asr_language", session.asr_language)
                session.translate_enabled = msg.get("translate_enabled", session.translate_enabled)
                session.translate_target_lang = msg.get("translate_target_lang", session.translate_target_lang)
                session.system_prompt = msg.get("system_prompt", session.system_prompt)
                session.course_materials = msg.get("course_materials", session.course_materials)
                await send_json(websocket, {"type": "config_updated"})

            elif msg_type == "start_listening":
                session.is_listening = True
                # 重置增量状态
                _session_last_full_text[session_id] = ""
                _session_transcript_count[session_id] = 0
                asr_service.clear_session(session_id)
                logger.info(f"[{session_id[:8]}] 开始监听")
                await send_json(websocket, {"type": "listening_started"})

            elif msg_type == "stop_listening":
                session.is_listening = False
                asr_service.clear_session(session_id)
                _session_last_full_text.pop(session_id, None)
                _session_transcript_count.pop(session_id, None)
                logger.info(f"[{session_id[:8]}] 停止监听")
                await send_json(websocket, {"type": "listening_stopped"})

            elif msg_type == "transcript":
                # 前端直接发来的文字（如 Web Speech API）
                if not session.is_listening:
                    continue
                text = msg.get("text", "").strip()
                is_final = msg.get("is_final", True)
                if not text:
                    continue
                transcript_id = f"t-{int(time.time() * 1000)}"
                await send_json(websocket, {
                    "type": "transcript",
                    "id": transcript_id,
                    "text": text,
                    "is_final": is_final,
                })
                if is_final:
                    session.add_transcript(text)
                    asyncio.create_task(_translate_and_send(websocket, text, transcript_id, session))

            elif msg_type == "audio_chunk":
                if not session.is_listening:
                    continue
                audio_b64 = msg.get("data", "")
                chunk_index = msg.get("chunk_index", 0)
                if not audio_b64:
                    continue
                try:
                    audio_bytes = base64.b64decode(audio_b64)
                    logger.debug(f"[WS] 收到音频块 #{chunk_index}: {len(audio_bytes)} bytes")
                    # 放入队列，由 worker 顺序处理
                    await _session_queues[session_id].put((audio_bytes, chunk_index))
                except Exception as e:
                    logger.warning(f"[WS] 音频解码失败: {e}")
                    continue

            elif msg_type == "manual_ask":
                question = msg.get("question", "").strip()
                if question:
                    logger.info(f"[手动提问] {question[:60]}")
                    asyncio.create_task(_generate_answer(websocket, session, question, force=True))

            elif msg_type == "clear_history":
                session.transcript_buffer.clear()
                asr_service.clear_session(session_id)
                _session_last_full_text.pop(session_id, None)
                _session_transcript_count.pop(session_id, None)
                await send_json(websocket, {"type": "history_cleared"})

            elif msg_type == "ping":
                await send_json(websocket, {"type": "pong"})

    except WebSocketDisconnect:
        logger.info(f"[{session_id[:8]}] WebSocket 断开")
    except Exception as e:
        logger.error(f"WebSocket 异常: {e}")
    finally:
        session.is_listening = False
        # 停止 worker
        if session_id in _session_queues:
            await _session_queues[session_id].put(None)
        asr_service.clear_session(session_id)
        _session_queues.pop(session_id, None)
        _session_workers.pop(session_id, None)
        _session_last_full_text.pop(session_id, None)
        _session_transcript_count.pop(session_id, None)


async def _detect_and_answer(websocket: WebSocket, session, text: str):
    """问题检测 -> 生成答案"""
    try:
        is_question = await asyncio.wait_for(
            llm_service.detect_question(text),
            timeout=10.0
        )
        if is_question:
            logger.info(f"[问题检测] 检测到问题: {text[:50]}")
            await send_json(websocket, {"type": "question_detected", "text": text})
            await _generate_answer(websocket, session, text)
    except asyncio.TimeoutError:
        logger.warning(f"[问题检测] 超时，跳过: {text[:30]}")
    except Exception as e:
        logger.error(f"问题检测异常: {e}")


async def _generate_answer(websocket: WebSocket, session, question: str, force: bool = False):
    """流式生成答案"""
    if session.is_generating and not force:
        return
    session.is_generating = True
    await send_json(websocket, {"type": "answer_start", "question": question})
    try:
        full_answer = []
        async for chunk in llm_service.generate_answer_stream(
            question,
            session.get_context(),
            session.system_prompt,
            session.course_materials,
            session.chat_history,
        ):
            full_answer.append(chunk)
            await send_json(websocket, {"type": "answer_chunk", "chunk": chunk})
        answer_text = "".join(full_answer)
        session.add_chat_turn(question, answer_text)
        await send_json(websocket, {
            "type": "answer_done",
            "full_answer": answer_text,
        })
        logger.info(f"[AI] 回答完成: {answer_text[:60]}...")
    except Exception as e:
        logger.error(f"生成答案异常: {e}")
        await send_json(websocket, {"type": "answer_done", "full_answer": ""})
    finally:
        session.is_generating = False
