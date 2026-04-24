/**
 * Electron Preload Script
 * 在渲染进程中安全暴露主进程 API（contextBridge）
 */
import { contextBridge, ipcRenderer } from 'electron';

// 暴露给渲染进程的 API
contextBridge.exposeInMainWorld('electronAPI', {
  // ── 系统信息 ──────────────────────────────────────────
  getBackendPort: (): Promise<number> =>
    ipcRenderer.invoke('get-backend-port'),

  getAppVersion: (): Promise<string> =>
    ipcRenderer.invoke('get-app-version'),

  checkBackend: (): Promise<boolean> =>
    ipcRenderer.invoke('check-backend'),

  // ── 文件操作 ──────────────────────────────────────────
  openFileDialog: (): Promise<Electron.OpenDialogReturnValue> =>
    ipcRenderer.invoke('open-file-dialog'),

  readFile: (filePath: string): Promise<{ success: boolean; data?: string; name?: string; error?: string }> =>
    ipcRenderer.invoke('read-file', filePath),

  // ── 窗口控制 ──────────────────────────────────────────
  setAlwaysOnTop: (flag: boolean): Promise<void> =>
    ipcRenderer.invoke('set-always-on-top', flag),

  minimizeToTray: (): Promise<void> =>
    ipcRenderer.invoke('minimize-to-tray'),

  // ── 快捷键事件监听 ────────────────────────────────────
  onToggleListen: (callback: () => void) => {
    ipcRenderer.on('shortcut:toggle-listen', callback);
    return () => ipcRenderer.removeListener('shortcut:toggle-listen', callback);
  },

  onManualAsk: (callback: () => void) => {
    ipcRenderer.on('shortcut:manual-ask', callback);
    return () => ipcRenderer.removeListener('shortcut:manual-ask', callback);
  },

  // ── 平台信息 ──────────────────────────────────────────
  platform: process.platform,
  isElectron: true,
});
