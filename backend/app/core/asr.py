"""
ASR 模块 — 基于 faster-whisper
终极稳定版：
  - 滑动窗口：只保留最近 30 秒音频，防止识别变慢
  - 顺序锁：确保每个会话的 ASR 任务按顺序执行，防止乱序
  - 优化转换逻辑
"""

import io
import logging
import os
import asyncio
import threading
from typing import Optional, Dict

logger = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()

# 缓存每个会话的音频数据和处理锁
_session_data: Dict[str, bytes] = {}
_session_locks: Dict[str, asyncio.Lock] = {}


def _get_model():
    """获取 faster-whisper 模型实例"""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from faster_whisper import WhisperModel
            model_size = os.environ.get("WHISPER_MODEL_SIZE", "small")
            logger.info(f"[ASR] 正在加载 faster-whisper 模型: {model_size}")
            _model = WhisperModel(model_size, device="cpu", compute_type="int8")
            logger.info(f"[ASR] faster-whisper 模型加载完成: {model_size}")
            return _model
        except Exception as e:
            logger.error(f"[ASR] 模型加载失败: {e}")
            return None


def _convert_to_wav(audio_bytes: bytes) -> Optional[bytes]:
    """将音频转换为 WAV (16kHz, mono)"""
    try:
        import av
        input_buf = io.BytesIO(audio_bytes)
        output_buf = io.BytesIO()

        in_container = None
        for fmt in ['webm', 'matroska', 'ogg', None]:
            try:
                input_buf.seek(0)
                in_container = av.open(input_buf, format=fmt)
                break
            except:
                continue

        if in_container is None:
            return None

        in_stream = next((s for s in in_container.streams if s.type == 'audio'), None)
        if in_stream is None:
            in_container.close()
            return None

        out_container = av.open(output_buf, mode='w', format='wav')
        out_stream = out_container.add_stream('pcm_s16le', rate=16000)
        out_stream.layout = 'mono'

        resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)

        for frame in in_container.decode(in_stream):
            for rf in resampler.resample(frame):
                rf.pts = None
                for packet in out_stream.encode(rf):
                    out_container.mux(packet)

        for packet in out_stream.encode(None):
            out_container.mux(packet)

        out_container.close()
        in_container.close()
        return output_buf.getvalue()
    except Exception as e:
        logger.debug(f"[ASR] 转换异常: {e}")
        return None


class ASRService:
    """语音识别服务"""

    async def transcribe(self, audio_bytes: bytes, session_id: str = "default", chunk_index: int = 1, language: Optional[str] = "zh") -> Optional[str]:
        """
        转录音频（带顺序锁和滑动窗口）
        """
        if not audio_bytes:
            return None

        # 获取或创建会话锁
        if session_id not in _session_locks:
            _session_locks[session_id] = asyncio.Lock()
        
        async with _session_locks[session_id]:
            # 维护会话音频数据
            if session_id not in _session_data or chunk_index == 1:
                _session_data[session_id] = b""
            
            # 追加新数据
            _session_data[session_id] += audio_bytes
            
            # 滑动窗口：只保留最近 1MB 的数据（约 30-60 秒 WebM）
            if len(_session_data[session_id]) > 1024 * 1024:
                # 粗略切分，保留后 1MB
                _session_data[session_id] = _session_data[session_id][-1024 * 1024:]
            
            full_audio = _session_data[session_id]

            model = _get_model()
            if model is None:
                return None

            try:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None,
                    lambda: self._transcribe_sync(model, full_audio, language),
                )
            except Exception as e:
                logger.error(f"[ASR] 识别任务异常: {e}")
                return None

    def _transcribe_sync(self, model, audio_bytes: bytes, language: Optional[str]) -> Optional[str]:
        """同步识别"""
        try:
            wav_bytes = _convert_to_wav(audio_bytes)
            if not wav_bytes:
                return None

            audio_io = io.BytesIO(wav_bytes)
            segments, info = model.transcribe(
                audio_io,
                language=language if language else None,
                beam_size=5,
                vad_filter=False
            )
            
            texts = [seg.text.strip() for seg in segments if seg.text.strip()]
            result = "".join(texts) if texts else None
            
            if result:
                logger.info(f"[ASR] 识别成功 (时长: {info.duration:.2f}s): {result}")
            return result
        except Exception as e:
            logger.error(f"[ASR] 识别失败: {e}")
            return None

    def clear_session(self, session_id: str):
        """清除会话缓存"""
        if session_id in _session_data:
            del _session_data[session_id]
        if session_id in _session_locks:
            del _session_locks[session_id]


asr_service = ASRService()
