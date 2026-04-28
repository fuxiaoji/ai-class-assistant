"""
ASR 调试模块 - 保存收到的音频块到文件，分析格式
临时使用，调试完成后删除
"""
import os
import io
import logging

logger = logging.getLogger(__name__)
DEBUG_DIR = "/tmp/asr_debug_chunks"
os.makedirs(DEBUG_DIR, exist_ok=True)
_chunk_count = 0


def save_chunk(audio_bytes: bytes, suffix: str = "bin") -> str:
    """保存音频块到文件，返回文件路径"""
    global _chunk_count
    _chunk_count += 1
    path = os.path.join(DEBUG_DIR, f"chunk_{_chunk_count:04d}.{suffix}")
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def analyze_chunk(audio_bytes: bytes) -> dict:
    """分析音频块的格式"""
    info = {
        "size": len(audio_bytes),
        "hex_header": audio_bytes[:16].hex() if len(audio_bytes) >= 16 else audio_bytes.hex(),
        "format": "unknown",
    }
    
    # 检测常见格式的魔数
    if audio_bytes[:4] == b'RIFF':
        info["format"] = "WAV"
    elif audio_bytes[:4] == b'OggS':
        info["format"] = "OGG"
    elif audio_bytes[:2] == b'\x1a\x45':  # EBML header (WebM/MKV)
        info["format"] = "WebM/MKV"
    elif audio_bytes[:3] == b'ID3' or (audio_bytes[:2] in [b'\xff\xfb', b'\xff\xf3', b'\xff\xf2']):
        info["format"] = "MP3"
    elif audio_bytes[:4] == b'fLaC':
        info["format"] = "FLAC"
    elif audio_bytes[:4] in [b'\x00\x00\x00\x18', b'\x00\x00\x00\x1c', b'\x00\x00\x00\x20']:
        info["format"] = "MP4/M4A"
    elif audio_bytes[:2] in [b'\xff\xf1', b'\xff\xf9']:
        info["format"] = "AAC"
    
    # 尝试 PyAV 解析
    try:
        import av
        buf = io.BytesIO(audio_bytes)
        container = av.open(buf)
        streams = [f"{s.type}:{s.codec_context.name}" for s in container.streams]
        info["av_streams"] = streams
        info["av_format"] = container.format.name
        container.close()
        info["av_ok"] = True
    except Exception as e:
        info["av_ok"] = False
        info["av_error"] = str(e)
    
    return info
