/**
 * API 服务封装
 * 封装所有与后端 REST API 的交互
 */
import type { SessionConfig, UploadResponse } from '../types';

// 后端地址，生产环境通过环境变量配置
const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || '请求失败');
  }
  return res.json();
}

export const api = {
  /** 健康检查 */
  health: () => request<{ status: string }>('/api/health'),

  /** 创建新会话 */
  createSession: () => request<{ session_id: string }>('/api/session/new', { method: 'POST' }),

  /** 更新会话配置 */
  updateConfig: (sessionId: string, config: SessionConfig) =>
    request(`/api/session/${sessionId}/config`, {
      method: 'PUT',
      body: JSON.stringify({
        system_prompt: config.systemPrompt,
        course_name: config.courseName,
        course_materials: config.courseMaterials,
      }),
    }),

  /** 上传课件文件 */
  uploadMaterial: async (sessionId: string, file: File): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${BASE_URL}/api/session/${sessionId}/upload-material`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || '上传失败');
    }
    return res.json();
  },

  /** 清空课件内容 */
  clearMaterial: (sessionId: string) =>
    request(`/api/session/${sessionId}/material`, { method: 'DELETE' }),

  /** 获取完整识别记录 */
  getTranscript: (sessionId: string) =>
    request<{ transcript: string[]; total: number }>(`/api/session/${sessionId}/transcript`),
};

/** 构建 WebSocket URL */
export function buildWsUrl(sessionId: string): string {
  const wsBase = import.meta.env.VITE_WS_BASE_URL ||
    BASE_URL.replace(/^http/, 'ws');
  return `${wsBase}/ws/${sessionId}`;
}
