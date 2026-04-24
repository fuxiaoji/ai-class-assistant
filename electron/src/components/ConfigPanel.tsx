/**
 * 配置面板组件
 * 支持 LLM API 配置、课程配置、课件上传
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
  const [showPresets, setShowPresets] = useState(false);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await new Promise(r => setTimeout(r, 300));
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
      setUploadMsg(`已解析 ${result.extracted_text_length} 字符`);
      onConfigChange({ courseMaterials: `[已上传: ${file.name}]\n${result.preview}...` });
    } catch (err) {
      setUploadStatus('error');
      setUploadMsg(`上传失败: ${err instanceof Error ? err.message : '未知错误'}`);
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

  const inputStyle: React.CSSProperties = {
    width: '100%',
    boxSizing: 'border-box',
    padding: '8px 12px',
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '6px',
    color: '#f1f5f9',
    fontSize: '13px',
    outline: 'none',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', paddingBottom: '16px' }}>

      {/* LLM API 配置 */}
      <div style={{ background: 'rgba(30,58,138,0.3)', border: '1px solid rgba(59,130,246,0.4)', borderRadius: '8px', padding: '16px' }}>
        <h3 style={{ color: '#93c5fd', fontSize: '13px', fontWeight: 600, marginBottom: '12px', marginTop: 0 }}>
          🔑 LLM API 配置
        </h3>

        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', color: '#cbd5e1', fontSize: '12px', marginBottom: '4px' }}>
            API Key
          </label>
          <input
            type="password"
            style={inputStyle}
            placeholder="sk-... (OpenAI / DeepSeek / 其他兼容接口)"
            value={apiKey}
            onChange={e => onApiKeyChange(e.target.value)}
          />
          <p style={{ color: '#64748b', fontSize: '11px', marginTop: '4px', marginBottom: 0 }}>
            自动保存到本地，下次打开无需重新填写
          </p>
        </div>

        <div>
          <label style={{ display: 'block', color: '#cbd5e1', fontSize: '12px', marginBottom: '4px' }}>
            API Base URL
          </label>
          <input
            type="text"
            style={inputStyle}
            placeholder="https://api.minimax.chat/v1"
            value={apiBaseUrl}
            onChange={e => onApiBaseUrlChange(e.target.value)}
          />
          <p style={{ color: '#64748b', fontSize: '11px', marginTop: '4px', marginBottom: 0 }}>
            DeepSeek: https://api.deepseek.com/v1 &nbsp;|&nbsp; 默认: OpenAI
          </p>
        </div>
      </div>

      {/* 课程名称 */}
      <div>
        <label style={{ display: 'block', color: '#cbd5e1', fontSize: '13px', fontWeight: 500, marginBottom: '6px' }}>
          课程名称
        </label>
        <input
          type="text"
          style={inputStyle}
          placeholder="例如：高等数学、大学英语..."
          value={config.courseName}
          onChange={e => onConfigChange({ courseName: e.target.value })}
        />
      </div>

      {/* AI 角色提示词 */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
          <label style={{ color: '#cbd5e1', fontSize: '13px', fontWeight: 500 }}>
            AI 角色提示词
          </label>
          <div style={{ position: 'relative' }}>
            <button
              style={{ color: '#38bdf8', fontSize: '12px', background: 'none', border: 'none', cursor: 'pointer' }}
              onClick={() => setShowPresets(v => !v)}
            >
              预设模板 ▾
            </button>
            {showPresets && (
              <div style={{
                position: 'absolute', right: 0, top: '24px', zIndex: 20,
                background: '#1e293b', border: '1px solid #334155',
                borderRadius: '8px', boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
                width: '220px', overflow: 'hidden',
              }}>
                {PRESET_PROMPTS.map(p => (
                  <button
                    key={p.label}
                    style={{
                      display: 'block', width: '100%', textAlign: 'left',
                      padding: '8px 12px', color: '#cbd5e1', fontSize: '13px',
                      background: 'none', border: 'none', cursor: 'pointer',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#334155')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                    onClick={() => { onConfigChange({ systemPrompt: p.value }); setShowPresets(false); }}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <textarea
          style={{ ...inputStyle, resize: 'vertical', minHeight: '100px' }}
          rows={5}
          placeholder="描述 AI 的角色和回答风格..."
          value={config.systemPrompt}
          onChange={e => onConfigChange({ systemPrompt: e.target.value })}
        />
      </div>

      {/* 课件内容 */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
          <label style={{ color: '#cbd5e1', fontSize: '13px', fontWeight: 500 }}>
            课件内容
          </label>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              style={{ color: '#38bdf8', fontSize: '12px', background: 'none', border: 'none', cursor: 'pointer' }}
              onClick={() => fileInputRef.current?.click()}
            >
              上传文件
            </button>
            {config.courseMaterials && (
              <button
                style={{ color: '#f87171', fontSize: '12px', background: 'none', border: 'none', cursor: 'pointer' }}
                onClick={handleClearMaterial}
              >
                清空
              </button>
            )}
          </div>
        </div>
        <input ref={fileInputRef} type="file" accept=".pdf,.txt,.md,.docx" style={{ display: 'none' }} onChange={handleFileUpload} />
        {uploadStatus !== 'idle' && (
          <p style={{
            fontSize: '12px', marginBottom: '6px', marginTop: 0,
            color: uploadStatus === 'success' ? '#34d399' : uploadStatus === 'error' ? '#f87171' : '#94a3b8',
          }}>
            {uploadMsg}
          </p>
        )}
        <textarea
          style={{ ...inputStyle, resize: 'vertical', minHeight: '120px', fontSize: '12px' }}
          rows={6}
          placeholder="粘贴课件文字内容，或点击「上传文件」自动提取（支持 PDF、TXT、MD、DOCX）..."
          value={config.courseMaterials}
          onChange={e => onConfigChange({ courseMaterials: e.target.value })}
        />
        <p style={{ color: '#64748b', fontSize: '11px', marginTop: '4px', marginBottom: 0 }}>
          {config.courseMaterials.length} 字符 · AI 将优先基于此内容回答
        </p>
      </div>

      {/* 保存按钮 */}
      <button
        style={{
          width: '100%',
          padding: '10px',
          background: (sessionId && apiKey) ? '#0284c7' : '#475569',
          color: 'white',
          border: 'none',
          borderRadius: '8px',
          fontSize: '14px',
          fontWeight: 600,
          cursor: (sessionId && apiKey) ? 'pointer' : 'not-allowed',
          transition: 'background 0.2s',
        }}
        onClick={handleSave}
        disabled={!sessionId || isSaving || !apiKey}
        title={!apiKey ? '请先填写 API Key' : '保存配置'}
      >
        {isSaving ? '保存中...' : (!apiKey ? '请先填写 API Key' : '✓ 保存配置')}
      </button>
    </div>
  );
};
