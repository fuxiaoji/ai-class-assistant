/**
 * AI 实时听课助手 - Electron 桌面端主应用组件
 */
import { useEffect, useCallback, useRef, useState } from 'react';
import { useAppStore } from './store/appStore';
import { useWebSocket } from './hooks/useWebSocket';
import { useAudioCapture } from './hooks/useAudioCapture';
import { api } from './services/api';
import { StatusBar } from './components/StatusBar';
import { MicControl } from './components/MicControl';
import { AnswerPanel } from './components/AnswerPanel';
import { TranscriptPanel } from './components/TranscriptPanel';
import { ConfigPanel } from './components/ConfigPanel';
import { ElectronToolbar } from './components/ElectronToolbar';
import { isElectron, onToggleListen, onManualAsk } from './utils/electron';
import type { WSMessage } from './types';

let answerIdCounter = 0;

export default function App() {
  const { state, dispatch } = useAppStore();
  const pendingAnswerId = useRef<string>('');
  const [backendReady, setBackendReady] = useState(false);
  const [alwaysOnTop, setAlwaysOnTop] = useState(false);
  const isListeningRef = useRef(false);
  const sendRef = useRef<(msg: Record<string, unknown>) => void>(() => {});

  // 用 ref 存储最新的 state，供自动发送配置时使用
  const stateRef = useRef(state);
  useEffect(() => { stateRef.current = state; }, [state]);

  const handleWsMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
      case 'connected':
        dispatch({ type: 'SET_CONNECTION_STATUS', payload: 'connected' });
        // 连接成功后自动发送一次配置（确保 localStorage 中的 API Key 立即生效）
        setTimeout(() => {
          const s = stateRef.current;
          if (s.apiKey) {
            sendRef.current({
              type: 'config_update',
              system_prompt: s.config.systemPrompt,
              course_name: s.config.courseName,
              course_materials: s.config.courseMaterials,
              api_key: s.apiKey,
              api_base_url: s.apiBaseUrl,
              asr_language: s.config.asrLanguage,
              translate_enabled: s.config.translateEnabled,
              translate_target_lang: s.config.translateTargetLang,
            });
          }
        }, 300);
        break;
      case 'transcript': {
        // 后端 faster-whisper 识别完成后推送过来的文字（可能附带翻译）
        const id = `t-${Date.now()}-${Math.random()}`;
        dispatch({
          type: 'ADD_TRANSCRIPT',
          payload: {
            id,
            text: msg.text as string,
            translation: msg.translation as string | undefined,
            isQuestion: false,
            timestamp: Date.now()
          }
        });
        break;
      }
      case 'question_detected': {
        const last = state.transcripts[state.transcripts.length - 1];
        if (last) dispatch({ type: 'MARK_TRANSCRIPT_QUESTION', payload: last.id });
        break;
      }
      case 'answer_start': {
        const id = `a-${++answerIdCounter}`;
        pendingAnswerId.current = id;
        dispatch({ type: 'START_STREAMING', payload: { question: msg.question as string, answerId: id } });
        break;
      }
      case 'answer_chunk':
        dispatch({ type: 'APPEND_STREAM_CHUNK', payload: msg.chunk as string });
        break;
      case 'answer_done':
        dispatch({ type: 'FINISH_STREAMING', payload: { answerId: pendingAnswerId.current, fullAnswer: msg.full_answer as string } });
        break;
      case 'error':
        console.error('服务端错误:', msg.message);
        dispatch({ type: 'SET_LISTENING_STATUS', payload: isListeningRef.current ? 'listening' : 'idle' });
        break;
    }
  }, [dispatch, state.transcripts]);

  const { connect, send, status: wsStatus } = useWebSocket({
    onMessage: handleWsMessage,
    onStatusChange: (s) => dispatch({ type: 'SET_CONNECTION_STATUS', payload: s }),
  });

  // 同步 send 到 ref，供 handleWsMessage 中使用
  useEffect(() => { sendRef.current = send as unknown as (msg: Record<string, unknown>) => void; }, [send]);

  // 等待后端就绪
  useEffect(() => {
    const init = async () => {
      if (isElectron()) {
        let retries = 0;
        while (retries < 20) {
          const ok = await api.healthCheck();
          if (ok) { setBackendReady(true); break; }
          await new Promise(r => setTimeout(r, 1000));
          retries++;
        }
        if (retries >= 20) setBackendReady(true);
      } else {
        setBackendReady(true);
      }
    };
    init();
  }, []);

  // 创建会话并连接 WebSocket
  useEffect(() => {
    if (!backendReady) return;
    const initSession = async () => {
      try {
        const { session_id } = await api.createSession();
        dispatch({ type: 'SET_SESSION_ID', payload: session_id });
        connect(session_id);
      } catch (e) {
        console.error('初始化失败:', e);
        dispatch({ type: 'SET_CONNECTION_STATUS', payload: 'error' });
      }
    };
    initSession();
  }, [backendReady]); // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * 收到音频块时，通过 WebSocket 发送给后端
   * 后端用 faster-whisper 识别，识别完成后推送 transcript 消息
   */
  const handleAudioChunk = useCallback((base64Data: string) => {
    send({
      type: 'audio_chunk',
      data: base64Data,
      session_id: state.sessionId,
    });
  }, [send, state.sessionId]);

  const { start: startAudio, stop: stopAudio, isCapturing, volume, error: audioError } = useAudioCapture({
    onAudioChunk: handleAudioChunk,
    onVolumeChange: (v) => dispatch({ type: 'SET_VOLUME', payload: v }),
  });

  const handleStartListening = useCallback(async () => {
    await startAudio();
    send({ type: 'start_listening' });
    dispatch({ type: 'SET_LISTENING_STATUS', payload: 'listening' });
    isListeningRef.current = true;
  }, [startAudio, send, dispatch]);

  const handleStopListening = useCallback(() => {
    stopAudio();
    send({ type: 'stop_listening' });
    dispatch({ type: 'SET_LISTENING_STATUS', payload: 'idle' });
    isListeningRef.current = false;
  }, [stopAudio, send, dispatch]);

  const handleManualAsk = useCallback(() => {
    send({ type: 'manual_ask' });
  }, [send]);

  useEffect(() => {
    const unsubToggle = onToggleListen(() => {
      if (isListeningRef.current) handleStopListening();
      else handleStartListening();
    });
    const unsubAsk = onManualAsk(() => handleManualAsk());
    return () => { unsubToggle(); unsubAsk(); };
  }, [handleStartListening, handleStopListening, handleManualAsk]);

  // 保存配置时，将 API Key 和配置一起发送给后端
  const handleConfigSave = useCallback(() => {
    send({
      type: 'config_update',
      system_prompt: state.config.systemPrompt,
      course_name: state.config.courseName,
      course_materials: state.config.courseMaterials,
      api_key: state.apiKey,
      api_base_url: state.apiBaseUrl,
      asr_language: state.config.asrLanguage,
      translate_enabled: state.config.translateEnabled,
      translate_target_lang: state.config.translateTargetLang,
    });
    dispatch({ type: 'SET_ACTIVE_TAB', payload: 'listen' });
  }, [send, state.config, state.apiKey, state.apiBaseUrl, dispatch]);

  const handleToggleAlwaysOnTop = useCallback(async () => {
    const newVal = !alwaysOnTop;
    setAlwaysOnTop(newVal);
    if (isElectron()) await window.electronAPI!.setAlwaysOnTop(newVal);
  }, [alwaysOnTop]);

  const isStreaming = state.listeningStatus === 'processing';

  // 等待后端启动的加载界面
  if (!backendReady && isElectron()) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#0f172a', gap: '16px' }}>
        <div style={{ width: '32px', height: '32px', border: '2px solid #0ea5e9', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
        <p style={{ color: '#94a3b8', fontSize: '14px' }}>正在启动本地服务...</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-slate-900 select-none">
      <StatusBar connectionStatus={wsStatus} sessionId={state.sessionId} courseName={state.config.courseName} />
      {isElectron() && (
        <ElectronToolbar
          alwaysOnTop={alwaysOnTop}
          onToggleAlwaysOnTop={handleToggleAlwaysOnTop}
          onMinimizeToTray={() => window.electronAPI?.minimizeToTray()}
        />
      )}
      <div className="flex flex-1 overflow-hidden">
        {/* 左侧面板 */}
        <div className="w-80 flex flex-col gap-4 p-4 border-r border-slate-800 overflow-hidden">
          <MicControl
            connectionStatus={wsStatus}
            listeningStatus={state.listeningStatus}
            volume={isCapturing ? volume : 0}
            onStartListening={handleStartListening}
            onStopListening={handleStopListening}
            onManualAsk={handleManualAsk}
          />
          {audioError && (
            <div className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
              {audioError}
            </div>
          )}
          <div className="card flex-1 flex flex-col overflow-hidden">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">实时字幕</span>
              <button
                className="text-xs text-slate-500 hover:text-slate-300"
                onClick={() => { send({ type: 'clear_history' }); dispatch({ type: 'CLEAR_HISTORY' }); }}
              >
                清空
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              <TranscriptPanel transcripts={state.transcripts} />
            </div>
          </div>
        </div>

        {/* 右侧主内容 */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex border-b border-slate-800 px-4">
            {([
              { id: 'listen', label: '💡 AI 答案' },
              { id: 'config', label: '⚙️ 课程配置' },
            ] as const).map(tab => (
              <button
                key={tab.id}
                className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                  state.activeTab === tab.id
                    ? 'border-sky-500 text-sky-400'
                    : 'border-transparent text-slate-400 hover:text-slate-300'
                }`}
                onClick={() => dispatch({ type: 'SET_ACTIVE_TAB', payload: tab.id })}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {state.activeTab === 'listen' && (
              <AnswerPanel
                currentQuestion={state.currentQuestion}
                currentStreamingAnswer={state.currentStreamingAnswer}
                answers={state.answers}
                isStreaming={isStreaming}
              />
            )}
            {state.activeTab === 'config' && (
              <ConfigPanel
                sessionId={state.sessionId}
                config={state.config}
                apiKey={state.apiKey}
                apiBaseUrl={state.apiBaseUrl}
                onConfigChange={(partial) => dispatch({ type: 'UPDATE_CONFIG', payload: partial })}
                onApiKeyChange={(key) => dispatch({ type: 'SET_API_KEY', payload: key })}
                onApiBaseUrlChange={(url) => dispatch({ type: 'SET_API_BASE_URL', payload: url })}
                onSave={handleConfigSave}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
