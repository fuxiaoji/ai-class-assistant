/**
 * WebSocket Hook
 * 管理与后端的 WebSocket 连接，处理消息收发和重连逻辑
 */
import { useRef, useState, useCallback, useEffect } from 'react';
import type { WSMessage, ConnectionStatus } from '../types';
import { buildWsUrl } from '../services/api';

interface UseWebSocketOptions {
  onMessage: (msg: WSMessage) => void;
  onStatusChange?: (status: ConnectionStatus) => void;
}

export function useWebSocket({ onMessage, onStatusChange }: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const sessionIdRef = useRef<string>('');

  const updateStatus = useCallback((s: ConnectionStatus) => {
    setStatus(s);
    onStatusChange?.(s);
  }, [onStatusChange]);

  const disconnect = useCallback(() => {
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    if (pingTimer.current) clearInterval(pingTimer.current);
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    updateStatus('disconnected');
  }, [updateStatus]);

  const connect = useCallback((sessionId: string) => {
    disconnect();
    sessionIdRef.current = sessionId;
    updateStatus('connecting');

    const ws = new WebSocket(buildWsUrl(sessionId));
    wsRef.current = ws;

    ws.onopen = () => {
      updateStatus('connected');
      // 心跳保活
      pingTimer.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 25000);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as WSMessage;
        onMessage(msg);
      } catch {
        console.warn('无效的 WebSocket 消息:', event.data);
      }
    };

    ws.onerror = () => {
      updateStatus('error');
    };

    ws.onclose = () => {
      if (pingTimer.current) clearInterval(pingTimer.current);
      updateStatus('disconnected');
      // 3 秒后自动重连
      reconnectTimer.current = setTimeout(() => {
        if (sessionIdRef.current) connect(sessionIdRef.current);
      }, 3000);
    };
  }, [disconnect, onMessage, updateStatus]);

  const send = useCallback((data: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  useEffect(() => {
    return () => disconnect();
  }, [disconnect]);

  return { connect, disconnect, send, status };
}
