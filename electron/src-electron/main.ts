/**
 * Electron 主进程
 * 负责：窗口管理、系统托盘、全局快捷键、后端进程管理、IPC 通信
 */
import {
  app,
  BrowserWindow,
  Tray,
  Menu,
  globalShortcut,
  ipcMain,
  shell,
  nativeImage,
  dialog,
  Notification,
  systemPreferences,
} from 'electron';
import * as path from 'path';
import * as fs from 'fs';
import { spawn, ChildProcess } from 'child_process';

// ── 常量 ──────────────────────────────────────────────────
const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
const VITE_DEV_URL = 'http://localhost:5174';
const BACKEND_PORT = 18765; // 本地端使用不同端口，避免与网站端冲突

// ── 全局变量 ──────────────────────────────────────────────
let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let backendProcess: ChildProcess | null = null;
let isQuitting = false;

// ── 后端进程管理 ──────────────────────────────────────────

function getBackendPath(): string {
  if (isDev) {
    return path.join(__dirname, '../../backend');
  }
  // 打包后，后端在 resources/backend-bin 目录
  return path.join(process.resourcesPath, 'backend-bin');
}

function getPackagedBackendExecPath(): string | null {
  const candidates = [
    path.join(process.resourcesPath, 'backend-bin', 'ai-class-backend'),
    path.join(process.resourcesPath, 'bin', 'ai-class-backend'),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}

function startBackend(): Promise<void> {
  return new Promise((resolve, reject) => {
    const commonEnv = {
      ...process.env,
      BACKEND_PORT: String(BACKEND_PORT),
      APP_PORT: String(BACKEND_PORT),
      CORS_ORIGINS: '*',
    };

    if (isDev) {
      const backendDir = getBackendPath();
      const mainPy = path.join(backendDir, 'main.py');
      if (!fs.existsSync(mainPy)) {
        console.warn('后端文件不存在，跳过后端启动:', mainPy);
        resolve();
        return;
      }
      const pythonCmd = 'python3';
      console.log(`启动后端(Dev): ${pythonCmd} -m uvicorn main:app --port ${BACKEND_PORT}`);
      backendProcess = spawn(
        pythonCmd,
        ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)],
        {
          cwd: backendDir,
          env: commonEnv,
          stdio: ['ignore', 'pipe', 'pipe'],
        }
      );
    } else {
      const backendExec = getPackagedBackendExecPath();
      if (!backendExec) {
        console.warn('后端可执行文件不存在，跳过后端启动:', process.resourcesPath);
        resolve();
        return;
      }
      try {
        fs.chmodSync(backendExec, 0o755);
      } catch {
      }
      console.log(`启动后端(Pkg): ${backendExec}`);
      backendProcess = spawn(
        backendExec,
        [],
        {
          cwd: path.dirname(backendExec),
          env: commonEnv,
          stdio: ['ignore', 'pipe', 'pipe'],
        }
      );
    }

    let started = false;

    backendProcess.stdout?.on('data', (data: Buffer) => {
      const msg = data.toString();
      console.log('[Backend]', msg.trim());
      if (!started && (msg.includes('Application startup complete') || msg.includes('Uvicorn running'))) {
        started = true;
        resolve();
      }
    });

    backendProcess.stderr?.on('data', (data: Buffer) => {
      const msg = data.toString();
      console.error('[Backend ERR]', msg.trim());
      if (!started && msg.includes('Application startup complete')) {
        started = true;
        resolve();
      }
    });

    backendProcess.on('error', (err) => {
      console.error('后端进程启动失败:', err);
      if (!started) reject(err);
    });

    backendProcess.on('exit', (code) => {
      console.log('后端进程退出，code:', code);
      backendProcess = null;
    });

    // 5 秒超时后强制 resolve（前端会自动重连）
    setTimeout(() => {
      if (!started) {
        console.warn('后端启动超时，继续加载前端...');
        started = true;
        resolve();
      }
    }, 5000);
  });
}

function stopBackend() {
  if (backendProcess) {
    console.log('停止后端进程...');
    backendProcess.kill('SIGTERM');
    backendProcess = null;
  }
}

// ── 窗口管理 ──────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 750,
    minWidth: 800,
    minHeight: 600,
    title: 'AI 听课助手',
    backgroundColor: '#0f172a',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    trafficLightPosition: { x: 16, y: 16 },
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
    show: false,
  });

  // 加载页面
  if (isDev) {
    mainWindow.loadURL(VITE_DEV_URL);
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  // 窗口准备好后显示（避免白屏闪烁）
  mainWindow.once('ready-to-show', () => {
    mainWindow?.show();
    mainWindow?.focus();
  });

  // 关闭时最小化到托盘，而不是退出
  mainWindow.on('close', (e) => {
    if (!isQuitting && process.platform === 'darwin') {
      e.preventDefault();
      mainWindow?.hide();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // 在系统浏览器中打开外部链接
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

// ── 系统托盘 ──────────────────────────────────────────────

function createTray() {
  // 使用内置图标（实际项目可替换为自定义图标）
  const iconPath = path.join(__dirname, '../public/tray-icon.png');
  let trayIcon: Electron.NativeImage;

  if (fs.existsSync(iconPath)) {
    trayIcon = nativeImage.createFromPath(iconPath).resize({ width: 16, height: 16 });
  } else {
    // 创建一个简单的默认图标
    trayIcon = nativeImage.createEmpty();
  }

  tray = new Tray(trayIcon);
  tray.setToolTip('AI 听课助手');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '显示窗口',
      click: () => {
        mainWindow?.show();
        mainWindow?.focus();
      },
    },
    {
      label: '开始监听 (Ctrl+Shift+L)',
      click: () => {
        mainWindow?.show();
        mainWindow?.webContents.send('shortcut:toggle-listen');
      },
    },
    {
      label: '手动求助 (Ctrl+Shift+H)',
      click: () => {
        mainWindow?.webContents.send('shortcut:manual-ask');
      },
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);

  tray.on('click', () => {
    if (mainWindow?.isVisible()) {
      mainWindow.hide();
    } else {
      mainWindow?.show();
      mainWindow?.focus();
    }
  });
}

// ── 全局快捷键 ────────────────────────────────────────────

function registerShortcuts() {
  // Ctrl+Shift+L (Cmd+Shift+L on Mac)：切换监听
  globalShortcut.register('CommandOrControl+Shift+L', () => {
    mainWindow?.show();
    mainWindow?.focus();
    mainWindow?.webContents.send('shortcut:toggle-listen');
  });

  // Ctrl+Shift+H (Cmd+Shift+H on Mac)：手动求助
  globalShortcut.register('CommandOrControl+Shift+H', () => {
    mainWindow?.webContents.send('shortcut:manual-ask');
    // 显示通知
    if (Notification.isSupported()) {
      new Notification({
        title: 'AI 听课助手',
        body: '已触发手动求助，正在生成答案...',
        silent: true,
      }).show();
    }
  });

  // Ctrl+Shift+W：显示/隐藏窗口
  globalShortcut.register('CommandOrControl+Shift+W', () => {
    if (mainWindow?.isVisible()) {
      mainWindow.hide();
    } else {
      mainWindow?.show();
      mainWindow?.focus();
    }
  });
}

// ── IPC 通信 ──────────────────────────────────────────────

function setupIPC() {
  // 获取后端端口
  ipcMain.handle('get-backend-port', () => BACKEND_PORT);

  // 获取应用版本
  ipcMain.handle('get-app-version', () => app.getVersion());

  // 打开文件选择对话框
  ipcMain.handle('open-file-dialog', async () => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ['openFile'],
      filters: [
        { name: '课件文件', extensions: ['pdf', 'txt', 'md', 'docx'] },
        { name: '所有文件', extensions: ['*'] },
      ],
    });
    return result;
  });

  // 读取本地文件内容
  ipcMain.handle('read-file', async (_event, filePath: string) => {
    try {
      const content = fs.readFileSync(filePath);
      return { success: true, data: content.toString('base64'), name: path.basename(filePath) };
    } catch (err) {
      return { success: false, error: String(err) };
    }
  });

  // 后端健康检查
  ipcMain.handle('check-backend', async () => {
    try {
      const http = await import('http');
      return new Promise<boolean>((resolve) => {
        const req = http.default.get(`http://127.0.0.1:${BACKEND_PORT}/api/health`, (res) => {
          resolve(res.statusCode === 200);
        });
        req.on('error', () => resolve(false));
        req.setTimeout(2000, () => { req.destroy(); resolve(false); });
      });
    } catch {
      return false;
    }
  });

  // 设置窗口置顶
  ipcMain.handle('set-always-on-top', (_event, flag: boolean) => {
    mainWindow?.setAlwaysOnTop(flag, 'floating');
  });

  // 最小化到托盘
  ipcMain.handle('minimize-to-tray', () => {
    mainWindow?.hide();
  });
}

// ── 应用生命周期 ──────────────────────────────────────────

app.whenReady().then(async () => {
  setupIPC();

  if (process.platform === 'darwin') {
    try {
      const micStatus = systemPreferences.getMediaAccessStatus('microphone');
      if (micStatus !== 'granted') {
        await systemPreferences.askForMediaAccess('microphone');
      }
    } catch (err) {
      console.warn('麦克风权限预请求失败:', err);
    }
  }

  // 开发模式下不自动启动后端（请手动运行 run_backend.sh）
  if (!isDev) {
    try {
      await startBackend();
      console.log('后端启动成功');
    } catch (err) {
      console.warn('后端启动失败，将使用外部后端:', err);
    }
  } else {
    console.log('[Dev] 开发模式：跳过自动启动后端，请手动运行 backend');
  }

  createWindow();
  createTray();
  registerShortcuts();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    } else {
      mainWindow?.show();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    isQuitting = true;
    app.quit();
  }
});

app.on('before-quit', () => {
  isQuitting = true;
  globalShortcut.unregisterAll();
  stopBackend();
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});
