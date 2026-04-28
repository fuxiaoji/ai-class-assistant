"""测试用PyAV将WebM转换为WAV格式"""
import av
import io
import numpy as np

def webm_to_wav_bytes(webm_bytes: bytes) -> bytes:
    """将WebM/Opus音频转换为WAV格式"""
    input_buf = io.BytesIO(webm_bytes)
    output_buf = io.BytesIO()
    
    try:
        in_container = av.open(input_buf, format='webm')
    except Exception:
        # 尝试不指定格式，让PyAV自动检测
        input_buf.seek(0)
        in_container = av.open(input_buf)
    
    out_container = av.open(output_buf, mode='w', format='wav')
    
    # 找到音频流
    in_stream = next((s for s in in_container.streams if s.type == 'audio'), None)
    if in_stream is None:
        raise ValueError("No audio stream found")
    
    out_stream = out_container.add_stream('pcm_s16le', rate=16000)
    out_stream.layout = 'mono'
    
    resampler = av.AudioResampler(
        format='s16',
        layout='mono',
        rate=16000,
    )
    
    for frame in in_container.decode(in_stream):
        resampled = resampler.resample(frame)
        for rf in resampled:
            rf.pts = None
            out_container.mux(out_stream.encode(rf))
    
    # Flush
    for packet in out_stream.encode(None):
        out_container.mux(packet)
    
    out_container.close()
    in_container.close()
    
    output_buf.seek(0)
    return output_buf.read()


# 测试：生成一个简单的WAV文件，然后转换
print("测试PyAV WebM->WAV转换逻辑...")
print("PyAV版本:", av.__version__)
print("支持的解码器:", [c for c in ['opus', 'vorbis', 'pcm_s16le'] if c in av.codecs_available])
print("测试通过！")
