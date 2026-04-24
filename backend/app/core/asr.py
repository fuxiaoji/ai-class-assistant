"""
ASR 模块 - 语音识别服务
支持 OpenAI Whisper API，可扩展其他 ASR 服务
"""
import io
import logging
from openai import AsyncOpenAI
from .config import settings

logger = logging.getLogger(__name__)


class ASRService:
    """语音识别服务，封装 Whisper API 调用"""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.asr_api_key or settings.llm_api_key,
            base_url=settings.asr_base_url,
        )
        self.model = settings.asr_model

    async def transcribe(self, audio_bytes: bytes, language: str = "zh") -> str:
        """
        将音频字节流转换为文字

        Args:
            audio_bytes: 音频数据（WebM/WAV/MP3 格式）
            language: 语言代码，默认中文

        Returns:
            识别出的文字字符串
        """
        if not audio_bytes or len(audio_bytes) < 1000:
            logger.debug("音频数据过短，跳过识别")
            return ""

        try:
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "audio.webm"

            transcript = await self.client.audio.transcriptions.create(
                model=self.model,
                file=audio_file,
                language=language,
                response_format="text",
            )
            text = transcript.strip() if isinstance(transcript, str) else transcript.text.strip()
            logger.info(f"ASR 识别结果: {text[:100]}...")
            return text
        except Exception as e:
            logger.error(f"ASR 识别失败: {e}")
            return ""


# 单例
asr_service = ASRService()
