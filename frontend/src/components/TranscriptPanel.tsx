/**
 * 字幕面板 — 双区域设计
 *
 * 上方：实时字幕区（只显示最新一条，大字体，快速响应）
 *   - 限制最大高度，防止长文本遮挡完整记录区
 *   - 始终显示翻译（无论 isFinal 状态）
 * 下方：完整文本区（所有识别结果拼接，可滚动回顾）
 */
import React, { useEffect, useRef } from 'react';
import type { TranscriptEntry } from '../types';

interface TranscriptPanelProps {
  transcripts: TranscriptEntry[];
}

export const TranscriptPanel: React.FC<TranscriptPanelProps> = ({ transcripts }) => {
  const fullTextRef = useRef<HTMLDivElement>(null);
  const liveTextRef = useRef<HTMLDivElement>(null);

  // 最新一条字幕（用于实时显示）
  const latest = transcripts[transcripts.length - 1] ?? null;

  // 完整文本记录（所有最终字幕）
  const finalTranscripts = transcripts.filter(t => t.isFinal !== false);

  // 完整文本区自动滚动到底部
  useEffect(() => {
    if (fullTextRef.current) {
      fullTextRef.current.scrollTop = fullTextRef.current.scrollHeight;
    }
  }, [finalTranscripts.length]);

  // 实时字幕区：内容更新时滚动到底部（防止长文本被截断）
  useEffect(() => {
    if (liveTextRef.current) {
      liveTextRef.current.scrollTop = liveTextRef.current.scrollHeight;
    }
  }, [latest?.text, latest?.translation]);

  return (
    <div className="flex flex-col h-full gap-3">
      {/* ── 实时字幕区（限制最大高度，防止遮挡完整记录） ── */}
      <div className="flex flex-col gap-1 flex-shrink-0">
        <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
          实时字幕
        </span>
        {/* max-h-[120px] 限制高度，overflow-y-auto 允许内部滚动 */}
        <div
          ref={liveTextRef}
          className="max-h-[120px] min-h-[52px] overflow-y-auto bg-slate-800/60 rounded-lg px-3 py-2.5 border border-slate-700/40"
        >
          {latest ? (
            <div className="w-full">
              <p
                className={`text-sm leading-relaxed break-words ${
                  latest.isFinal === false
                    ? 'text-slate-400 italic'
                    : latest.isQuestion
                    ? 'text-amber-200'
                    : 'text-slate-100'
                }`}
              >
                {latest.isQuestion && latest.isFinal !== false && (
                  <span className="text-amber-400 mr-1">❓</span>
                )}
                {latest.text}
                {latest.isFinal === false && (
                  <span className="inline-block w-1.5 h-3.5 bg-sky-400 ml-0.5 animate-pulse rounded-sm align-middle" />
                )}
              </p>
              {/* 修复：只要有翻译就显示，不再因 isFinal 状态而隐藏 */}
              {latest.translation && (
                <p className="text-xs text-sky-400 mt-1 leading-relaxed border-l-2 border-sky-500/40 pl-2">
                  {latest.translation}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-slate-600 italic">等待识别...</p>
          )}
        </div>
      </div>

      {/* ── 完整文本区（流式拼接，可回顾） ── */}
      <div className="flex flex-col gap-1 flex-1 min-h-0">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
            完整记录
          </span>
          <span className="text-xs text-slate-600">
            {finalTranscripts.length} 条
          </span>
        </div>
        <div
          ref={fullTextRef}
          className="flex-1 overflow-y-auto bg-slate-800/40 rounded-lg px-3 py-2 min-h-0 border border-slate-700/30"
        >
          {finalTranscripts.length === 0 ? (
            <p className="text-xs text-slate-600 italic">暂无记录</p>
          ) : (
            <div className="space-y-1.5">
              {finalTranscripts.map(t => (
                <div key={t.id} className="group">
                  <p
                    className={`text-xs leading-relaxed break-words ${
                      t.isQuestion ? 'text-amber-300' : 'text-slate-300'
                    }`}
                  >
                    {t.isQuestion && (
                      <span className="text-amber-400 mr-1">❓</span>
                    )}
                    {t.text}
                  </p>
                  {t.translation && (
                    <p className="text-xs text-sky-500 mt-0.5 leading-relaxed border-l-2 border-sky-600/40 pl-1.5">
                      {t.translation}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
