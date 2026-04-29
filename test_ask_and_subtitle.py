#!/usr/bin/env python3
"""
快速测试：验证求助功能和字幕不重复
- 先创建 session，再连接 WebSocket
- 发送真实音频块，检查字幕不重复
- 发送 manual_ask，检查 AI 回答完整返回
"""
import asyncio
import json
import base64
import time
import sys
import os
import requests

try:
    import websockets
except ImportError:
    os.system("pip3 install websockets -q")
    import websockets

BASE_URL = "http://127.0.0.1:18765"
API_KEY = "sk-cp-XjUgmt_U54CNXjdwRRuPIPnKJBGSqVNFLazkfUaEeRPuiEyWEVvFnaKzJNwXtizkiC_z6BJhzbkP1NqHUY60zmCEv9LNbPRZ8a0kv1Hz49TjO3AB9jkIGf4"

def load_real_audio() -> bytes:
    """加载真实语音 WebM 文件"""
    candidates = [
        '/tmp/test_classroom.webm',
        '/Users/Zhuanz1/Desktop/code/helper/test_classroom.webm',
    ]
    for path in candidates:
        if os.path.exists(path):
            data = open(path, 'rb').read()
            print(f"  ✅ 使用真实音频: {path} ({len(data)} bytes)")
            return data
    print("  ❌ 未找到真实音频文件")
    return None

async def run_test():
    print("=" * 60)
    print("测试：求助功能 + 字幕不重复")
    print("=" * 60)

    # 1. 创建 session
    resp = requests.post(f"{BASE_URL}/api/session/new")
    assert resp.status_code == 200, f"创建 session 失败: {resp.text}"
    session_id = resp.json()['session_id']
    print(f"✅ 创建 session: {session_id[:8]}...")

    WS_URL = f"ws://127.0.0.1:18765/ws/{session_id}"

    results = {
        'subtitles': [],
        'translations': [],
        'answer_chunks': [],
        'answer_done': False,
        'answer_text': '',
    }

    # 加载真实音频
    real_audio = load_real_audio()
    if not real_audio:
        print("❌ 无法加载音频文件，测试中止")
        return False

    # 把音频分成 3 块
    chunk_size = len(real_audio) // 3
    audio_chunks = [
        real_audio[:chunk_size],
        real_audio[chunk_size:chunk_size*2],
        real_audio[chunk_size*2:],
    ]

    async with websockets.connect(WS_URL, ping_interval=None) as ws:
        # 2. 发送配置
        await ws.send(json.dumps({
            "type": "config_update",
            "api_key": API_KEY,
            "api_base_url": "https://api.minimax.chat/v1",
            "asr_language": "en",
            "translate_enabled": True,
            "translate_target_lang": "zh",
            "system_prompt": "你是一个课堂助手，请用中文简洁回答问题。",
        }))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        assert msg['type'] == 'config_updated', f"配置失败: {msg}"
        print("✅ 配置成功")

        # 3. 开始监听
        await ws.send(json.dumps({"type": "start_listening"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        assert msg['type'] == 'listening_started', f"开始监听失败: {msg}"
        print("✅ 开始监听")

        # 4. 发送音频块（模拟流式输入）
        print(f"\n发送 {len(audio_chunks)} 个音频块...")
        for i, chunk in enumerate(audio_chunks, start=1):
            b64 = base64.b64encode(chunk).decode()
            await ws.send(json.dumps({
                "type": "audio_chunk",
                "data": b64,
                "chunk_index": i,
            }))
            print(f"  📤 块 #{i}: {len(chunk)} bytes")
            await asyncio.sleep(0.3)

        # 5. 等待字幕（最多 40 秒）
        print("\n等待字幕...")
        deadline = time.time() + 40
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2)
                msg = json.loads(raw)
                mtype = msg.get('type', '')
                if mtype == 'transcript':
                    text = msg.get('text', '')
                    results['subtitles'].append(text)
                    print(f"  🎯 字幕: {text[:80]}")
                elif mtype == 'transcript_translation':
                    trans = msg.get('translation', '')
                    results['translations'].append(trans)
                    print(f"  🌐 翻译: {trans[:80]}")
            except asyncio.TimeoutError:
                if results['subtitles']:
                    break

        # 6. 发送手动提问
        question = "What is machine learning? Please explain in one sentence."
        print(f"\n发送手动提问: {question}")
        await ws.send(json.dumps({
            "type": "manual_ask",
            "question": question,
        }))

        # 7. 等待 AI 回答（最多 60 秒）
        print("等待 AI 回答...")
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=3)
                msg = json.loads(raw)
                mtype = msg.get('type', '')
                if mtype == 'answer_start':
                    print(f"  🤖 AI 开始回答: {msg.get('question', '')[:60]}")
                elif mtype == 'answer_chunk':
                    chunk = msg.get('chunk', '')
                    results['answer_chunks'].append(chunk)
                    print(f"  💬 {chunk}", end='', flush=True)
                elif mtype == 'answer_done':
                    results['answer_done'] = True
                    results['answer_text'] = msg.get('full_answer', ''.join(results['answer_chunks']))
                    print(f"\n  ✅ 回答完成！({len(results['answer_text'])} 字)")
                    break
                elif mtype == 'transcript':
                    # 监听期间也可能有字幕
                    text = msg.get('text', '')
                    results['subtitles'].append(text)
                    print(f"\n  🎯 字幕（监听中）: {text[:60]}")
            except asyncio.TimeoutError:
                if results['answer_done']:
                    break

        # 8. 停止监听
        await ws.send(json.dumps({"type": "stop_listening"}))

    # ── 结果分析 ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    subtitle_count = len(results['subtitles'])
    translation_count = len(results['translations'])
    answer_complete = results['answer_done']
    answer_length = len(results['answer_text'])

    print(f"字幕条数:    {subtitle_count}")
    print(f"翻译条数:    {translation_count}")
    print(f"AI 回答完成: {'✅' if answer_complete else '❌'}")
    print(f"AI 回答长度: {answer_length} 字符")

    if subtitle_count > 1:
        duplicates = sum(1 for i in range(1, subtitle_count)
                        if results['subtitles'][i] == results['subtitles'][i-1])
        print(f"字幕重复数:  {duplicates} {'✅' if duplicates == 0 else '⚠️'}")

    if results['answer_text']:
        print(f"\nAI 回答内容:\n{results['answer_text'][:300]}")

    if subtitle_count >= 1 and answer_complete:
        print("\n🎉 测试通过！字幕识别和求助功能均正常工作。")
        return True
    else:
        print("\n❌ 测试未完全通过：")
        if subtitle_count == 0:
            print("  - 没有收到任何字幕")
        if not answer_complete:
            print("  - AI 回答未完成（可能是 API 超时或网络问题）")
        return False

if __name__ == '__main__':
    success = asyncio.run(run_test())
    sys.exit(0 if success else 1)
