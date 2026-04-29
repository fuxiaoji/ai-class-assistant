"""
ASR 模块 — 基于 faster-whisper（稳定版）

流式音频处理策略：
  - 前端发送的 chunk_index 从 1 开始（块 #1 含完整 EBML header）
  - 块 #1（chunk_index <= 1）：完整 WebM，缓存前 64KB 作为 header，并识别全部内容
  - 块 #2+（chunk_index > 1）：裸 Opus 帧，自动拼接 header 后识别
  - 滑动窗口：累积超过 2MB 时截断，防止识别越来越慢
  - 无复杂锁机制，由 websocket.py 的 asyncio.Queue 保证顺序
"""

import io
import logging
import os
import threading
from typing import Optional, Dict

logger = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()

# 每个会话的 EBML header（第一块的前 64KB）
_session_headers: Dict[str, bytes] = {}
# 每个会话的累积完整音频（header + 所有块）
_session_audio: Dict[str, bytes] = {}

# header 最大缓存大小（前 64KB 足以包含完整 EBML header）
HEADER_MAX_SIZE = 65536
# 滑动窗口最大音频大小（约 60 秒）
MAX_AUDIO_BYTES = 2 * 1024 * 1024  # 2MB


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


def _is_valid_webm(data: bytes) -> bool:
    """检查是否是有效的 WebM 文件（EBML magic: 1a 45 df a3）"""
    return (len(data) >= 4 and
            data[0] == 0x1a and data[1] == 0x45 and
            data[2] == 0xdf and data[3] == 0xa3)


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
                c = av.open(input_buf, format=fmt)
                if any(s.type == 'audio' for s in c.streams):
                    in_container = c
                    break
                c.close()
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
        logger.debug(f"[ASR] PyAV 转换成功: {len(audio_bytes)} → {len(wav)} bytes WAV")
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
            logger.info(f"[ASR] 识别成功 (时长: {info.duration:.2f}s): {result[:100]}")
        return result
    except Exception as e:
        logger.error(f"[ASR] 识别失败: {e}")
        return None


class ASRService:
    """语音识别服务"""

    def transcribe_sync(
        self,
        audio_bytes: bytes,
        session_id: str = "default",
        chunk_index: int = 1,
        language: Optional[str] = "zh",
    ) -> Optional[str]:
        """
        同步转录音频块（在线程池中调用，由 asyncio.Queue 保证顺序）

        chunk_index <= 1：第一块，包含完整 EBML header
        chunk_index > 1：后续裸帧块，自动拼接 header 后识别
        """
        if not audio_bytes:
            return None

        model = _get_model()
        if model is None:
            return None

        if chunk_index <= 1:
            # 第一块：必须是完整 WebM（含 EBML header）
            if not _is_valid_webm(audio_bytes):
                logger.warning(
                    f"[ASR] 块 #{chunk_index}: 不是有效 WebM "
                    f"(magic: {audio_bytes[:4].hex() if audio_bytes else 'empty'})，跳过"
                )
                return None

            # 只缓存前 HEADER_MAX_SIZE 字节作为 header（不缓存全部音频，避免重复）
            _session_headers[session_id] = audio_bytes[:HEADER_MAX_SIZE]
            # 第一块的完整音频（用于本次识别）
            _session_audio[session_id] = audio_bytes
            logger.info(f"[ASR] 块 #{chunk_index} (第一块/header): {len(audio_bytes)} bytes")

        else:
            # 后续块：拼接 header + 新块
            header = _session_headers.get(session_id)
            if not header:
                logger.warning(f"[ASR] 块 #{chunk_index}: 无 header 缓存，跳过")
                return None

            # 累积音频：prev_audio + 新块（prev_audio 已包含 header）
            prev_audio = _session_audio.get(session_id, header)
            accumulated = prev_audio + audio_bytes

            # 滑动窗口：超过 MAX_AUDIO_BYTES 时截断
            if len(accumulated) > MAX_AUDIO_BYTES:
                # 保留 header + 后半部分音频
                keep_size = MAX_AUDIO_BYTES // 2
                accumulated = header + accumulated[-keep_size:]
                logger.debug(f"[ASR] 滑动窗口截断: 保留 {len(accumulated)} bytes")

            _session_audio[session_id] = accumulated
            logger.info(f"[ASR] 块 #{chunk_index}: 累积 {len(accumulated)} bytes")

        # 取累积的完整音频进行识别
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
        logger.info(f"[ASR] 清除会话缓存: {session_id[:8] if len(session_id) >= 8 else session_id}")


asr_service = ASRService()
