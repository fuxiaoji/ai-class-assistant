/**
 * AI 实时听课助手 - 主应用组件
 */
import { useEffect, useCallback, useRef } from 'react';
import { useAppStore } from './store/appStore';
import { useWebSocket } from './hooks/useWebSocket';
import { useAudioCapture } from './hooks/useAudioCapture';
import { api } from './services/api';
import { StatusBar } from './components/StatusBar';
import { MicControl } from './components/MicControl';
import { AnswerPanel } from './components/AnswerPanel';
import { TranscriptPanel } from './components/TranscriptPanel';
import { ConfigPanel } from './components/ConfigPanel';
import type { WSMessage } from './types';

let answerIdCounter = 0;

function AppContent() {
  const { state, dispatch } = useAppStore();
  const pendingAnswerId = useRef<string>('');

  const handleWsMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
      case 'connected':
        dispatch({ type: 'SET_CONNECTION_STATUS', payload: 'connected' });
        break;
      case 'transcript': {
        const id = `t-${Date.now()}-${Math.random()}`;
        dispatch({ type: 'ADD_TRANSCRIPT', payload: { id, text: msg.text as string, isQuestion: false, timestamp: Date.now() } });
        break;
      }
      case 'question_detected': {
        const lastTranscript = state.transcripts[state.transcripts.length - 1];
        if (lastTranscript) dispatch({ type: 'MARK_TRANSCRIPT_QUESTION', payload: lastTranscript.id });
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
        break;
    }
  }, [dispatch, state.transcripts]);

  const { connect, send, status: wsStatus } = useWebSocket({
    onMessage: handleWsMessage,
    onStatusChange: (s) => dispatch({ type: 'SET_CONNECTION_STATUS', payload: s }),
  });

  useEffect(() => {
    const init = async () => {
      try {
        const { session_id } = await api.createSession();
        dispatch({ type: 'SET_SESSION_ID', payload: session_id });
        connect(session_id);
      } catch (e) {
        console.error('初始化失败:', e);
        dispatch({ type: 'SET_CONNECTION_STATUS', payload: 'error' });
      }
    };
    init();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleAudioChunk = useCallback((base64Data: string) => {
    send({ 
      type: 'audio_chunk', 
      data: base64Data, 
      session_id: state.sessionId,
      api_key: state.apiKey,
      api_base_url: state.apiBaseUrl,
    });
  }, [send, state.sessionId, state.apiKey, state.apiBaseUrl]);

  const { start: startAudio, stop: stopAudio, isCapturing, volume, error: audioError } = useAudioCapture({
    chunkDurationMs: 3000,
    onAudioChunk: handleAudioChunk,
    onVolumeChange: (v) => dispatch({ type: 'SET_VOLUME', payload: v }),
  });

  const handleStartListening = useCallback(async () => {
    await startAudio();
    send({ type: 'start_listening' });
    dispatch({ type: 'SET_LISTENING_STATUS', payload: 'listening' });
  }, [startAudio, send, dispatch]);

  const handleStopListening = useCallback(() => {
    stopAudio();
    send({ type: 'stop_listening' });
    dispatch({ type: 'SET_LISTENING_STATUS', payload: 'idle' });
  }, [stopAudio, send, dispatch]);

  const handleManualAsk = useCallback(() => {
    send({ type: 'manual_ask' });
  }, [send]);

  const handleConfigSave = useCallback(() => {
    send({ 
      type: 'config_update', 
      system_prompt: state.config.systemPrompt, 
      course_name: state.config.courseName, 
      course_materials: state.config.courseMaterials,
      api_key: state.apiKey,
      api_base_url: state.apiBaseUrl,
    });
    dispatch({ type: 'SET_ACTIVE_TAB', payload: 'listen' });
  }, [send, state.config, state.apiKey, state.apiBaseUrl, dispatch]);

  const isStreaming = state.listeningStatus === 'processing';

  return (
    <div className="flex flex-col h-screen bg-slate-900">
      <StatusBar connectionStatus={wsStatus} sessionId={state.sessionId} courseName={state.config.courseName} />
      <div className="flex flex-1 overflow-hidden">
        {/* 左侧 */}
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
            <div className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">⚠ {audioError}</div>
          )}
          <div className="card flex-1 flex flex-col overflow-hidden">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">实时字幕</span>
              <button className="text-xs text-slate-500 hover:text-slate-300" onClick={() => { send({ type: 'clear_history' }); dispatch({ type: 'CLEAR_HISTORY' }); }}>清空</button>
            </div>
            <div className="flex-1 overflow-hidden">
              <TranscriptPanel transcripts={state.transcripts} />
            </div>
          </div>
        </div>
        {/* 右侧 */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex border-b border-slate-800 px-4">
            {([{ id: 'listen', label: '💡 AI 答案' }, { id: 'config', label: '⚙️ 课程配置' }] as const).map(tab => (
              <button key={tab.id} className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${state.activeTab === tab.id ? 'border-sky-500 text-sky-400' : 'border-transparent text-slate-400 hover:text-slate-300'}`} onClick={() => dispatch({ type: 'SET_ACTIVE_TAB', payload: tab.id })}>{tab.label}</button>
            ))}
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {state.activeTab === 'listen' && (
              <AnswerPanel currentQuestion={state.currentQuestion} currentStreamingAnswer={state.currentStreamingAnswer} answers={state.answers} isStreaming={isStreaming} />
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

export default function App() {
  return <AppContent />;
}
