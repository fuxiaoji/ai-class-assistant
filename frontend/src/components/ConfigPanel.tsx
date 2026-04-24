/**
 * 配置面板组件
 * 支持课程配置、课件上传、LLM API 配置
 */
import React, { useRef, useState } from 'react';
import { api } from '../services/api';
import type { SessionConfig, UploadResponse } from '../types';

interface ConfigPanelProps {
  sessionId: string;
  config: SessionConfig;
  apiKey: string;
  apiBaseUrl: string;
  onConfigChange: (partial: Partial<SessionConfig>) => void;
  onApiKeyChange: (key: string) => void;
  onApiBaseUrlChange: (url: string) => void;
  onSave: () => void;
}

const PRESET_PROMPTS = [
  { label: '学术助教', value: '你是一个知识渊博的大学助教。请根据课件内容用简洁清晰的语言回答问题，必要时举例说明。' },
  { label: '考试辅导', value: '你是一个考试辅导老师。请根据课件内容回答问题，并提供解题思路和关键要点。' },
  { label: '启蒙讲师', value: '你是一个耐心的启蒙讲师。请用通俗易懂的语言解释概念，避免过于复杂的表述。' },
];

export const ConfigPanel: React.FC<ConfigPanelProps> = ({
  sessionId,
  config,
  apiKey,
  apiBaseUrl,
  onConfigChange,
  onApiKeyChange,
  onApiBaseUrlChange,
  onSave,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle');
  const [uploadMsg, setUploadMsg] = useState('');

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await new Promise(r => setTimeout(r, 500));
      onSave();
    } finally {
      setIsSaving(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !sessionId) return;
    setUploadStatus('uploading');
    setUploadMsg('正在上传并解析...');
    try {
      const result: UploadResponse = await api.uploadMaterial(sessionId, file);
      setUploadStatus('success');
      setUploadMsg(`✓ 已解析 ${result.extracted_text_length} 字符`);
      onConfigChange({ courseMaterials: `[已上传: ${file.name}]\n${result.preview}...` });
    } catch (err) {
      setUploadStatus('error');
      setUploadMsg(`✗ ${err instanceof Error ? err.message : '上传失败'}`);
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleClearMaterial = async () => {
    if (!sessionId) return;
    await api.clearMaterial(sessionId);
    onConfigChange({ courseMaterials: '' });
    setUploadStatus('idle');
    setUploadMsg('');
  };

  return (
    <div className="flex flex-col gap-5 overflow-y-auto">
      {/* LLM API 配置 */}
      <div className="bg-blue-900/20 border border-blue-700/50 rounded-lg p-4">
        <h3 className="text-sm font-medium text-blue-300 mb-3">🔑 LLM API 配置</h3>
        
        {/* API Key */}
        <div className="mb-3">
          <label className="block text-xs font-medium text-slate-300 mb-1">API Key</label>
          <input
            type="password"
            className="input-field text-sm"
            placeholder="sk-... (OpenAI、DeepSeek 等兼容接口)"
            value={apiKey}
            onChange={e => onApiKeyChange(e.target.value)}
          />
          <p className="text-xs text-slate-500 mt-1">💾 自动保存到浏览器本地存储</p>
        </div>

        {/* API Base URL */}
        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1">API Base URL</label>
          <input
            type="text"
            className="input-field text-sm"
            placeholder="https://api.openai.com/v1"
            value={apiBaseUrl}
            onChange={e => onApiBaseUrlChange(e.target.value)}
          />
          <p className="text-xs text-slate-500 mt-1">
            默认：OpenAI | 可切换：DeepSeek、Anthropic 等兼容接口
          </p>
        </div>
      </div>

      {/* 课程名称 */}
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1.5">课程名称</label>
        <input
          type="text"
          className="input-field"
          placeholder="例如：高等数学、大学英语..."
          value={config.courseName}
          onChange={e => onConfigChange({ courseName: e.target.value })}
        />
      </div>

      {/* 系统提示词 */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-sm font-medium text-slate-300">AI 角色提示词</label>
          <div className="relative group">
            <button className="text-xs text-sky-400 hover:text-sky-300">预设模板 ▾</button>
            <div className="absolute right-0 top-6 z-10 hidden group-hover:block bg-slate-800 border border-slate-700 rounded-lg shadow-xl w-56 overflow-hidden">
              {PRESET_PROMPTS.map(p => (
                <button
                  key={p.label}
                  className="w-full text-left px-3 py-2 text-sm text-slate-300 hover:bg-slate-700 transition-colors"
                  onClick={() => onConfigChange({ systemPrompt: p.value })}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <textarea
          className="textarea-field"
          rows={5}
          placeholder="描述 AI 的角色和回答风格，例如：你是一个大学物理助教，请根据课件内容用简洁的语言回答老师的问题..."
          value={config.systemPrompt}
          onChange={e => onConfigChange({ systemPrompt: e.target.value })}
        />
      </div>

      {/* 课件内容 */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-sm font-medium text-slate-300">课件内容</label>
          <div className="flex gap-2">
            <button
              className="text-xs text-sky-400 hover:text-sky-300"
              onClick={() => fileInputRef.current?.click()}
            >
              上传文件
            </button>
            {config.courseMaterials && (
              <button
                className="text-xs text-red-400 hover:text-red-300"
                onClick={handleClearMaterial}
              >
                清空
              </button>
            )}
          </div>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.txt,.md,.docx"
          className="hidden"
          onChange={handleFileUpload}
        />
        {uploadStatus !== 'idle' && (
          <p className={`text-xs mb-1.5 ${
            uploadStatus === 'success' ? 'text-emerald-400' :
            uploadStatus === 'error' ? 'text-red-400' : 'text-slate-400'
          }`}>
            {uploadMsg}
          </p>
        )}
        <textarea
          className="textarea-field text-xs"
          rows={6}
          placeholder="粘贴课件文字内容，或点击「上传文件」自动提取（支持 PDF、TXT、MD、DOCX）..."
          value={config.courseMaterials}
          onChange={e => onConfigChange({ courseMaterials: e.target.value })}
        />
        <p className="text-xs text-slate-500 mt-1">
          {config.courseMaterials.length} 字符 · AI 将优先基于此内容回答
        </p>
      </div>

      {/* 保存按钮 */}
      <button
        className="btn-primary justify-center"
        onClick={handleSave}
        disabled={!sessionId || isSaving || !apiKey}
        title={!apiKey ? '请先填写 API Key' : ''}
      >
        {isSaving ? (
          <>
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
            </svg>
            保存中...
          </>
        ) : (
          <>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7"/>
            </svg>
            保存配置
          </>
        )}
      </button>
    </div>
  );
};
