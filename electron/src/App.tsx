/**
 * AI 实时听课助手 - Electron 桌面端主应用组件
 *
 * 修复记录：
 *   - transcript 消息增加 is_final 字段处理：
 *     - is_final=false：使用 UPSERT_TRANSCRIPT 更新临时字幕条目
 *     - is_final=true（或未指定）：使用 ADD_TRANSCRIPT 追加最终字幕
 *   - 翻译结果通过 UPDATE_TRANSCRIPT_TRANSLATION 异步更新对应字幕条目
 *   - 音频块通过 WebSocket 发送给后端，后端用 faster-whisper 识别后推送字幕
 *   - 修复 answer_done 逻辑，防止 AI 回答中途消失
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
          const payload: Record<string, unknown> = {
            type: 'config_update',
            system_prompt: s.config.systemPrompt,
            course_name: s.config.courseName,
            course_materials: s.config.courseMaterials,
            asr_language: s.config.asrLanguage,
            translate_enabled: s.config.translateEnabled,
            translate_target_lang: s.config.translateTargetLang,
          };
          if (s.apiKey) {
            payload.api_key = s.apiKey;
            payload.api_base_url = s.apiBaseUrl;
          }
          sendRef.current(payload);
        }, 300);
        break;

      case 'transcript': {
        const id = (msg.id as string) || `t-${Date.now()}-${Math.random()}`;
        const text = msg.text as string;
        const isFinal = msg.is_final !== false; // 默认为 true

        if (isFinal) {
          dispatch({
            type: 'ADD_TRANSCRIPT',
            payload: {
              id,
              text,
              translation: msg.translation as string | undefined,
              isQuestion: false,
              timestamp: Date.now(),
              isFinal: true,
            }
          });
        } else {
          dispatch({
            type: 'UPSERT_TRANSCRIPT',
            payload: {
              id,
              text,
              isQuestion: false,
              timestamp: Date.now(),
              isFinal: false,
            }
          });
        }
        break;
      }

      case 'transcript_translation': {
        const id = msg.id as string;
        const translation = msg.translation as string;
        if (id && translation) {
          dispatch({ type: 'UPDATE_TRANSCRIPT_TRANSLATION', payload: { id, translation } });
        }
        break;
      }

      case 'question_detected': {
        const transcripts = stateRef.current.transcripts;
        const last = transcripts[transcripts.length - 1];
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
        // 修复：如果后端没传 full_answer，则使用当前已累积的 streamingAnswer
        const finalAnswer = (msg.full_answer as string) || stateRef.current.currentStreamingAnswer;
        dispatch({ 
          type: 'FINISH_STREAMING', 
          payload: { 
            answerId: pendingAnswerId.current || `a-${Date.now()}`, 
            fullAnswer: finalAnswer 
          } 
        });
        break;

      case 'error':
        console.error('[WS] 服务端错误:', msg.message);
        dispatch({ type: 'SET_LISTENING_STATUS', payload: isListeningRef.current ? 'listening' : 'idle' });
        break;

      case 'config_updated':
        console.log('[WS] 配置已更新');
        break;

      case 'listening_started':
        console.log('[WS] 后端确认开始监听');
        break;

      case 'listening_stopped':
        console.log('[WS] 后端确认停止监听');
        break;

      case 'pong':
        break;

      default:
        console.log('[WS] 未知消息类型:', msg.type, msg);
    }
  }, [dispatch]);

  const { connect, send, status: wsStatus } = useWebSocket({
    onMessage: handleWsMessage,
    onStatusChange: (s) => dispatch({ type: 'SET_CONNECTION_STATUS', payload: s }),
  });

  useEffect(() => { sendRef.current = send as unknown as (msg: Record<string, unknown>) => void; }, [send]);

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

  const handleAudioChunk = useCallback((base64Data: string, chunkIndex: number) => {
    if (wsStatus !== 'connected') return;
    send({
      type: 'audio_chunk',
      data: base64Data,
      chunk_index: chunkIndex,
      session_id: state.sessionId,
    });
  }, [send, state.sessionId, wsStatus]);

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

  const handleManualAsk = useCallback((question: string) => {
    if (!question.trim()) return;
    send({ type: 'manual_ask', question });
    dispatch({ type: 'SET_ACTIVE_TAB', payload: 'listen' });
  }, [send, dispatch]);

  useEffect(() => {
    const unsubToggle = onToggleListen(() => {
      if (isListeningRef.current) handleStopListening();
      else handleStartListening();
    });
    const unsubAsk = onManualAsk(() => {
      // 触发手动提问逻辑
    });
    return () => { unsubToggle(); unsubAsk(); };
  }, [handleStartListening, handleStopListening, handleManualAsk]);

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
