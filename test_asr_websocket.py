"""
ASR WebSocket 端到端测试脚本
模拟浏览器 MediaRecorder 发送 WebM 音频块，测试后端 faster-whisper 识别是否正常工作

用法：
    python3 test_asr_websocket.py [音频文件路径]
    
    如果不提供音频文件，会自动用 macOS say 命令生成测试语音
    
测试内容：
    1. 建立 WebSocket 连接
    2. 发送配置（设置 ASR 语言）
    3. 发送 start_listening
    4. 将音频文件转换为 WebM 格式，分块发送
    5. 接收并打印所有服务端消息
    6. 验证是否收到 transcript 消息（字幕）
"""
import asyncio
import base64
import json
import sys
import io
import time
import os
import subprocess
import tempfile

try:
    import websockets
except ImportError:
    print("安装 websockets: pip install websockets")
    sys.exit(1)

try:
    import av
    HAS_AV = True
except ImportError:
    HAS_AV = False
    print("警告: PyAV 未安装")

WS_URL = "ws://127.0.0.1:18765/ws/test-ws-session"


def generate_speech_aiff(text: str, output_path: str) -> bool:
    """使用 macOS say 命令生成语音"""
    try:
        result = subprocess.run(
            ['say', text, '-o', output_path],
            capture_output=True, timeout=15
        )
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception as e:
        print(f"say 命令失败: {e}")
        return False


def audio_to_webm(audio_path: str) -> bytes:
    """将任意音频文件转换为 WebM/Opus（模拟浏览器 MediaRecorder 输出）"""
    output_buf = io.BytesIO()
    
    in_container = av.open(audio_path)
    out_container = av.open(output_buf, mode='w', format='webm')
    
    in_stream = next(s for s in in_container.streams if s.type == 'audio')
    out_stream = out_container.add_stream('libopus', rate=48000)
    out_stream.layout = 'mono'
    
    resampler = av.AudioResampler(format='fltp', layout='mono', rate=48000)
    
    for frame in in_container.decode(in_stream):
        for rf in resampler.resample(frame):
            rf.pts = None
            for packet in out_stream.encode(rf):
                out_container.mux(packet)
    
    for packet in out_stream.encode(None):
        out_container.mux(packet)
    
    out_container.close()
    in_container.close()
    
    output_buf.seek(0)
    return output_buf.read()


async def test_websocket():
    """主测试函数"""
    print(f"\n{'='*60}")
    print("ASR WebSocket 端到端测试")
    print(f"{'='*60}")
    print(f"连接到: {WS_URL}")
    
    # 准备测试音频
    audio_file = sys.argv[1] if len(sys.argv) > 1 else None
    webm_bytes = None
    
    if audio_file and os.path.exists(audio_file):
        print(f"使用音频文件: {audio_file}")
        if HAS_AV:
            print("转换为 WebM/Opus...")
            webm_bytes = audio_to_webm(audio_file)
            print(f"WebM 大小: {len(webm_bytes)} bytes")
        else:
            with open(audio_file, 'rb') as f:
                webm_bytes = f.read()
    else:
        # 使用 say 生成英文语音
        with tempfile.NamedTemporaryFile(suffix='.aiff', delete=False) as f:
            tmp_path = f.name
        
        test_text = "Hello, this is a test. Machine learning is a branch of artificial intelligence."
        print(f"生成测试语音: '{test_text}'")
        
        if generate_speech_aiff(test_text, tmp_path):
            print(f"AIFF 大小: {os.path.getsize(tmp_path)} bytes")
            if HAS_AV:
                print("转换为 WebM/Opus...")
                webm_bytes = audio_to_webm(tmp_path)
                print(f"WebM 大小: {len(webm_bytes)} bytes")
            os.unlink(tmp_path)
        else:
            print("❌ 无法生成测试语音")
            return False
    
    if not webm_bytes:
        print("❌ 无音频数据")
        return False
    
    # 将音频分成 2 个块（模拟 2 秒间隔）
    chunk_size = len(webm_bytes) // 2
    chunks = [webm_bytes[:chunk_size], webm_bytes[chunk_size:]]
    print(f"分成 {len(chunks)} 个音频块，每块约 {chunk_size} bytes")
    
    received_transcript = False
    messages_received = []
    
    try:
        async with websockets.connect(WS_URL, ping_interval=None) as ws:
            print("\n✅ WebSocket 连接成功")
            
            # 等待 connected 消息
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            print(f"📨 收到: {json.dumps(msg, ensure_ascii=False)}")
            messages_received.append(msg)
            
            # 发送配置（英文识别）
            config = {
                "type": "config_update",
                "asr_language": "en",
                "translate_enabled": False,
            }
            await ws.send(json.dumps(config))
            print(f"📤 发送配置: asr_language=en")
            
            # 等待配置确认
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            print(f"📨 收到: {json.dumps(msg, ensure_ascii=False)}")
            messages_received.append(msg)
            
            # 发送 start_listening
            await ws.send(json.dumps({"type": "start_listening"}))
            print("📤 发送: start_listening")
            
            # 等待 listening_started
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            print(f"📨 收到: {json.dumps(msg, ensure_ascii=False)}")
            messages_received.append(msg)
            
            # 发送所有音频块
            for i, chunk in enumerate(chunks):
                b64 = base64.b64encode(chunk).decode('utf-8')
                payload = {
                    "type": "audio_chunk",
                    "data": b64,
                    "session_id": "test-ws-session",
                }
                await ws.send(json.dumps(payload))
                print(f"\n📤 发送音频块 #{i+1}: {len(chunk)} bytes → {len(b64)} chars (base64)")
            
            # 等待识别结果（最多 60 秒）
            print("\n⏳ 等待识别结果（最多 60 秒）...")
            deadline = asyncio.get_event_loop().time() + 60
            
            while asyncio.get_event_loop().time() < deadline:
                remaining = deadline - asyncio.get_event_loop().time()
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5))
                    msg = json.loads(raw)
                    messages_received.append(msg)
                    
                    msg_type = msg.get('type', '')
                    
                    if msg_type == 'transcript':
                        received_transcript = True
                        text = msg.get('text', '')
                        is_final = msg.get('is_final', True)
                        print(f"\n🎉 收到字幕！is_final={is_final}, text: {text}")
                    elif msg_type == 'transcript_translation':
                        print(f"🌐 翻译: {msg.get('translation', '')}")
                    elif msg_type == 'error':
                        print(f"❌ 错误: {msg.get('message', '')}")
                    else:
                        print(f"📨 收到: {json.dumps(msg, ensure_ascii=False)}")
                    
                    if received_transcript:
                        # 再等 3 秒看是否有翻译
                        try:
                            extra = await asyncio.wait_for(ws.recv(), timeout=3)
                            extra_msg = json.loads(extra)
                            messages_received.append(extra_msg)
                            if extra_msg.get('type') == 'transcript_translation':
                                print(f"🌐 翻译: {extra_msg.get('translation', '')}")
                            else:
                                print(f"📨 额外消息: {json.dumps(extra_msg, ensure_ascii=False)}")
                        except asyncio.TimeoutError:
                            pass
                        break
                        
                except asyncio.TimeoutError:
                    print(".", end="", flush=True)
                    continue
            
            if not received_transcript:
                print("\n⏱ 等待超时")
            
            # 发送 stop_listening
            await ws.send(json.dumps({"type": "stop_listening"}))
            print("\n📤 发送: stop_listening")
    
    except ConnectionRefusedError:
        print("❌ 连接被拒绝，请确保后端服务正在运行")
        print(f"   启动命令: cd backend && python3 -m uvicorn main:app --port 18765")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 测试结果
    print(f"\n{'='*60}")
    print("测试结果")
    print(f"{'='*60}")
    print(f"收到消息总数: {len(messages_received)}")
    print(f"收到 transcript 消息: {'✅ 是' if received_transcript else '❌ 否'}")
    
    msg_types = [m.get('type') for m in messages_received]
    print(f"消息类型序列: {msg_types}")
    
    if received_transcript:
        print("\n✅ 测试通过！ASR 识别和字幕推送功能正常工作")
        return True
    else:
        print("\n⚠️  未收到 transcript 消息")
        return False


if __name__ == "__main__":
    result = asyncio.run(test_websocket())
    sys.exit(0 if result else 1)
