/**
 * 麦克风控制面板
 * 包含开始/停止按钮、音量可视化和手动提问按钮
 */
import React, { useMemo } from 'react';
import type { ConnectionStatus, ListeningStatus } from '../types';

interface MicControlProps {
  connectionStatus: ConnectionStatus;
  listeningStatus: ListeningStatus;
  volume: number;
  onStartListening: () => void;
  onStopListening: () => void;
  onManualAsk: () => void;
}

export const MicControl: React.FC<MicControlProps> = ({
  connectionStatus,
  listeningStatus,
  volume,
  onStartListening,
  onStopListening,
  onManualAsk,
}) => {
  const isConnected = connectionStatus === 'connected';
  const isListening = listeningStatus === 'listening';
  const isProcessing = listeningStatus === 'processing';

  // 音量条数量
  const bars = 20;
  const activeBarCount = useMemo(() => Math.round(volume * bars * 5), [volume]);

  return (
    <div className="card flex flex-col items-center gap-4">
      {/* 音量可视化 */}
      <div className="flex items-end gap-0.5 h-12 w-full max-w-xs">
        {Array.from({ length: bars }).map((_, i) => {
          const isActive = i < activeBarCount;
          const height = 20 + (i / bars) * 80;
          return (
            <div
              key={i}
              className={`flex-1 rounded-sm transition-all duration-75 ${
                isActive
                  ? i < bars * 0.6 ? 'bg-emerald-400' : i < bars * 0.85 ? 'bg-yellow-400' : 'bg-red-400'
                  : 'bg-slate-700'
              }`}
              style={{ height: `${isActive ? height : 20}%` }}
            />
          );
        })}
      </div>

      {/* 状态文字 */}
      <div className="text-sm text-slate-400 h-5">
        {!isConnected && '请先连接到服务器'}
        {isConnected && listeningStatus === 'idle' && '点击开始监听课堂'}
        {isListening && (
          <span className="text-emerald-400 flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse inline-block" />
            正在监听中...
          </span>
        )}
        {isProcessing && (
          <span className="text-sky-400 flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-sky-400 animate-pulse inline-block" />
            AI 正在思考...
          </span>
        )}
      </div>

      {/* 控制按钮 */}
      <div className="flex gap-3">
        {!isListening ? (
          <button
            className="btn-primary text-base px-6 py-3"
            disabled={!isConnected}
            onClick={onStartListening}
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 1a4 4 0 0 1 4 4v7a4 4 0 0 1-8 0V5a4 4 0 0 1 4-4zm0 2a2 2 0 0 0-2 2v7a2 2 0 0 0 4 0V5a2 2 0 0 0-2-2zm-7 9a7 7 0 0 0 14 0h2a9 9 0 0 1-8 8.94V23h-2v-2.06A9 9 0 0 1 3 12H5z"/>
            </svg>
            开始监听
          </button>
        ) : (
          <button
            className="btn-danger text-base px-6 py-3"
            onClick={onStopListening}
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <rect x="6" y="6" width="12" height="12" rx="1"/>
            </svg>
            停止监听
          </button>
        )}

        <button
          className="btn-secondary text-base px-4 py-3"
          disabled={!isConnected}
          onClick={onManualAsk}
          title="手动触发：让 AI 根据最近的内容生成答案"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
          </svg>
          求助
        </button>
      </div>
    </div>
  );
};
