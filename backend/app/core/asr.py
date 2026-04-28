"""
ASR 模块 — 基于 faster-whisper
简洁可靠版：
  - 每个会话维护一个持续增长的音频流（BytesIO）
  - 块 #0：完整 WebM（含 EBML header），缓存并识别
  - 块 #1+：裸帧，自动拼接 header 后识别
  - 无复杂锁机制，由 websocket.py 的 asyncio.Queue 保证顺序
  - 滑动窗口：超过 2MB 时截断，防止识别变慢
"""

import io
import logging
import os
import threading
from typing import Optional, Dict

logger = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()

# 每个会话的 header 块（第一块完整 WebM）
_session_headers: Dict[str, bytes] = {}
# 每个会话的累积音频数据
_session_audio: Dict[str, bytes] = {}


def _get_model():
    """获取 faster-whisper 模型实例（懒加载，线程安全）"""
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
    """将 WebM/Opus 音频转换为 WAV (16kHz, mono)"""
    try:
        import av
        input_buf = io.BytesIO(audio_bytes)
        output_buf = io.BytesIO()

        in_container = None
        for fmt in ['webm', 'matroska', None]:
            try:
                input_buf.seek(0)
                in_container = av.open(input_buf, format=fmt)
                # 确认有音频流
                if any(s.type == 'audio' for s in in_container.streams):
                    break
                in_container.close()
                in_container = None
            except Exception:
                in_container = None
                continue

        if in_container is None:
            logger.debug("[ASR] PyAV 无法打开音频容器")
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

        wav = output_buf.getvalue()
        logger.debug(f"[ASR] PyAV 转换成功: {len(audio_bytes)} → {len(wav)} bytes")
        return wav
    except Exception as e:
        logger.debug(f"[ASR] 转换异常: {e}")
        return None


def _transcribe_sync(model, wav_bytes: bytes, language: Optional[str]) -> Optional[str]:
    """同步识别 WAV 音频"""
    try:
        audio_io = io.BytesIO(wav_bytes)
        segments, info = model.transcribe(
            audio_io,
            language=language if language else None,
            beam_size=5,
            vad_filter=False,
        )
        texts = [seg.text.strip() for seg in segments if seg.text.strip()]
        result = " ".join(texts) if texts else None
        if result:
            logger.info(f"[ASR] 识别成功 (时长: {info.duration:.2f}s): {result[:80]}...")
        return result
    except Exception as e:
        logger.error(f"[ASR] 识别失败: {e}")
        return None


class ASRService:
    """语音识别服务 — 简洁可靠版"""

    def transcribe_sync(self, audio_bytes: bytes, session_id: str = "default",
                        chunk_index: int = 0, language: Optional[str] = "zh") -> Optional[str]:
        """
        同步转录音频块（在线程池中调用）
        
        chunk_index == 0：第一块，包含完整 EBML header，缓存为 session header
        chunk_index > 0：后续裸帧块，自动拼接 session header 后识别
        """
        if not audio_bytes:
            return None

        model = _get_model()
        if model is None:
            return None

        if chunk_index == 0:
            # 第一块：完整 WebM，直接缓存并识别
            _session_headers[session_id] = audio_bytes
            _session_audio[session_id] = audio_bytes
            logger.info(f"[ASR] 块 #0 (header): {len(audio_bytes)} bytes，开始识别")
        else:
            # 后续块：拼接 header + 当前块
            header = _session_headers.get(session_id, b"")
            if not header:
                logger.warning(f"[ASR] 块 #{chunk_index}: 无 header 缓存，跳过")
                return None
            
            combined = header + audio_bytes
            
            # 滑动窗口：累积音频，最多保留 2MB
            prev = _session_audio.get(session_id, header)
            accumulated = prev + audio_bytes
            if len(accumulated) > 2 * 1024 * 1024:
                # 保留 header + 后半部分
                keep = accumulated[-(1024 * 1024):]
                accumulated = header + keep
            _session_audio[session_id] = accumulated
            
            combined = accumulated
            logger.info(f"[ASR] 块 #{chunk_index}: 累积 {len(combined)} bytes，开始识别")

        full_audio = _session_audio.get(session_id, audio_bytes)
        wav_bytes = _convert_to_wav(full_audio)
        if not wav_bytes:
            logger.warning(f"[ASR] 块 #{chunk_index}: WAV 转换失败")
            return None

        return _transcribe_sync(model, wav_bytes, language)

    def clear_session(self, session_id: str):
        """清除会话缓存"""
        _session_headers.pop(session_id, None)
        _session_audio.pop(session_id, None)
        logger.info(f"[ASR] 清除会话缓存: {session_id}")


asr_service = ASRService()
