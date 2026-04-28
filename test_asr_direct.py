"""
直接测试 ASR 模块（绕过 WebSocket），验证 PyAV 转换和 faster-whisper 识别是否正常工作

用法：
    python3 test_asr_direct.py [音频文件路径]
    
    如果不提供音频文件，使用 macOS say 命令生成测试语音
"""
import asyncio
import io
import sys
import os
import subprocess
import tempfile

# 添加 backend 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))


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


def aiff_to_webm(aiff_path: str) -> bytes:
    """将 AIFF 转换为 WebM/Opus（模拟浏览器 MediaRecorder 输出）"""
    import av
    
    output_buf = io.BytesIO()
    
    in_container = av.open(aiff_path)
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


async def main():
    print("=" * 60)
    print("ASR 直接测试（PyAV 转换 + faster-whisper 识别）")
    print("=" * 60)
    
    # 准备测试音频
    audio_file = sys.argv[1] if len(sys.argv) > 1 else None
    webm_bytes = None
    
    if audio_file and os.path.exists(audio_file):
        print(f"使用音频文件: {audio_file}")
        if audio_file.endswith('.aiff') or audio_file.endswith('.wav'):
            print("转换为 WebM/Opus（模拟浏览器输出）...")
            webm_bytes = aiff_to_webm(audio_file)
            print(f"WebM 大小: {len(webm_bytes)} bytes")
        else:
            with open(audio_file, 'rb') as f:
                webm_bytes = f.read()
    else:
        # 使用 say 生成英文语音（更容易识别）
        with tempfile.NamedTemporaryFile(suffix='.aiff', delete=False) as f:
            tmp_path = f.name
        
        test_text = "Hello, this is a test. Machine learning is a branch of artificial intelligence."
        print(f"生成测试语音: '{test_text}'")
        
        if generate_speech_aiff(test_text, tmp_path):
            print(f"AIFF 文件: {tmp_path} ({os.path.getsize(tmp_path)} bytes)")
            print("转换为 WebM/Opus...")
            webm_bytes = aiff_to_webm(tmp_path)
            print(f"WebM 大小: {len(webm_bytes)} bytes")
            os.unlink(tmp_path)
        else:
            print("❌ 无法生成测试语音")
            return
    
    if not webm_bytes:
        print("❌ 无音频数据")
        return
    
    # 测试 PyAV 转换
    print("\n--- 测试 PyAV 转换（WebM → WAV）---")
    from app.core.asr import _convert_to_wav
    
    wav_bytes = _convert_to_wav(webm_bytes)
    if wav_bytes:
        print(f"✅ 转换成功: {len(webm_bytes)} → {len(wav_bytes)} bytes")
    else:
        print("❌ 转换失败")
        return
    
    # 测试 faster-whisper 识别
    print("\n--- 测试 faster-whisper 识别 ---")
    print("加载模型（首次运行需要下载，请稍候...）")
    
    from app.core.asr import asr_service
    
    start_time = asyncio.get_event_loop().time()
    result = await asr_service.transcribe(webm_bytes, language="en")
    elapsed = asyncio.get_event_loop().time() - start_time
    
    print(f"识别耗时: {elapsed:.2f}s")
    
    if result:
        print(f"✅ 识别成功！")
        print(f"识别结果: {result}")
    else:
        print("⚠️  识别结果为空（可能是静音或模型加载中）")
        
        # 尝试中文
        print("\n尝试中文识别...")
        result_zh = await asr_service.transcribe(webm_bytes, language="zh")
        if result_zh:
            print(f"✅ 中文识别: {result_zh}")
        else:
            print("⚠️  中文识别也为空")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
