/**
 * Electron 专属工具栏
 * 提供窗口置顶、最小化到托盘等桌面端专属功能
 */
import React from 'react';

interface ElectronToolbarProps {
  alwaysOnTop: boolean;
  onToggleAlwaysOnTop: () => void;
  onMinimizeToTray?: () => void;
}

export const ElectronToolbar: React.FC<ElectronToolbarProps> = ({
  alwaysOnTop,
  onToggleAlwaysOnTop,
  onMinimizeToTray,
}) => {
  return (
    <div className="flex items-center gap-2 px-4 py-1.5 bg-slate-800/50 border-b border-slate-700/50 text-xs">
      <span className="text-slate-500">桌面端</span>
      <span className="text-slate-700">·</span>

      {/* 窗口置顶 */}
      <button
        className={`flex items-center gap-1 px-2 py-0.5 rounded transition-colors ${
          alwaysOnTop
            ? 'bg-sky-600/30 text-sky-400 border border-sky-600/50'
            : 'text-slate-400 hover:text-slate-300 hover:bg-slate-700/50'
        }`}
        onClick={onToggleAlwaysOnTop}
        title="窗口置顶（上课时保持在最前面）"
      >
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M5 11l7-7 7 7M5 19l7-7 7 7" />
        </svg>
        {alwaysOnTop ? '已置顶' : '置顶'}
      </button>

      {/* 最小化到托盘 */}
      {onMinimizeToTray && (
        <button
          className="flex items-center gap-1 px-2 py-0.5 rounded text-slate-400 hover:text-slate-300 hover:bg-slate-700/50 transition-colors"
          onClick={onMinimizeToTray}
          title="最小化到系统托盘"
        >
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
          托盘
        </button>
      )}

      <div className="flex-1" />

      {/* 快捷键提示 */}
      <div className="flex items-center gap-3 text-slate-600">
        <span>⌘⇧L 切换监听</span>
        <span>⌘⇧H 手动求助</span>
        <span>⌘⇧W 显示/隐藏</span>
      </div>
    </div>
  );
};
