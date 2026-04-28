"""
ASR 模块 — 基于 faster-whisper（本地离线语音识别）
开源项目：https://github.com/SYSTRAN/faster-whisper
Stars: 22.4k | License: MIT | 比 OpenAI Whisper 快 4 倍，支持 CPU 运行

使用方式：
  - 首次运行时自动从 HuggingFace 下载模型（约 500MB，仅需一次）
  - 之后完全离线运行，无需任何 API Key
  - 默认使用 small 模型，可通过环境变量 WHISPER_MODEL_SIZE 调整
    可选：tiny(~75MB) / base(~145MB) / small(~500MB) / medium(~1.5GB)

音频格式处理：
  前端 MediaRecorder 使用 stop/start 循环模式，每个片段都是完整的 WebM 文件
  （包含 EBML header），PyAV 可以正确解析。
"""

import io
import logging
import os
import threading
import tempfile
import subprocess
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


def _detect_format(audio_bytes: bytes) -> str:
    """检测音频格式"""
    if len(audio_bytes) < 4:
        return "unknown"
    magic = audio_bytes[:4]
    if magic[:2] == b'\x1a\x45':
        return "webm"
    if magic == b'RIFF':
        return "wav"
    if magic == b'OggS':
        return "ogg"
    if magic[:3] == b'ID3' or magic[:2] in [b'\xff\xfb', b'\xff\xf3', b'\xff\xf2']:
        return "mp3"
    if magic == b'fLaC':
        return "flac"
    if magic[:2] in [b'\xff\xf1', b'\xff\xf9']:
        return "aac"
    return "unknown"


def _convert_to_wav_pyav(audio_bytes: bytes, fmt_hint: str = None) -> Optional[bytes]:
    """
    使用 PyAV 将音频转换为 WAV（16kHz, 单声道, PCM s16le）
    
    前端使用 stop/start 循环录音，每个片段都是完整的 WebM 文件（含 EBML header），
    PyAV 可以正确解析。
    """
    try:
        import av

        input_buf = io.BytesIO(audio_bytes)
        output_buf = io.BytesIO()

        # 按格式提示尝试打开，依次尝试 webm、matroska、ogg、自动检测
        formats_to_try = []
        if fmt_hint and fmt_hint not in ('unknown',):
            formats_to_try.append(fmt_hint)
        formats_to_try += ['webm', 'matroska', 'ogg', None]

        in_container = None
        last_err = None
        for fmt in formats_to_try:
            try:
                input_buf.seek(0)
                if fmt:
                    in_container = av.open(input_buf, format=fmt)
                else:
                    in_container = av.open(input_buf)
                logger.debug(f"[ASR] PyAV 打开成功，format={fmt}")
                break
            except Exception as e:
                last_err = e
                continue

        if in_container is None:
            logger.warning(f"[ASR] PyAV 无法打开音频（所有格式均失败，最后错误: {last_err}）")
            return None

        # 找到音频流
        in_stream = next((s for s in in_container.streams if s.type == 'audio'), None)
        if in_stream is None:
            logger.warning("[ASR] 音频数据中未找到音频流")
            in_container.close()
            return None

        logger.debug(f"[ASR] 音频流: codec={in_stream.codec_context.name}, "
                     f"rate={in_stream.codec_context.sample_rate}, "
                     f"channels={in_stream.codec_context.channels}")

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

        frame_count = 0
        for frame in in_container.decode(in_stream):
            resampled_frames = resampler.resample(frame)
            for rf in resampled_frames:
                rf.pts = None
                for packet in out_stream.encode(rf):
                    out_container.mux(packet)
            frame_count += 1

        # Flush 编码器
        for packet in out_stream.encode(None):
            out_container.mux(packet)

        out_container.close()
        in_container.close()

        output_buf.seek(0)
        wav_bytes = output_buf.read()
        logger.info(f"[ASR] PyAV 转换成功: {len(audio_bytes)} bytes → {len(wav_bytes)} bytes WAV "
                    f"（{frame_count} frames）")
        return wav_bytes

    except Exception as e:
        logger.error(f"[ASR] PyAV 转换异常: {e}")
        return None


def _convert_to_wav_ffmpeg(audio_bytes: bytes) -> Optional[bytes]:
    """
    使用系统 ffmpeg 命令行将音频转换为 WAV（备用方案）
    """
    # 查找 ffmpeg
    ffmpeg_paths = [
        'ffmpeg',
        '/opt/homebrew/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        '/usr/bin/ffmpeg',
    ]
    ffmpeg_bin = None
    for p in ffmpeg_paths:
        try:
            result = subprocess.run([p, '-version'], capture_output=True, timeout=3)
            if result.returncode == 0:
                ffmpeg_bin = p
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    if not ffmpeg_bin:
        logger.debug("[ASR] 系统未安装 ffmpeg，跳过 ffmpeg 转换")
        return None

    try:
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as f_in:
            f_in.write(audio_bytes)
            in_path = f_in.name

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f_out:
            out_path = f_out.name

        result = subprocess.run(
            [ffmpeg_bin, '-y', '-i', in_path,
             '-ar', '16000', '-ac', '1', '-f', 'wav', out_path],
            capture_output=True, timeout=30
        )

        if result.returncode != 0:
            logger.warning(f"[ASR] ffmpeg 转换失败: {result.stderr.decode()[:200]}")
            return None

        with open(out_path, 'rb') as f:
            wav_bytes = f.read()

        logger.info(f"[ASR] ffmpeg 转换成功: {len(audio_bytes)} → {len(wav_bytes)} bytes")
        return wav_bytes

    except Exception as e:
        logger.error(f"[ASR] ffmpeg 转换异常: {e}")
        return None
    finally:
        for p in [in_path, out_path]:
            try:
                os.unlink(p)
            except Exception:
                pass


def _convert_to_wav(audio_bytes: bytes) -> Optional[bytes]:
    """
    将任意格式音频转换为 WAV（16kHz, 单声道, PCM s16le）
    优先使用 PyAV，失败则尝试 ffmpeg 命令行
    """
    fmt = _detect_format(audio_bytes)
    logger.debug(f"[ASR] 检测到音频格式: {fmt}，大小: {len(audio_bytes)} bytes，"
                 f"magic: {audio_bytes[:4].hex()}")

    # 如果已经是 WAV，直接返回
    if fmt == 'wav':
        logger.debug("[ASR] 已是 WAV 格式，直接使用")
        return audio_bytes

    # 尝试 PyAV
    wav = _convert_to_wav_pyav(audio_bytes, fmt_hint=fmt)
    if wav:
        return wav

    # 尝试 ffmpeg 命令行
    wav = _convert_to_wav_ffmpeg(audio_bytes)
    if wav:
        return wav

    logger.warning(f"[ASR] 所有转换方法均失败，格式: {fmt}，大小: {len(audio_bytes)} bytes")
    return None


class ASRService:
    """
    语音识别服务
    使用 faster-whisper 进行本地离线语音识别
    项目地址：https://github.com/SYSTRAN/faster-whisper

    输入：浏览器 MediaRecorder 产生的完整 WebM 文件（stop/start 循环录音模式）
    处理：PyAV 转换为 WAV → faster-whisper 识别
    输出：识别文字
    """

    async def transcribe(self, audio_bytes: bytes, language: Optional[str] = "zh") -> Optional[str]:
        """
        将音频字节流转录为文字
        :param audio_bytes: 完整的 WebM 文件（来自前端 stop/start 循环录音）
        :param language: 语言代码，默认中文 zh，传 None 则自动检测
        :return: 识别出的文字，失败返回 None
        """
        if not audio_bytes or len(audio_bytes) < 500:
            logger.debug(f"[ASR] 音频块过小（{len(audio_bytes)} bytes），跳过")
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
            # 转换为 WAV
            wav_bytes = _convert_to_wav(audio_bytes)
            if wav_bytes is None:
                logger.warning("[ASR] 格式转换失败，无法识别此音频块")
                return None

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
                logger.debug("[ASR] 识别结果为空（静音或无有效语音）")
                return None
            result = " ".join(texts)
            logger.info(f"[ASR] 识别成功: {result[:80]}")
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
