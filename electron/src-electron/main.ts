import { app, BrowserWindow, ipcMain, globalShortcut, Tray, Menu, nativeImage, dialog } from 'electron';
import * as path from 'path';
import { spawn, ChildProcess } from 'child_process';
import * as fs from 'fs';

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let backendProcess: ChildProcess | null = null;
const BACKEND_PORT = 18765;

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;

function startBackend() {
  let executablePath = '';
  let args: string[] = [];

  if (isDev) {
    executablePath = 'python3';
    args = ['-m', 'uvicorn', 'main:app', '--port', BACKEND_PORT.toString()];
    const backendDir = path.join(app.getAppPath(), '..', 'backend');
    backendProcess = spawn(executablePath, args, { cwd: backendDir, shell: true });
  } else {
    executablePath = path.join(process.resourcesPath, 'bin', 'ai-class-backend');
    if (process.platform === 'win32') executablePath += '.exe';
    if (fs.existsSync(executablePath)) {
      backendProcess = spawn(executablePath, ['--port', BACKEND_PORT.toString()], {
        cwd: path.dirname(executablePath),
        env: { ...process.env, PORT: BACKEND_PORT.toString() }
      });
    }
  }
}

function createTray() {
  const iconPath = path.join(__dirname, '../public/vite.svg');
  const icon = nativeImage.createFromPath(iconPath);
  tray = new Tray(icon.resize({ width: 16, height: 16 }));
  const contextMenu = Menu.buildFromTemplate([
    { label: '显示主窗口', click: () => mainWindow?.show() },
    { label: '切换监听 (⌘⇧L)', click: () => mainWindow?.webContents.send('toggle-listening') },
    { type: 'separator' },
    { label: '退出', click: () => app.quit() }
  ]);
  tray.setToolTip('AI 听课助手');
  tray.setContextMenu(contextMenu);
}

function registerShortcuts() {
  globalShortcut.register('CommandOrControl+Shift+L', () => {
    mainWindow?.webContents.send('toggle-listening');
  });
  globalShortcut.register('CommandOrControl+Shift+W', () => {
    if (mainWindow?.isVisible()) {
      mainWindow.hide();
    } else {
      mainWindow?.show();
    }
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1000, height: 700,
    minWidth: 800, minHeight: 600,
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#0f172a',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  mainWindow.once('ready-to-show', () => mainWindow?.show());
}

app.whenReady().then(() => {
  startBackend();
  createWindow();
  createTray();
  registerShortcuts();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
  if (backendProcess) backendProcess.kill();
});

ipcMain.handle('select-file', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openFile'],
    filters: [{ name: 'Documents', extensions: ['pdf', 'docx', 'txt', 'md'] }]
  });
  if (!result.canceled && result.filePaths.length > 0) {
    return result.filePaths[0];
  }
  return null;
});
