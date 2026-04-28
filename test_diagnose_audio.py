"""
诊断 Electron MediaRecorder 实际发来的音频块格式
通过 WebSocket 接收一个真实的音频块，保存到文件，分析格式
"""
import asyncio
import base64
import json
import io
import os
import sys

try:
    import websockets
except ImportError:
    print("pip install websockets")
    sys.exit(1)

WS_URL = "ws://127.0.0.1:18765/ws/diag-session"
SAVE_DIR = "/tmp/audio_diag"
os.makedirs(SAVE_DIR, exist_ok=True)


def analyze_bytes(data: bytes, label: str):
    print(f"\n=== {label} ===")
    print(f"大小: {len(data)} bytes")
    print(f"前16字节 hex: {data[:16].hex()}")
    print(f"前4字节 ascii: {data[:4]}")
    
    # 检测格式
    if data[:4] == b'RIFF':
        print("格式: WAV ✅")
    elif data[:2] == b'\x1a\x45':
        print("格式: WebM/MKV (EBML header) ✅")
    elif data[:4] == b'OggS':
        print("格式: OGG")
    elif data[:3] == b'ID3':
        print("格式: MP3")
    else:
        print(f"格式: 未知 (magic: {data[:4].hex()})")
    
    # PyAV 解析
    try:
        import av
        buf = io.BytesIO(data)
        for fmt in ['webm', 'matroska', 'ogg', None]:
            try:
                buf.seek(0)
                if fmt:
                    c = av.open(buf, format=fmt)
                else:
                    c = av.open(buf)
                streams = [(s.type, s.codec_context.name) for s in c.streams]
                print(f"PyAV 解析成功 (format={fmt}): streams={streams} ✅")
                c.close()
                break
            except Exception as e:
                print(f"PyAV format={fmt} 失败: {e}")
    except Exception as e:
        print(f"PyAV 导入失败: {e}")


async def intercept_audio():
    """拦截后端收到的音频块"""
    print("等待 Electron 发送音频块...")
    print("请在 Electron 应用中点击开始监听，说几句话")
    print(f"音频块将保存到: {SAVE_DIR}")
    
    # 修改后端 websocket 路由，临时保存音频块
    # 实际上我们直接监听后端日志中的 audio_chunk 消息
    # 这里改为直接在 asr.py 中添加保存逻辑
    print("\n请查看 /tmp/asr_debug_chunks/ 目录中的文件")
    print("运行: ls -la /tmp/asr_debug_chunks/")


if __name__ == "__main__":
    asyncio.run(intercept_audio())
