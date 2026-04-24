/**
 * 配置面板
 * 提供课程名称、系统提示词预设、课件上传和文本粘贴功能
 */
import React, { useState, useRef } from 'react';
import type { SessionConfig, UploadResponse } from '../types';
import { api } from '../services/api';

interface ConfigPanelProps {
  sessionId: string;
  config: SessionConfig;
  onConfigChange: (config: Partial<SessionConfig>) => void;
  onSave: () => void;
}

const PRESET_PROMPTS = [
  {
    label: '通用课堂助手',
    value: '你是一个智能课堂助手，帮助学生理解课堂内容。当老师提问时，根据课件内容给出简洁准确的参考答案，用第一人称回答，不超过200字。',
  },
  {
    label: '数学课助手',
    value: '你是一个数学课堂助手，擅长解题和推导。当老师提出数学问题时，给出清晰的解题思路和步骤，必要时用公式表示。',
  },
  {
    label: '英语课助手',
    value: '你是一个英语课堂助手。当老师用英文提问时，用英文回答；当老师用中文提问时，用中文回答。注重语法和表达的准确性。',
  },
  {
    label: '编程课助手',
    value: '你是一个编程课堂助手，熟悉各种编程语言和算法。当老师提出编程相关问题时，给出简洁的代码示例或解释，重点突出核心概念。',
  },
];

export const ConfigPanel: React.FC<ConfigPanelProps> = ({
  sessionId,
  config,
  onConfigChange,
  onSave,
}) => {
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle');
  const [uploadMsg, setUploadMsg] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await api.updateConfig(sessionId, config);
      onSave();
    } catch (e) {
      console.error(e);
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
      // 更新本地显示
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
        disabled={!sessionId || isSaving}
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
