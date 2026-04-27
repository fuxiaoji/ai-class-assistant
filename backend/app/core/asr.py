"""
ASR 模块 — 基于 faster-whisper（本地离线语音识别）
开源项目：https://github.com/SYSTRAN/faster-whisper
Stars: 22.4k | License: MIT | 比 OpenAI Whisper 快 4 倍，支持 CPU 运行

使用方式：
  - 首次运行时自动从 HuggingFace 下载模型（约 500MB，仅需一次）
  - 之后完全离线运行，无需任何 API Key
  - 默认使用 small 模型，可通过环境变量 WHISPER_MODEL_SIZE 调整
    可选：tiny(~75MB) / base(~145MB) / small(~500MB) / medium(~1.5GB)
"""

import io
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()


def _get_model():
    """获取 faster-whisper 模型实例（懒加载 + 线程安全）"""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from faster_whisper import WhisperModel
            model_size = os.environ.get("WHISPER_MODEL_SIZE", "small")
            logger.info(f"[ASR] 正在加载 faster-whisper 模型: {model_size}（首次运行会自动下载）")
            _model = WhisperModel(model_size, device="cpu", compute_type="int8")
            logger.info(f"[ASR] faster-whisper 模型加载完成: {model_size}")
            return _model
        except ImportError:
            logger.error("[ASR] faster-whisper 未安装，请运行: pip install faster-whisper")
            return None
        except Exception as e:
            logger.error(f"[ASR] 模型加载失败: {e}")
            return None


class ASRService:
    """
    语音识别服务
    使用 faster-whisper 进行本地离线语音识别
    项目地址：https://github.com/SYSTRAN/faster-whisper
    """

    async def transcribe(self, audio_bytes: bytes, language: Optional[str] = "zh") -> Optional[str]:
        """
        将音频字节流转录为文字
        :param audio_bytes: WAV/WebM/MP4 等格式的音频数据
        :param language: 语言代码，默认中文 zh，传 None 则自动检测
        :return: 识别出的文字，失败返回 None
        """
        if not audio_bytes or len(audio_bytes) < 1000:
            return None

        model = _get_model()
        if model is None:
            logger.warning("[ASR] 模型未就绪，跳过识别")
            return None

        try:
            import asyncio
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._transcribe_sync(model, audio_bytes, language),
            )
            return result
        except Exception as e:
            logger.error(f"[ASR] 识别失败: {e}")
            return None

    def _transcribe_sync(self, model, audio_bytes: bytes, language: Optional[str]) -> Optional[str]:
        """同步识别（在线程池中执行，避免阻塞事件循环）"""
        try:
            audio_io = io.BytesIO(audio_bytes)
            segments, info = model.transcribe(
                audio_io,
                language=language if language else None,
                beam_size=3,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=300),
                condition_on_previous_text=False,
            )
            texts = [seg.text.strip() for seg in segments if seg.text.strip()]
            if not texts:
                return None
            result = " ".join(texts)
            logger.info(f"[ASR] 识别结果: {result[:80]}")
            return result
        except Exception as e:
            logger.error(f"[ASR] 同步识别异常: {e}")
            return None

    def is_ready(self) -> bool:
        """检查模型是否已加载"""
        return _model is not None

    def preload(self):
        """预加载模型（可在后台线程中调用，加快首次识别速度）"""
        def _load():
            _get_model()
        t = threading.Thread(target=_load, daemon=True)
        t.start()
        logger.info("[ASR] 已在后台开始预加载 faster-whisper 模型...")


# 全局单例
asr_service = ASRService()
