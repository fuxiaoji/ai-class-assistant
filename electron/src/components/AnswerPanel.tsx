/**
 * 答案展示面板
 * 显示当前流式生成的答案和历史答案列表
 */
import React from 'react';
import type { AnswerEntry } from '../types';

interface AnswerPanelProps {
  currentQuestion: string;
  currentStreamingAnswer: string;
  answers: AnswerEntry[];
  isStreaming: boolean;
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export const AnswerPanel: React.FC<AnswerPanelProps> = ({
  currentQuestion,
  currentStreamingAnswer,
  answers,
  isStreaming,
}) => {
  return (
    <div className="flex flex-col gap-4 h-full">
      {/* 当前流式答案 */}
      {(isStreaming || currentStreamingAnswer) && (
        <div className="card border-sky-500/50 bg-sky-950/30 animate-fade-in">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-medium text-sky-400 uppercase tracking-wide">AI 正在回答</span>
            <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse" />
          </div>
          {currentQuestion && (
            <p className="text-sm text-slate-400 mb-2 italic">
              问题：{currentQuestion}
            </p>
          )}
          <div className="text-slate-100 leading-relaxed whitespace-pre-wrap">
            {currentStreamingAnswer}
            {isStreaming && <span className="typing-cursor" />}
          </div>
        </div>
      )}

      {/* 历史答案 */}
      {answers.length === 0 && !isStreaming ? (
        <div className="flex-1 flex flex-col items-center justify-center text-slate-500 gap-3">
          <svg className="w-12 h-12 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/>
          </svg>
          <p className="text-sm">开始监听后，AI 会在检测到问题时自动生成答案</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3 overflow-y-auto">
          {answers.map((answer) => (
            <div key={answer.id} className="card hover:border-slate-600 transition-colors">
              <div className="flex items-start justify-between gap-2 mb-2">
                <span className="text-xs text-slate-500">{formatTime(answer.timestamp)}</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700 text-slate-400">历史</span>
              </div>
              <p className="text-sm text-slate-400 mb-2 italic">
                问题：{answer.question}
              </p>
              <div className="text-slate-200 text-sm leading-relaxed whitespace-pre-wrap">
                {answer.answer}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
