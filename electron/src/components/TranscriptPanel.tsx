/**
 * 实时字幕面板
 * 展示 ASR 识别出的文本，高亮显示检测到问题的条目
 *
 * 修复记录：
 *   - 支持临时字幕条目（isFinal=false）：显示为半透明斜体，带动画光标
 *   - 最终字幕正常显示
 *   - 翻译结果在字幕下方显示（异步更新）
 */
import React, { useEffect, useRef } from 'react';
import type { TranscriptEntry } from '../types';

interface TranscriptPanelProps {
  transcripts: TranscriptEntry[];
}

export const TranscriptPanel: React.FC<TranscriptPanelProps> = ({ transcripts }) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcripts.length, transcripts[transcripts.length - 1]?.text]);

  if (transcripts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-2">
        <svg className="w-8 h-8 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
        </svg>
        <p className="text-xs">识别内容将显示在这里</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5 overflow-y-auto h-full pr-1">
      {transcripts.map((entry) => {
        const isInterim = entry.isFinal === false;
        return (
          <div
            key={entry.id}
            className={`text-sm px-3 py-2 rounded-lg transition-all ${
              isInterim
                ? 'bg-slate-800/30 border border-slate-700/30 text-slate-400 italic'
                : entry.isQuestion
                ? 'bg-amber-900/40 border border-amber-600/50 text-amber-200'
                : 'bg-slate-800/60 text-slate-300'
            }`}
          >
            {entry.isQuestion && !isInterim && (
              <span className="text-xs text-amber-400 font-medium mr-1">❓</span>
            )}
            <div className="flex items-baseline gap-1">
              <span>{entry.text}</span>
              {isInterim && (
                <span className="inline-block w-0.5 h-3.5 bg-sky-400 animate-pulse ml-0.5 flex-shrink-0" />
              )}
            </div>
            {entry.translation && !isInterim && (
              <div className="text-xs mt-1 text-sky-300/90 border-l-2 border-sky-500/40 pl-2">
                {entry.translation}
              </div>
            )}
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
};
