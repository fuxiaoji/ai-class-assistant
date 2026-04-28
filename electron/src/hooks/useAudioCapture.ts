/**
 * 音频采集 Hook — 麦克风录音 + 发送完整 WebM 文件给后端
 *
 * 核心修复：
 *   MediaRecorder 在 timeslice 模式下，每个小块都是裸 Opus 帧，
 *   没有 WebM 容器头（EBML header），PyAV/ffmpeg 无法解析。
 *
 *   正确方案：每隔 SEGMENT_DURATION_MS 毫秒，stop() 当前录音再 start() 新录音。
 *   每次 stop() 触发 ondataavailable 时，MediaRecorder 会产生一个完整的 WebM 文件
 *   （包含完整的 EBML header），PyAV 和 faster-whisper 都能正确解析。
 *
 * 架构：
 *   前端录音（完整 WebM 片段）→ base64 → WebSocket audio_chunk → 后端 PyAV 转 WAV → faster-whisper
 */
import { useRef, useState, useCallback, useEffect } from 'react';

/** 每个录音片段的时长（毫秒）。越短延迟越低，但太短会导致识别不准确 */
const SEGMENT_DURATION_MS = 4000;

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
  const segmentTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isCapturingRef = useRef(false);
  const segmentCountRef = useRef(0);
  const mimeTypeRef = useRef('');

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

  /**
   * 录制一个片段：创建新的 MediaRecorder，录制 SEGMENT_DURATION_MS 毫秒后停止
   * 停止时 ondataavailable 会收到一个完整的 WebM 文件（含 EBML header）
   */
  const recordSegment = useCallback((stream: MediaStream) => {
    if (!isCapturingRef.current) return;

    const mimeType = mimeTypeRef.current;
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    recorderRef.current = recorder;

    recorder.ondataavailable = async (event) => {
      if (!event.data || event.data.size < MIN_CHUNK_SIZE) {
        console.debug(`[AudioCapture] 片段 #${segmentCountRef.current} 过小（${event.data?.size ?? 0} bytes），跳过`);
        return;
      }
      try {
        const arrayBuffer = await event.data.arrayBuffer();
        const uint8 = new Uint8Array(arrayBuffer);

        // 验证是否有 EBML header（WebM 的魔数是 0x1A 0x45 0xDF 0xA3）
        const hasEBML = uint8[0] === 0x1a && uint8[1] === 0x45;
        const hasRIFF = uint8[0] === 0x52 && uint8[1] === 0x49; // RIFF (WAV)
        console.log(
          `[AudioCapture] 片段 #${segmentCountRef.current}: ${uint8.length} bytes, ` +
          `magic=${uint8.slice(0, 4).join(',')}, ` +
          `WebM=${hasEBML}, WAV=${hasRIFF}`
        );

        if (!hasEBML && !hasRIFF) {
          console.warn('[AudioCapture] 音频块缺少容器头，跳过（裸帧无法识别）');
          return;
        }

        const base64 = uint8ToBase64(uint8);
        console.log(`[AudioCapture] 发送片段 #${segmentCountRef.current}: ${uint8.length} bytes → ${base64.length} chars base64`);
        onAudioChunkRef.current(base64);
      } catch (e) {
        console.error('[AudioCapture] 音频块处理失败:', e);
      }
    };

    recorder.onerror = (e) => {
      console.error('[AudioCapture] 录音错误:', e);
    };

    // 录制完整片段后停止（不用 timeslice，stop() 时才触发 ondataavailable）
    recorder.start();
    segmentCountRef.current++;
    console.log(`[AudioCapture] 开始录制片段 #${segmentCountRef.current}（${SEGMENT_DURATION_MS}ms）`);

    // 定时停止，触发 ondataavailable，然后立即开始下一个片段
    segmentTimerRef.current = setTimeout(() => {
      if (!isCapturingRef.current) return;
      if (recorder.state === 'recording') {
        recorder.stop(); // 停止 → 触发 ondataavailable（完整 WebM 文件）
      }
      // 短暂延迟后开始下一个片段
      setTimeout(() => {
        if (isCapturingRef.current) {
          recordSegment(stream);
        }
      }, 100);
    }, SEGMENT_DURATION_MS);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    segmentCountRef.current = 0;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      isCapturingRef.current = true;

      startVolumeMonitor(stream);

      // 选择最佳格式（优先 WebM/Opus）
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : '';
      mimeTypeRef.current = mimeType;
      console.log(`[AudioCapture] 使用格式: ${mimeType || '浏览器默认'}`);
      console.log(`[AudioCapture] 录音模式: 每 ${SEGMENT_DURATION_MS}ms 一个完整片段（stop/start 循环）`);

      setIsCapturing(true);
      recordSegment(stream);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error('[AudioCapture] 启动失败:', msg);
      if (msg.includes('Permission') || msg.includes('NotAllowed') || msg.includes('denied')) {
        setError('麦克风权限被拒绝，请在系统设置中允许访问麦克风');
      } else {
        setError('麦克风启动失败: ' + msg);
      }
      isCapturingRef.current = false;
    }
  }, [startVolumeMonitor, recordSegment]);

  const stop = useCallback(() => {
    console.log(`[AudioCapture] 停止录音，共录制 ${segmentCountRef.current} 个片段`);
    isCapturingRef.current = false;

    if (segmentTimerRef.current) {
      clearTimeout(segmentTimerRef.current);
      segmentTimerRef.current = null;
    }
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

    setIsCapturing(false);
    setVolume(0);
  }, []);

  useEffect(() => {
    return () => {
      isCapturingRef.current = false;
      if (segmentTimerRef.current) clearTimeout(segmentTimerRef.current);
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
