"""
ASR WebSocket 端到端测试脚本
模拟前端 stop/start 循环录音模式：每次发送一个完整的 WebM 文件（含 EBML header）

关键修复：
  旧方案：将 WebM 分成 2 块发送 → 第2块是裸帧，PyAV 无法解析
  新方案：发送整个完整 WebM 文件 → PyAV 可以正确解析（有 EBML header）
"""
import asyncio
import base64
import json
import sys
import io
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


def generate_complete_webm() -> bytes:
    """生成一个完整的 WebM 文件（模拟 MediaRecorder stop() 产生的完整片段）"""
    with tempfile.NamedTemporaryFile(suffix='.aiff', delete=False) as f:
        aiff_path = f.name

    test_text = "Hello, this is a test. Machine learning is a branch of artificial intelligence."
    print(f"生成测试语音: '{test_text}'")

    try:
        result = subprocess.run(['say', test_text, '-o', aiff_path],
                                capture_output=True, timeout=15)
        if result.returncode != 0:
            print(f"say 命令失败: {result.stderr}")
            return b''
        print(f"AIFF 大小: {os.path.getsize(aiff_path)} bytes")
    except Exception as e:
        print(f"say 命令异常: {e}")
        return b''

    if not HAS_AV:
        print("PyAV 未安装，无法转换格式")
        os.unlink(aiff_path)
        return b''

    try:
        output_buf = io.BytesIO()
        in_container = av.open(aiff_path)
        in_stream = next(s for s in in_container.streams if s.type == 'audio')

        out_container = av.open(output_buf, mode='w', format='webm')
        out_stream = out_container.add_stream('libopus', rate=48000)
        out_stream.layout = 'mono'

        resampler = av.AudioResampler(format='fltp', layout='mono', rate=48000)

        for frame in in_container.decode(in_stream):
            for rf in resampler.resample(frame):
                rf.pts = None
                for pkt in out_stream.encode(rf):
                    out_container.mux(pkt)

        for pkt in out_stream.encode(None):
            out_container.mux(pkt)

        out_container.close()
        in_container.close()

        output_buf.seek(0)
        webm_bytes = output_buf.read()

        # 验证 EBML header
        has_ebml = len(webm_bytes) >= 2 and webm_bytes[0] == 0x1a and webm_bytes[1] == 0x45
        print(f"WebM 大小: {len(webm_bytes)} bytes，magic: {webm_bytes[:4].hex()}，EBML header: {'✅' if has_ebml else '❌'}")
        return webm_bytes

    except Exception as e:
        print(f"PyAV 转换失败: {e}")
        return b''
    finally:
        try:
            os.unlink(aiff_path)
        except Exception:
            pass


async def test_websocket():
    print(f"\n{'='*60}")
    print("ASR WebSocket 端到端测试（完整 WebM 模式）")
    print(f"{'='*60}")
    print(f"连接到: {WS_URL}")

    webm_bytes = generate_complete_webm()
    if not webm_bytes:
        print("❌ 无法生成测试音频")
        return False

    received_transcript = False
    messages_received = []

    try:
        async with websockets.connect(WS_URL, ping_interval=None) as ws:
            print("\n✅ WebSocket 连接成功")

            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            print(f"📨 收到: {json.dumps(msg, ensure_ascii=False)}")
            messages_received.append(msg)

            await ws.send(json.dumps({"type": "config_update", "asr_language": "en", "translate_enabled": False}))
            print("📤 发送配置: asr_language=en")

            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            print(f"📨 收到: {json.dumps(msg, ensure_ascii=False)}")
            messages_received.append(msg)

            await ws.send(json.dumps({"type": "start_listening"}))
            print("📤 发送: start_listening")

            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            print(f"📨 收到: {json.dumps(msg, ensure_ascii=False)}")
            messages_received.append(msg)

            # 发送完整 WebM 文件（不分块！）
            b64 = base64.b64encode(webm_bytes).decode('utf-8')
            await ws.send(json.dumps({"type": "audio_chunk", "data": b64}))
            print(f"\n📤 发送完整 WebM 片段: {len(webm_bytes)} bytes → {len(b64)} chars base64")

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
                        print(f"\n🎉 收到字幕！is_final={msg.get('is_final')}, text: {msg.get('text')}")
                        break
                    elif msg_type == 'error':
                        print(f"❌ 错误: {msg.get('message', '')}")
                    else:
                        print(f"📨 收到: {json.dumps(msg, ensure_ascii=False)[:100]}")

                except asyncio.TimeoutError:
                    print(".", end="", flush=True)
                    continue

            if not received_transcript:
                print("\n⏱ 等待超时，未收到字幕")

            await ws.send(json.dumps({"type": "stop_listening"}))
            print("\n📤 发送: stop_listening")

    except ConnectionRefusedError:
        print("❌ 连接被拒绝，请确保后端服务正在运行")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    print(f"\n{'='*60}")
    print("测试结果")
    print(f"{'='*60}")
    print(f"收到消息总数: {len(messages_received)}")
    print(f"收到 transcript 消息: {'✅ 是' if received_transcript else '❌ 否'}")
    print(f"消息类型序列: {[m.get('type') for m in messages_received]}")

    if received_transcript:
        print("\n✅ 测试通过！ASR 识别和字幕推送功能正常工作")
        return True
    else:
        print("\n❌ 测试失败：未收到 transcript 消息")
        print("   请检查后端日志: cat /tmp/backend_new.log | tail -30")
        return False


if __name__ == "__main__":
    result = asyncio.run(test_websocket())
    sys.exit(0 if result else 1)
