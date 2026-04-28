// ===== WebSocket 消息类型 =====

export type WSMessageType =
  | 'connected'
  | 'listening_started'
  | 'listening_stopped'
  | 'config_updated'
  | 'transcript'
  | 'transcript_translation'
  | 'question_detected'
  | 'answer_start'
  | 'answer_chunk'
  | 'answer_done'
  | 'history_cleared'
  | 'error'
  | 'pong';

export interface WSMessage {
  type: WSMessageType;
  [key: string]: unknown;
}

export interface TranscriptMessage extends WSMessage {
  type: 'transcript';
  id: string;
  text: string;
  is_final?: boolean;
  buffer_length: number;
}

export interface QuestionDetectedMessage extends WSMessage {
  type: 'question_detected';
  text: string;
}

export interface AnswerChunkMessage extends WSMessage {
  type: 'answer_chunk';
  chunk: string;
}

export interface AnswerDoneMessage extends WSMessage {
  type: 'answer_done';
  full_answer: string;
}

export interface AnswerStartMessage extends WSMessage {
  type: 'answer_start';
  question: string;
}

// ===== 应用状态类型 =====

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export type ListeningStatus = 'idle' | 'listening' | 'processing';

export interface TranscriptEntry {
  id: string;
  text: string;
  translation?: string;
  isQuestion: boolean;
  timestamp: number;
  /** 是否为临时中间结果（Web Speech API interim result） */
  isFinal?: boolean;
}

export interface AnswerEntry {
  id: string;
  question: string;
  answer: string;
  isStreaming: boolean;
  timestamp: number;
}

// ===== 配置类型 =====

export interface SessionConfig {
  systemPrompt: string;
  courseName: string;
  courseMaterials: string;
  asrLanguage: string;
  translateEnabled: boolean;
  translateTargetLang: string;
}

// ===== API 响应类型 =====

export interface UploadResponse {
  filename: string;
  extracted_text_length: number;
  preview: string;
}
