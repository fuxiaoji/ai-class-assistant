/**
 * 顶部状态栏组件
 * 显示连接状态、会话 ID 和课程名称
 */
import React from 'react';
import type { ConnectionStatus } from '../types';

interface StatusBarProps {
  connectionStatus: ConnectionStatus;
  sessionId: string;
  courseName: string;
}

const statusConfig: Record<ConnectionStatus, { label: string; color: string; dot: string }> = {
  disconnected: { label: '未连接', color: 'text-slate-400', dot: 'bg-slate-500' },
  connecting:   { label: '连接中...', color: 'text-yellow-400', dot: 'bg-yellow-400 animate-pulse' },
  connected:    { label: '已连接', color: 'text-emerald-400', dot: 'bg-emerald-400' },
  error:        { label: '连接错误', color: 'text-red-400', dot: 'bg-red-400 animate-pulse' },
};

export const StatusBar: React.FC<StatusBarProps> = ({ connectionStatus, sessionId, courseName }) => {
  const cfg = statusConfig[connectionStatus];
  return (
    <header className="flex items-center justify-between px-6 py-3 bg-slate-900 border-b border-slate-800">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${cfg.dot}`} />
          <span className={`text-sm font-medium ${cfg.color}`}>{cfg.label}</span>
        </div>
        {sessionId && (
          <span className="text-xs text-slate-500 font-mono">#{sessionId}</span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <span className="text-lg font-semibold text-sky-400">🎓 AI 听课助手</span>
      </div>

      <div className="text-sm text-slate-400 max-w-[200px] truncate">
        {courseName || '未设置课程'}
      </div>
    </header>
  );
};
