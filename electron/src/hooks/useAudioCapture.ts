/**
 * 音频采集 Hook（Web Speech API 版本）
 * 使用浏览器原生 Web Speech API 做实时语音识别，无需 OpenAI Whisper Key
 * Electron 和 Chrome 均内置支持，完全免费
 */
import { useRef, useState, useCallback, useEffect } from 'react';

declare global {
  interface Window {
    SpeechRecognition: typeof SpeechRecognition;
    webkitSpeechRecognition: typeof SpeechRecognition;
  }
}

interface UseAudioCaptureOptions {
  /** 收到识别文字的回调 */
  onTranscript: (text: string, isFinal: boolean) => void;
  /** 音量变化回调（0-1） */
  onVolumeChange?: (volume: number) => void;
  /** 识别语言，默认中文 */
  lang?: string;
}

export function useAudioCapture({
  onTranscript,
  onVolumeChange,
  lang = 'zh-CN',
}: UseAudioCaptureOptions) {
  const [isCapturing, setIsCapturing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [volume, setVolume] = useState(0);

  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const isCapturingRef = useRef(false);

  const onTranscriptRef = useRef(onTranscript);
  const onVolumeChangeRef = useRef(onVolumeChange);
  useEffect(() => { onTranscriptRef.current = onTranscript; }, [onTranscript]);
  useEffect(() => { onVolumeChangeRef.current = onVolumeChange; }, [onVolumeChange]);

  const startVolumeMonitor = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
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
      console.warn('音量监控启动失败:', e);
    }
  }, []);

  const start = useCallback(async () => {
    setError(null);

    const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionAPI) {
      setError('当前环境不支持 Web Speech API，请使用 Chrome 或 Electron');
      return;
    }

    await startVolumeMonitor();

    const recognition = new SpeechRecognitionAPI();
    recognition.lang = lang;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const text = result[0].transcript.trim();
        if (!text) continue;
        onTranscriptRef.current(text, result.isFinal);
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      console.error('[ASR] 识别错误:', event.error);
      if (event.error === 'not-allowed') {
        setError('麦克风权限被拒绝，请在系统设置中允许访问麦克风');
        setIsCapturing(false);
        isCapturingRef.current = false;
      } else if (event.error === 'network') {
        setError('网络错误：Web Speech API 需要连接网络（使用 Google 语音服务）');
      }
      // no-speech 等错误忽略，自动重启
    };

    recognition.onend = () => {
      if (isCapturingRef.current) {
        try { recognition.start(); } catch (e) { /* 忽略 */ }
      }
    };

    recognitionRef.current = recognition;
    isCapturingRef.current = true;

    try {
      recognition.start();
      setIsCapturing(true);
    } catch (e) {
      setError('语音识别启动失败: ' + (e instanceof Error ? e.message : String(e)));
      isCapturingRef.current = false;
    }
  }, [lang, startVolumeMonitor]);

  const stop = useCallback(() => {
    isCapturingRef.current = false;
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    if (recognitionRef.current) {
      recognitionRef.current.onend = null;
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
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
      if (recognitionRef.current) {
        recognitionRef.current.onend = null;
        recognitionRef.current.stop();
      }
      streamRef.current?.getTracks().forEach(t => t.stop());
      audioCtxRef.current?.close();
    };
  }, []);

  return { start, stop, isCapturing, volume, error };
}
