/**
 * 音频采集 Hook
 * 使用 Web Audio API + MediaRecorder 采集麦克风音频
 * 内置简单的静音检测（VAD），避免发送无效音频
 */
import { useRef, useState, useCallback } from 'react';

interface UseAudioCaptureOptions {
  /** 每个音频块的时长（毫秒），默认 3000ms */
  chunkDurationMs?: number;
  /** 静音阈值（0-1），低于此值认为是静音，默认 0.01 */
  silenceThreshold?: number;
  /** 收到音频块的回调，参数为 base64 编码的音频数据 */
  onAudioChunk: (base64Data: string) => void;
  /** 音量变化回调（0-1） */
  onVolumeChange?: (volume: number) => void;
}

export function useAudioCapture({
  chunkDurationMs = 3000,
  silenceThreshold = 0.01,
  onAudioChunk,
  onVolumeChange,
}: UseAudioCaptureOptions) {
  const [isCapturing, setIsCapturing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [volume, setVolume] = useState(0);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  /** 计算当前音量 RMS */
  const measureVolume = useCallback(() => {
    if (!analyserRef.current) return 0;
    const data = new Uint8Array(analyserRef.current.frequencyBinCount);
    analyserRef.current.getByteTimeDomainData(data);
    let sum = 0;
    for (const v of data) {
      const normalized = (v - 128) / 128;
      sum += normalized * normalized;
    }
    return Math.sqrt(sum / data.length);
  }, []);

  /** 音量监控循环 */
  const startVolumeMonitor = useCallback(() => {
    const loop = () => {
      const v = measureVolume();
      setVolume(v);
      onVolumeChange?.(v);
      animFrameRef.current = requestAnimationFrame(loop);
    };
    animFrameRef.current = requestAnimationFrame(loop);
  }, [measureVolume, onVolumeChange]);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000,
        },
      });
      streamRef.current = stream;

      // 设置音量分析器
      const audioCtx = new AudioContext();
      audioCtxRef.current = audioCtx;
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      analyserRef.current = analyser;

      // 选择最佳 MIME 类型
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : 'audio/ogg';

      const recorder = new MediaRecorder(stream, { mimeType });
      recorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType });
        chunksRef.current = [];

        // VAD：检查是否有足够音量
        const currentVolume = measureVolume();
        if (blob.size > 2000 && currentVolume > silenceThreshold) {
          const reader = new FileReader();
          reader.onloadend = () => {
            const base64 = (reader.result as string).split(',')[1];
            if (base64) onAudioChunk(base64);
          };
          reader.readAsDataURL(blob);
        }

        // 如果还在录制，继续下一个块
        if (recorderRef.current?.state === 'inactive' && isCapturing) {
          recorderRef.current.start();
          setTimeout(() => recorderRef.current?.stop(), chunkDurationMs);
        }
      };

      // 开始录制
      recorder.start();
      setTimeout(() => recorder.stop(), chunkDurationMs);

      // 持续循环录制
      const loopRecord = () => {
        if (!recorderRef.current) return;
        if (recorderRef.current.state === 'inactive') {
          recorderRef.current.start();
          setTimeout(() => {
            recorderRef.current?.stop();
            setTimeout(loopRecord, 100);
          }, chunkDurationMs);
        }
      };
      setTimeout(loopRecord, chunkDurationMs + 100);

      startVolumeMonitor();
      setIsCapturing(true);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '麦克风访问失败';
      setError(msg);
      console.error('音频采集失败:', err);
    }
  }, [chunkDurationMs, silenceThreshold, onAudioChunk, measureVolume, startVolumeMonitor, isCapturing]);

  const stop = useCallback(() => {
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    if (recorderRef.current?.state !== 'inactive') recorderRef.current?.stop();
    streamRef.current?.getTracks().forEach(t => t.stop());
    audioCtxRef.current?.close();
    streamRef.current = null;
    recorderRef.current = null;
    audioCtxRef.current = null;
    analyserRef.current = null;
    setIsCapturing(false);
    setVolume(0);
  }, []);

  return { start, stop, isCapturing, volume, error };
}
