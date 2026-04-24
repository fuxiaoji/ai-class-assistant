/**
 * WebSocket Hook（Electron 版本）
 * 支持动态 WebSocket URL（从 Electron IPC 获取后端端口）
 */
import { useRef, useCallback, useState, useEffect } from 'react';
import type { ConnectionStatus, WSMessage } from '../types';
import { api } from '../services/api';

interface UseWebSocketOptions {
  onMessage: (msg: WSMessage) => void;
  onStatusChange: (status: ConnectionStatus) => void;
}

export function useWebSocket({ onMessage, onStatusChange }: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectCountRef = useRef(0);
  const sessionIdRef = useRef<string>('');
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');

  const updateStatus = useCallback((s: ConnectionStatus) => {
    setStatus(s);
    onStatusChange(s);
  }, [onStatusChange]);

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    if (pingTimerRef.current) clearInterval(pingTimerRef.current);
    reconnectCountRef.current = 999;
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    updateStatus('disconnected');
  }, [updateStatus]);

  const connect = useCallback(async (sessionId: string) => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    sessionIdRef.current = sessionId;
    updateStatus('connecting');

    try {
      const wsUrl = await api.getWsUrl(sessionId);
      console.log('[WS] 连接到:', wsUrl);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WS] 已连接');
        updateStatus('connected');
        reconnectCountRef.current = 0;
        // 心跳保活
        pingTimerRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 25000);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as WSMessage;
          onMessage(msg);
        } catch (e) {
          console.error('[WS] 消息解析失败:', e);
        }
      };

      ws.onclose = () => {
        if (pingTimerRef.current) clearInterval(pingTimerRef.current);
        wsRef.current = null;
        updateStatus('disconnected');
        if (reconnectCountRef.current < 5) {
          const delay = Math.min(1000 * Math.pow(2, reconnectCountRef.current), 10000);
          reconnectCountRef.current++;
          console.log(`[WS] ${delay}ms 后重连 (第${reconnectCountRef.current}次)...`);
          reconnectTimerRef.current = setTimeout(() => connect(sessionIdRef.current), delay);
        } else {
          updateStatus('error');
        }
      };

      ws.onerror = () => updateStatus('error');
    } catch (err) {
      console.error('[WS] 连接失败:', err);
      updateStatus('error');
    }
  }, [onMessage, updateStatus]);

  const send = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  useEffect(() => () => disconnect(), [disconnect]);

  return { connect, send, disconnect, status };
}
