"""
ASR 模块 — 基于 faster-whisper（本地离线语音识别）
开源项目：https://github.com/SYSTRAN/faster-whisper
Stars: 22.4k | License: MIT | 比 OpenAI Whisper 快 4 倍，支持 CPU 运行

使用方式：
  - 首次运行时自动从 HuggingFace 下载模型（约 500MB，仅需一次）
  - 之后完全离线运行，无需任何 API Key
  - 默认使用 small 模型，可通过环境变量 WHISPER_MODEL_SIZE 调整
    可选：tiny(~75MB) / base(~145MB) / small(~500MB) / medium(~1.5GB)

修复记录：
  - 2024: 增加 PyAV 转换层，将浏览器 MediaRecorder 输出的 WebM/Opus 流式音频块
    转换为 faster-whisper 可识别的 WAV 格式（16kHz, 单声道, PCM s16le）
    原因：MediaRecorder 每 2 秒产生一个 WebM 块，缺少完整容器头，
    直接送入 faster-whisper 会报 "Invalid data found when processing input"
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


def _convert_to_wav(audio_bytes: bytes) -> Optional[bytes]:
    """
    将任意格式音频（WebM/Opus、MP4、OGG 等）转换为 WAV（16kHz, 单声道, PCM s16le）
    使用 PyAV 进行转换，无需外部 ffmpeg 命令行工具。
    
    浏览器 MediaRecorder 产生的 WebM 流式块缺少完整的容器头信息，
    faster-whisper 底层的 ffmpeg 无法直接解析，需要先用 PyAV 重新封装。
    """
    try:
        import av
        
        input_buf = io.BytesIO(audio_bytes)
        output_buf = io.BytesIO()
        
        # 尝试打开输入，先尝试 webm 格式，再自动检测
        in_container = None
        for fmt in ['webm', 'matroska', None]:
            try:
                input_buf.seek(0)
                if fmt:
                    in_container = av.open(input_buf, format=fmt)
                else:
                    in_container = av.open(input_buf)
                break
            except Exception:
                continue
        
        if in_container is None:
            logger.warning("[ASR] PyAV 无法打开音频容器")
            return None
        
        # 找到音频流
        in_stream = next((s for s in in_container.streams if s.type == 'audio'), None)
        if in_stream is None:
            logger.warning("[ASR] 音频数据中未找到音频流")
            in_container.close()
            return None
        
        # 创建输出 WAV 容器
        out_container = av.open(output_buf, mode='w', format='wav')
        out_stream = out_container.add_stream('pcm_s16le', rate=16000)
        out_stream.layout = 'mono'
        
        # 重采样器：转为 16kHz 单声道 s16
        resampler = av.AudioResampler(
            format='s16',
            layout='mono',
            rate=16000,
        )
        
        for frame in in_container.decode(in_stream):
            resampled_frames = resampler.resample(frame)
            for rf in resampled_frames:
                rf.pts = None
                for packet in out_stream.encode(rf):
                    out_container.mux(packet)
        
        # Flush 编码器
        for packet in out_stream.encode(None):
            out_container.mux(packet)
        
        out_container.close()
        in_container.close()
        
        output_buf.seek(0)
        wav_bytes = output_buf.read()
        logger.debug(f"[ASR] WebM→WAV 转换完成: {len(audio_bytes)} → {len(wav_bytes)} bytes")
        return wav_bytes
        
    except Exception as e:
        logger.error(f"[ASR] 音频格式转换失败: {e}")
        return None


class ASRService:
    """
    语音识别服务
    使用 faster-whisper 进行本地离线语音识别
    项目地址：https://github.com/SYSTRAN/faster-whisper
    
    输入：浏览器 MediaRecorder 产生的 WebM/Opus 音频块（base64 解码后）
    处理：PyAV 转换为 WAV → faster-whisper 识别
    输出：识别文字
    """

    async def transcribe(self, audio_bytes: bytes, language: Optional[str] = "zh") -> Optional[str]:
        """
        将音频字节流转录为文字
        :param audio_bytes: WebM/Opus 或其他格式的音频数据（来自浏览器 MediaRecorder）
        :param language: 语言代码，默认中文 zh，传 None 则自动检测
        :return: 识别出的文字，失败返回 None
        """
        if not audio_bytes or len(audio_bytes) < 500:
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
            # 先尝试直接识别（如果是标准 WAV 格式）
            wav_bytes = _convert_to_wav(audio_bytes)
            if wav_bytes is None:
                # 转换失败，尝试直接用原始数据
                logger.warning("[ASR] 格式转换失败，尝试直接识别原始音频")
                audio_io = io.BytesIO(audio_bytes)
            else:
                audio_io = io.BytesIO(wav_bytes)
            
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
