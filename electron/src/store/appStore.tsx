/**
 * 全局应用状态管理
 * 使用 React Context + useReducer，无需额外依赖
 *
 * 修复记录：
 *   - 增加 UPSERT_TRANSCRIPT action，支持临时字幕（interim）覆盖更新
 *   - 临时字幕（isFinal=false）以 'interim' 为固定 id，避免重复条目堆积
 *   - 最终结果（isFinal=true）替换临时条目并生成唯一 id
 */
import React, { createContext, useContext, useReducer, type ReactNode } from 'react';
import type {
  ConnectionStatus,
  ListeningStatus,
  TranscriptEntry,
  AnswerEntry,
  SessionConfig,
} from '../types';

// ===== 状态定义 =====

interface AppState {
  sessionId: string;
  connectionStatus: ConnectionStatus;
  listeningStatus: ListeningStatus;
  volume: number;
  transcripts: TranscriptEntry[];
  answers: AnswerEntry[];
  currentStreamingAnswer: string;
  currentQuestion: string;
  config: SessionConfig;
  activeTab: 'listen' | 'config' | 'history';
  apiKey: string;
  apiBaseUrl: string;
}

const initialState: AppState = {
  sessionId: '',
  connectionStatus: 'disconnected',
  listeningStatus: 'idle',
  volume: 0,
  transcripts: [],
  answers: [],
  currentStreamingAnswer: '',
  currentQuestion: '',
  config: {
    systemPrompt: '',
    courseName: '',
    courseMaterials: '',
    asrLanguage: 'zh',
    translateEnabled: false,
    translateTargetLang: 'en',
  },
  activeTab: 'listen',
  apiKey: localStorage.getItem('ai_class_api_key') || '',
  apiBaseUrl: localStorage.getItem('ai_class_api_base_url') || 'https://api.minimax.chat/v1',
};

// ===== Action 定义 =====

type Action =
  | { type: 'SET_SESSION_ID'; payload: string }
  | { type: 'SET_CONNECTION_STATUS'; payload: ConnectionStatus }
  | { type: 'SET_LISTENING_STATUS'; payload: ListeningStatus }
  | { type: 'SET_VOLUME'; payload: number }
  | { type: 'ADD_TRANSCRIPT'; payload: TranscriptEntry }
  | { type: 'UPSERT_TRANSCRIPT'; payload: TranscriptEntry }
  | { type: 'UPDATE_TRANSCRIPT_TRANSLATION'; payload: { id: string; translation: string } }
  | { type: 'MARK_TRANSCRIPT_QUESTION'; payload: string }
  | { type: 'ADD_ANSWER'; payload: AnswerEntry }
  | { type: 'START_STREAMING'; payload: { question: string; answerId: string } }
  | { type: 'APPEND_STREAM_CHUNK'; payload: string }
  | { type: 'FINISH_STREAMING'; payload: { answerId: string; fullAnswer: string } }
  | { type: 'UPDATE_CONFIG'; payload: Partial<SessionConfig> }
  | { type: 'SET_ACTIVE_TAB'; payload: AppState['activeTab'] }
  | { type: 'CLEAR_HISTORY' }
  | { type: 'SET_API_KEY'; payload: string }
  | { type: 'SET_API_BASE_URL'; payload: string };

// ===== Reducer =====

function appReducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_SESSION_ID':
      return { ...state, sessionId: action.payload };
    case 'SET_CONNECTION_STATUS':
      return { ...state, connectionStatus: action.payload };
    case 'SET_LISTENING_STATUS':
      return { ...state, listeningStatus: action.payload };
    case 'SET_VOLUME':
      return { ...state, volume: action.payload };
    case 'ADD_TRANSCRIPT':
      return {
        ...state,
        // 移除临时条目（如果存在），再追加最终结果，保留最近 100 条
        transcripts: [
          ...state.transcripts.filter(t => t.id !== 'interim').slice(-99),
          action.payload,
        ],
      };
    case 'UPSERT_TRANSCRIPT': {
      const entry = action.payload;
      if (!entry.isFinal) {
        // 临时结果：替换或追加 interim 条目
        const hasInterim = state.transcripts.some(t => t.id === 'interim');
        if (hasInterim) {
          return {
            ...state,
            transcripts: state.transcripts.map(t =>
              t.id === 'interim' ? { ...entry, id: 'interim' } : t
            ),
          };
        }
        return {
          ...state,
          transcripts: [...state.transcripts.slice(-99), { ...entry, id: 'interim' }],
        };
      }
      // 最终结果：移除 interim，追加最终条目
      return {
        ...state,
        transcripts: [
          ...state.transcripts.filter(t => t.id !== 'interim').slice(-99),
          entry,
        ],
      };
    }
    case 'UPDATE_TRANSCRIPT_TRANSLATION': {
      const updated = state.transcripts.map(t =>
        t.id === action.payload.id ? { ...t, translation: action.payload.translation } : t
      );
      return { ...state, transcripts: updated };
    }
    case 'MARK_TRANSCRIPT_QUESTION': {
      const updated = state.transcripts.map(t =>
        t.id === action.payload ? { ...t, isQuestion: true } : t
      );
      return { ...state, transcripts: updated };
    }
    case 'START_STREAMING':
      return {
        ...state,
        currentStreamingAnswer: '',
        currentQuestion: action.payload.question,
        listeningStatus: 'processing',
      };
    case 'APPEND_STREAM_CHUNK':
      return {
        ...state,
        currentStreamingAnswer: state.currentStreamingAnswer + action.payload,
      };
    case 'FINISH_STREAMING': {
      const newAnswer: AnswerEntry = {
        id: action.payload.answerId,
        question: state.currentQuestion,
        answer: action.payload.fullAnswer,
        isStreaming: false,
        timestamp: Date.now(),
      };
      return {
        ...state,
        answers: [newAnswer, ...state.answers.slice(0, 19)],
        currentStreamingAnswer: '',
        currentQuestion: '',
        listeningStatus: 'listening',
      };
    }
    case 'UPDATE_CONFIG':
      return { ...state, config: { ...state.config, ...action.payload } };
    case 'SET_ACTIVE_TAB':
      return { ...state, activeTab: action.payload };
    case 'CLEAR_HISTORY':
      return { ...state, transcripts: [], answers: [], currentStreamingAnswer: '' };
    case 'SET_API_KEY':
      localStorage.setItem('ai_class_api_key', action.payload);
      return { ...state, apiKey: action.payload };
    case 'SET_API_BASE_URL':
      localStorage.setItem('ai_class_api_base_url', action.payload);
      return { ...state, apiBaseUrl: action.payload };
    default:
      return state;
  }
}

// ===== Context =====

const AppContext = createContext<{
  state: AppState;
  dispatch: React.Dispatch<Action>;
} | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState);
  return (
    <AppContext.Provider value={{ state, dispatch }}>
      {children}
    </AppContext.Provider>
  );
}

export function useAppStore() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppStore must be used within AppProvider');
  return ctx;
}
