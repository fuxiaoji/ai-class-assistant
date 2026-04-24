/**
 * API 服务封装（Electron 版本）
 * 动态获取后端端口，支持 Electron 本地后端和远程后端
 */
import { getBackendBaseUrl } from '../utils/electron';

let cachedBaseUrl: string | null = null;

async function getBaseUrl(): Promise<string> {
  if (!cachedBaseUrl) {
    cachedBaseUrl = await getBackendBaseUrl();
  }
  return cachedBaseUrl;
}

export function resetBaseUrlCache() {
  cachedBaseUrl = null;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const base = await getBaseUrl();
  const res = await fetch(`${base}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  createSession: () =>
    request<{ session_id: string }>('/api/session/new', { method: 'POST' }),

  updateConfig: (sessionId: string, config: {
    systemPrompt: string;
    courseName: string;
    courseMaterials: string;
  }) =>
    request(`/api/session/${sessionId}/config`, {
      method: 'PUT',
      body: JSON.stringify({
        system_prompt: config.systemPrompt,
        course_name: config.courseName,
        course_materials: config.courseMaterials,
      }),
    }),

  uploadMaterial: async (sessionId: string, file: File) => {
    const base = await getBaseUrl();
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${base}/api/session/${sessionId}/upload-material`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<{ extracted_text_length: number; preview: string }>;
  },

  clearMaterial: (sessionId: string) =>
    request(`/api/session/${sessionId}/material`, { method: 'DELETE' }),

  healthCheck: async (): Promise<boolean> => {
    try {
      const base = await getBaseUrl();
      const res = await fetch(`${base}/api/health`, { signal: AbortSignal.timeout(3000) });
      return res.ok;
    } catch {
      return false;
    }
  },

  getWsUrl: async (sessionId: string): Promise<string> => {
    const base = await getBaseUrl();
    const wsBase = base.replace('http://', 'ws://').replace('https://', 'wss://');
    return `${wsBase}/ws/${sessionId}`;
  },
};
