"""
ASR WebSocket 端到端测试脚本
模拟前端流式 timeslice 模式：header 块 + 后续块拼接发送

流式方案验证：
  块 #1：完整 WebM（含 EBML header），直接发送
  块 #2+：header 块 + 裸帧拼接成完整 WebM，再发送
  → 后端每次都能解析，实现流式字幕
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


def generate_webm_chunks() -> list[bytes]:
    """
    生成模拟 timeslice 模式的多个 WebM 块：
    - 块 #1：完整 WebM（含 EBML header）
    - 块 #2+：header 块 + 裸帧拼接
    """
    with tempfile.NamedTemporaryFile(suffix='.aiff', delete=False) as f:
        aiff_path = f.name

    test_text = "Hello, this is a streaming test. Machine learning is a branch of artificial intelligence. The model can recognize speech in real time."
    print(f"生成测试语音: '{test_text[:60]}...'")

    try:
        result = subprocess.run(['say', test_text, '-o', aiff_path],
                                capture_output=True, timeout=20)
        if result.returncode != 0:
            print(f"say 命令失败")
            return []
        print(f"AIFF 大小: {os.path.getsize(aiff_path)} bytes")
    except Exception as e:
        print(f"say 命令异常: {e}")
        return []

    if not HAS_AV:
        print("PyAV 未安装")
        os.unlink(aiff_path)
        return []

    try:
        # 生成完整 WebM
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
        full_webm = output_buf.read()
        print(f"完整 WebM: {len(full_webm)} bytes，magic: {full_webm[:4].hex()}")

        # 模拟 timeslice 分块：将完整 WebM 分成 3 块
        # 块 #1 包含 EBML header（约前 1/3）
        # 块 #2、#3 是后续音频数据
        total = len(full_webm)
        chunk_size = total // 3

        # 找到 EBML header 的边界（简单按比例分割）
        chunk1 = full_webm[:chunk_size]
        chunk2 = full_webm[chunk_size:chunk_size*2]
        chunk3 = full_webm[chunk_size*2:]

        print(f"\n模拟 timeslice 分块：")
        print(f"  块 #1: {len(chunk1)} bytes，EBML header: {chunk1[0]==0x1a and chunk1[1]==0x45}")
        print(f"  块 #2: {len(chunk2)} bytes（裸帧）")
        print(f"  块 #3: {len(chunk3)} bytes（裸帧）")

        # 模拟前端拼接逻辑：
        # 块 #1 直接发送（完整 WebM）
        # 块 #2 发送：chunk1 + chunk2（header + 新帧）
        # 块 #3 发送：chunk1 + chunk3（header + 新帧）
        send_chunk1 = chunk1
        send_chunk2 = bytes(chunk1) + bytes(chunk2)
        send_chunk3 = bytes(chunk1) + bytes(chunk3)

        print(f"\n实际发送大小：")
        print(f"  发送 #1: {len(send_chunk1)} bytes（原始第1块）")
        print(f"  发送 #2: {len(send_chunk2)} bytes（header + 第2块）")
        print(f"  发送 #3: {len(send_chunk3)} bytes（header + 第3块）")

        return [send_chunk1, send_chunk2, send_chunk3]

    except Exception as e:
        print(f"PyAV 处理失败: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        try:
            os.unlink(aiff_path)
        except Exception:
            pass


async def test_websocket():
    print(f"\n{'='*60}")
    print("ASR WebSocket 流式测试（timeslice header+chunk 拼接模式）")
    print(f"{'='*60}")
    print(f"连接到: {WS_URL}")

    chunks = generate_webm_chunks()
    if not chunks:
        print("❌ 无法生成测试音频")
        return False

    received_transcripts = []
    messages_received = []

    try:
        async with websockets.connect(WS_URL, ping_interval=None) as ws:
            print("\n✅ WebSocket 连接成功")

            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            print(f"📨 {msg['type']}: {msg.get('message', '')}")
            messages_received.append(msg)

            await ws.send(json.dumps({"type": "config_update", "asr_language": "en", "translate_enabled": False}))
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            print(f"📨 {msg['type']}")
            messages_received.append(msg)

            await ws.send(json.dumps({"type": "start_listening"}))
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            print(f"📨 {msg['type']}")
            messages_received.append(msg)

            print(f"\n开始流式发送 {len(chunks)} 个音频块...")

            # 并发：发送音频块的同时监听响应
            async def send_chunks():
                for i, chunk in enumerate(chunks):
                    b64 = base64.b64encode(chunk).decode('utf-8')
                    await ws.send(json.dumps({"type": "audio_chunk", "data": b64}))
                    print(f"📤 发送块 #{i+1}: {len(chunk)} bytes → {len(b64)} chars base64")
                    await asyncio.sleep(2)  # 模拟 2 秒间隔

            async def recv_messages():
                deadline = asyncio.get_event_loop().time() + 90
                while asyncio.get_event_loop().time() < deadline:
                    remaining = deadline - asyncio.get_event_loop().time()
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 3))
                        msg = json.loads(raw)
                        messages_received.append(msg)
                        if msg['type'] == 'transcript':
                            received_transcripts.append(msg)
                            print(f"\n🎉 字幕 #{len(received_transcripts)}: {msg.get('text', '')[:80]}")
                        elif msg['type'] == 'error':
                            print(f"❌ 错误: {msg.get('message', '')}")
                        else:
                            print(f"📨 {msg['type']}")
                    except asyncio.TimeoutError:
                        print(".", end="", flush=True)

            # 并发执行发送和接收
            await asyncio.gather(
                send_chunks(),
                asyncio.wait_for(recv_messages(), timeout=90)
            )

    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass
    except ConnectionRefusedError:
        print("❌ 连接被拒绝，请确保后端服务正在运行")
        return False
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

    print(f"\n\n{'='*60}")
    print("测试结果")
    print(f"{'='*60}")
    print(f"发送块数: {len(chunks)}")
    print(f"收到字幕数: {len(received_transcripts)}")
    for i, t in enumerate(received_transcripts):
        print(f"  字幕 #{i+1}: {t.get('text', '')[:80]}")

    if received_transcripts:
        print("\n✅ 流式 ASR 测试通过！")
        return True
    else:
        print("\n❌ 未收到字幕，请检查后端日志")
        print("   cat /tmp/backend_new.log | tail -30")
        return False


if __name__ == "__main__":
    result = asyncio.run(test_websocket())
    sys.exit(0 if result else 1)
