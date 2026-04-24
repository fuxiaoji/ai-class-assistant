/**
 * Electron 环境工具
 * 提供统一的 Electron API 访问接口，在 Web 环境中优雅降级
 */

// 声明 window.electronAPI 类型
declare global {
  interface Window {
    electronAPI?: {
      getBackendPort: () => Promise<number>;
      getAppVersion: () => Promise<string>;
      checkBackend: () => Promise<boolean>;
      openFileDialog: () => Promise<{ canceled: boolean; filePaths: string[] }>;
      readFile: (filePath: string) => Promise<{ success: boolean; data?: string; name?: string; error?: string }>;
      setAlwaysOnTop: (flag: boolean) => Promise<void>;
      minimizeToTray: () => Promise<void>;
      onToggleListen: (callback: () => void) => () => void;
      onManualAsk: (callback: () => void) => () => void;
      platform: string;
      isElectron: boolean;
    };
  }
}

/** 是否在 Electron 环境中运行 */
export const isElectron = (): boolean => {
  return typeof window !== 'undefined' && !!window.electronAPI?.isElectron;
};

/** 获取后端端口（Electron 中使用本地端口，Web 中使用默认端口） */
export const getBackendPort = async (): Promise<number> => {
  if (isElectron()) {
    return window.electronAPI!.getBackendPort();
  }
  return 8000; // Web 默认端口
};

/** 获取后端 Base URL */
export const getBackendBaseUrl = async (): Promise<string> => {
  const port = await getBackendPort();
  return `http://127.0.0.1:${port}`;
};

/** 获取 WebSocket Base URL */
export const getWsBaseUrl = async (): Promise<string> => {
  const port = await getBackendPort();
  return `ws://127.0.0.1:${port}`;
};

/** 打开文件选择对话框（Electron 原生，Web 降级为 input[type=file]） */
export const openFileDialog = async (): Promise<string | null> => {
  if (isElectron()) {
    const result = await window.electronAPI!.openFileDialog();
    if (!result.canceled && result.filePaths.length > 0) {
      return result.filePaths[0];
    }
    return null;
  }
  return null;
};

/** 读取本地文件（仅 Electron 可用） */
export const readLocalFile = async (filePath: string) => {
  if (isElectron()) {
    return window.electronAPI!.readFile(filePath);
  }
  return { success: false, error: '仅桌面端支持直接读取文件' };
};

/** 设置窗口置顶 */
export const setAlwaysOnTop = async (flag: boolean): Promise<void> => {
  if (isElectron()) {
    return window.electronAPI!.setAlwaysOnTop(flag);
  }
};

/** 最小化到托盘 */
export const minimizeToTray = async (): Promise<void> => {
  if (isElectron()) {
    return window.electronAPI!.minimizeToTray();
  }
};

/** 注册快捷键监听（仅 Electron） */
export const onToggleListen = (callback: () => void): (() => void) => {
  if (isElectron()) {
    return window.electronAPI!.onToggleListen(callback);
  }
  return () => {};
};

export const onManualAsk = (callback: () => void): (() => void) => {
  if (isElectron()) {
    return window.electronAPI!.onManualAsk(callback);
  }
  return () => {};
};
