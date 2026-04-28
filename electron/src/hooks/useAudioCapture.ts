/**
 * 音频采集 Hook — 流式录音 + 实时发送完整 WebM 片段
 *
 * 流式方案原理：
 *   MediaRecorder 在 timeslice 模式下，ondataavailable 每隔 TIMESLICE_MS 触发一次：
 *     - 第 1 块：包含完整 EBML header + 第一段音频数据（可独立解析）
 *     - 第 2+ 块：裸 Opus 帧，没有 EBML header，无法独立解析
 *
 *   解决方案：缓存第 1 块（header 块），后续每次收到新块时，
 *   将 header 块 + 当前块拼接成一个完整的 WebM 文件发送给后端。
 *   这样后端每次收到的都是可解析的完整 WebM，实现真正的流式识别。
 *
 *   延迟 = TIMESLICE_MS（默认 2000ms），比 stop/start 模式更低延迟且无录音中断。
 */
import { useRef, useState, useCallback, useEffect } from 'react';

/** 每隔多少毫秒触发一次 ondataavailable（流式延迟） */
const TIMESLICE_MS = 2000;

/** 最小有效音频块大小（字节），低于此值视为静音跳过 */
const MIN_CHUNK_SIZE = 500;

interface UseAudioCaptureOptions {
  onVolumeChange?: (volume: number) => void;
  onAudioChunk: (base64Data: string) => void;
}

export function useAudioCapture({ onVolumeChange, onAudioChunk }: UseAudioCaptureOptions) {
  const [isCapturing, setIsCapturing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [volume, setVolume] = useState(0);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number | null>(null);

  // 流式关键：缓存第一块（含 EBML header）
  const headerChunkRef = useRef<Uint8Array | null>(null);
  const chunkCountRef = useRef(0);

  const onVolumeChangeRef = useRef(onVolumeChange);
  const onAudioChunkRef = useRef(onAudioChunk);
  useEffect(() => { onVolumeChangeRef.current = onVolumeChange; }, [onVolumeChange]);
  useEffect(() => { onAudioChunkRef.current = onAudioChunk; }, [onAudioChunk]);

  /** 将 Uint8Array 转为 base64（分块处理，避免大数组栈溢出） */
  const uint8ToBase64 = (uint8: Uint8Array): string => {
    const CHUNK = 8192;
    let binary = '';
    for (let i = 0; i < uint8.length; i += CHUNK) {
      binary += String.fromCharCode(...uint8.subarray(i, i + CHUNK));
    }
    return btoa(binary);
  };

  /** 启动音量监控 */
  const startVolumeMonitor = useCallback((stream: MediaStream) => {
    try {
      const ctx = new AudioContext();
      audioCtxRef.current = ctx;
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      src.connect(analyser);
      analyserRef.current = analyser;

      const loop = () => {
        if (!analyserRef.current) return;
        const data = new Uint8Array(analyserRef.current.frequencyBinCount);
        analyserRef.current.getByteTimeDomainData(data);
        let sum = 0;
        for (const v of data) { const n = (v - 128) / 128; sum += n * n; }
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
    headerChunkRef.current = null;
    chunkCountRef.current = 0;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      startVolumeMonitor(stream);

      // 选择最佳格式（优先 WebM/Opus）
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : '';

      console.log(`[AudioCapture] 格式: ${mimeType || '浏览器默认'}`);
      console.log(`[AudioCapture] 流式模式: timeslice=${TIMESLICE_MS}ms，header+chunk 拼接`);

      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;

      recorder.ondataavailable = async (event) => {
        if (!event.data || event.data.size < MIN_CHUNK_SIZE) {
          console.debug(`[AudioCapture] 块 #${chunkCountRef.current + 1} 过小（${event.data?.size ?? 0} bytes），跳过`);
          return;
        }

        const arrayBuffer = await event.data.arrayBuffer();
        const chunk = new Uint8Array(arrayBuffer);
        chunkCountRef.current++;
        const n = chunkCountRef.current;

        // 检测 EBML header（WebM 魔数：0x1A 0x45 0xDF 0xA3）
        const hasEBML = chunk[0] === 0x1a && chunk[1] === 0x45;

        if (n === 1) {
          // 第一块：保存为 header 块（含 EBML header + Tracks 等元数据）
          headerChunkRef.current = chunk;
          console.log(`[AudioCapture] 块 #${n}: ${chunk.length} bytes，EBML header=${hasEBML}，已缓存为 header`);

          // 第一块本身就是完整可解析的 WebM，直接发送
          const base64 = uint8ToBase64(chunk);
          console.log(`[AudioCapture] 发送块 #${n}（完整 WebM）: ${chunk.length} bytes`);
          onAudioChunkRef.current(base64);
        } else {
          // 后续块：拼接 header + 当前块，形成完整 WebM 文件
          const header = headerChunkRef.current;
          if (!header) {
            console.warn(`[AudioCapture] 块 #${n}: 无 header 缓存，跳过`);
            return;
          }

          // 拼接：header 块 + 当前音频块
          const combined = new Uint8Array(header.length + chunk.length);
          combined.set(header, 0);
          combined.set(chunk, header.length);

          console.log(
            `[AudioCapture] 块 #${n}: ${chunk.length} bytes（裸帧），` +
            `拼接后: ${combined.length} bytes，EBML=${combined[0] === 0x1a && combined[1] === 0x45}`
          );

          const base64 = uint8ToBase64(combined);
          console.log(`[AudioCapture] 发送块 #${n}（header+chunk 拼接）: ${combined.length} bytes`);
          onAudioChunkRef.current(base64);
        }
      };

      recorder.onerror = (e) => {
        console.error('[AudioCapture] 录音错误:', e);
      };

      // timeslice 模式：每 TIMESLICE_MS 毫秒触发一次 ondataavailable
      recorder.start(TIMESLICE_MS);
      setIsCapturing(true);
      console.log(`[AudioCapture] 开始流式录音（timeslice=${TIMESLICE_MS}ms）`);

    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error('[AudioCapture] 启动失败:', msg);
      if (msg.includes('Permission') || msg.includes('NotAllowed') || msg.includes('denied')) {
        setError('麦克风权限被拒绝，请在系统设置中允许访问麦克风');
      } else {
        setError('麦克风启动失败: ' + msg);
      }
    }
  }, [startVolumeMonitor]);

  const stop = useCallback(() => {
    console.log(`[AudioCapture] 停止录音，共处理 ${chunkCountRef.current} 个块`);

    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop();
    }
    recorderRef.current = null;
    streamRef.current?.getTracks().forEach(t => t.stop());
    audioCtxRef.current?.close();
    streamRef.current = null;
    audioCtxRef.current = null;
    analyserRef.current = null;
    headerChunkRef.current = null;
    chunkCountRef.current = 0;

    setIsCapturing(false);
    setVolume(0);
  }, []);

  useEffect(() => {
    return () => {
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
