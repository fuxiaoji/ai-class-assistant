/**
 * 音频采集 Hook — 麦克风录音 + 发送音频块给后端
 *
 * 架构：前端录音 → base64 编码 → 通过 WebSocket 发送 audio_chunk → 后端 faster-whisper 识别
 * 优点：完全离线识别，无需 Google 服务，国内网络正常使用
 *
 * 录音参数：
 *   - MediaRecorder + WebM/Opus 格式（浏览器原生支持）
 *   - 每 2 秒发送一个音频块（可调整 CHUNK_INTERVAL_MS）
 *   - 同时用 AnalyserNode 实时监控音量
 */
import { useRef, useState, useCallback, useEffect } from 'react';

/** 每个音频块的时长（毫秒）*/
const CHUNK_INTERVAL_MS = 2000;

interface UseAudioCaptureOptions {
  /** 收到后端识别文字的回调（由 App.tsx 通过 WebSocket 消息触发，此 hook 不直接调用） */
  onTranscript?: (text: string, isFinal: boolean) => void;
  /** 音量变化回调（0-1） */
  onVolumeChange?: (volume: number) => void;
  /** 收到音频块时的回调（base64 编码的 WebM 数据） */
  onAudioChunk: (base64Data: string) => void;
}

export function useAudioCapture({
  onVolumeChange,
  onAudioChunk,
}: UseAudioCaptureOptions) {
  const [isCapturing, setIsCapturing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [volume, setVolume] = useState(0);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const isCapturingRef = useRef(false);

  const onVolumeChangeRef = useRef(onVolumeChange);
  const onAudioChunkRef = useRef(onAudioChunk);
  useEffect(() => { onVolumeChangeRef.current = onVolumeChange; }, [onVolumeChange]);
  useEffect(() => { onAudioChunkRef.current = onAudioChunk; }, [onAudioChunk]);

  /** 启动音量监控（AnalyserNode） */
  const startVolumeMonitor = useCallback((stream: MediaStream) => {
    try {
      const audioCtx = new AudioContext();
      audioCtxRef.current = audioCtx;
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      analyserRef.current = analyser;

      const loop = () => {
        if (!analyserRef.current) return;
        const data = new Uint8Array(analyserRef.current.frequencyBinCount);
        analyserRef.current.getByteTimeDomainData(data);
        let sum = 0;
        for (const v of data) {
          const n = (v - 128) / 128;
          sum += n * n;
        }
        const rms = Math.sqrt(sum / data.length);
        setVolume(rms);
        onVolumeChangeRef.current?.(rms);
        animFrameRef.current = requestAnimationFrame(loop);
      };
      animFrameRef.current = requestAnimationFrame(loop);
    } catch (e) {
      console.warn('[AudioCapture] 音量监控启动失败:', e);
    }
  }, []);

  const start = useCallback(async () => {
    setError(null);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      isCapturingRef.current = true;

      // 启动音量监控
      startVolumeMonitor(stream);

      // 选择最佳音频格式
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : '';

      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;

      recorder.ondataavailable = async (event) => {
        if (!event.data || event.data.size < 500) return; // 跳过过小的块（静音）
        try {
          const arrayBuffer = await event.data.arrayBuffer();
          const uint8 = new Uint8Array(arrayBuffer);
          // 转 base64
          let binary = '';
          for (let i = 0; i < uint8.length; i++) {
            binary += String.fromCharCode(uint8[i]);
          }
          const base64 = btoa(binary);
          onAudioChunkRef.current(base64);
        } catch (e) {
          console.error('[AudioCapture] 音频块处理失败:', e);
        }
      };

      recorder.onerror = (e) => {
        console.error('[AudioCapture] 录音错误:', e);
        setError('录音出错，请重试');
      };

      // 每 CHUNK_INTERVAL_MS 毫秒触发一次 ondataavailable
      recorder.start(CHUNK_INTERVAL_MS);
      setIsCapturing(true);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes('Permission') || msg.includes('NotAllowed')) {
        setError('麦克风权限被拒绝，请在系统设置中允许访问麦克风');
      } else {
        setError('麦克风启动失败: ' + msg);
      }
      isCapturingRef.current = false;
    }
  }, [startVolumeMonitor]);

  const stop = useCallback(() => {
    isCapturingRef.current = false;
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop();
    }
    recorderRef.current = null;
    streamRef.current?.getTracks().forEach(t => t.stop());
    audioCtxRef.current?.close();
    streamRef.current = null;
    audioCtxRef.current = null;
    analyserRef.current = null;
    setIsCapturing(false);
    setVolume(0);
  }, []);

  useEffect(() => {
    return () => {
      isCapturingRef.current = false;
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      if (recorderRef.current && recorderRef.current.state !== 'inactive') {
        recorderRef.current.stop();
      }
      streamRef.current?.getTracks().forEach(t => t.stop());
      audioCtxRef.current?.close();
    };
  }, []);

  return { start, stop, isCapturing, volume, error };
}
