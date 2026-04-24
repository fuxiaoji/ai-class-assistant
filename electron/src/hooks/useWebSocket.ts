/**
 * WebSocket Hook（Electron 版本）
 * 使用 useRef 稳定回调引用，防止 React 重渲染时意外断开连接
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
  const mountedRef = useRef(true);

  // 用 ref 稳定回调，避免每次渲染产生新函数引用导致 effect 重新执行
  const onMessageRef = useRef(onMessage);
  const onStatusChangeRef = useRef(onStatusChange);
  useEffect(() => { onMessageRef.current = onMessage; }, [onMessage]);
  useEffect(() => { onStatusChangeRef.current = onStatusChange; }, [onStatusChange]);

  const [status, setStatus] = useState<ConnectionStatus>('disconnected');

  const updateStatus = useCallback((s: ConnectionStatus) => {
    if (!mountedRef.current) return;
    setStatus(s);
    onStatusChangeRef.current(s);
  }, []); // 空依赖，永远不变

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    if (pingTimerRef.current) clearInterval(pingTimerRef.current);
    reconnectCountRef.current = 999; // 阻止自动重连
    if (wsRef.current) {
      wsRef.current.onclose = null; // 移除 onclose，防止触发重连逻辑
      wsRef.current.close();
      wsRef.current = null;
    }
    updateStatus('disconnected');
  }, [updateStatus]); // updateStatus 是稳定引用，所以 disconnect 也是稳定的

  const connect = useCallback(async (sessionId: string) => {
    // 如果已有连接，先关闭
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);

    sessionIdRef.current = sessionId;
    reconnectCountRef.current = 0; // 重置重连计数
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
        // 心跳保活，每 25 秒发一次 ping
        pingTimerRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 25000);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as WSMessage;
          onMessageRef.current(msg);
        } catch (e) {
          console.error('[WS] 消息解析失败:', e);
        }
      };

      ws.onclose = (event) => {
        if (pingTimerRef.current) clearInterval(pingTimerRef.current);
        wsRef.current = null;
        console.log('[WS] 连接关闭, code:', event.code, 'reason:', event.reason);
        updateStatus('disconnected');
        // 自动重连（最多 5 次，指数退避）
        if (reconnectCountRef.current < 5 && mountedRef.current) {
          const delay = Math.min(1000 * Math.pow(2, reconnectCountRef.current), 10000);
          reconnectCountRef.current++;
          console.log(`[WS] ${delay}ms 后重连 (第 ${reconnectCountRef.current} 次)...`);
          reconnectTimerRef.current = setTimeout(() => {
            if (mountedRef.current) connect(sessionIdRef.current);
          }, delay);
        } else if (reconnectCountRef.current >= 5) {
          updateStatus('error');
        }
      };

      ws.onerror = (err) => {
        console.error('[WS] 连接错误:', err);
        updateStatus('error');
      };
    } catch (err) {
      console.error('[WS] 连接失败:', err);
      updateStatus('error');
    }
  }, [updateStatus]); // updateStatus 是稳定引用

  const send = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    } else {
      console.warn('[WS] 发送失败：连接未就绪');
    }
  }, []);

  // 组件卸载时清理，mountedRef 防止卸载后触发状态更新
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (pingTimerRef.current) clearInterval(pingTimerRef.current);
      reconnectCountRef.current = 999;
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []); // 空依赖，只在挂载/卸载时执行一次

  return { connect, send, disconnect, status };
}
