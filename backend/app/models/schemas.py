"""
数据模型定义
"""
from pydantic import BaseModel
from typing import Optional, List


# ===== WebSocket 消息模型 =====

class WSMessage(BaseModel):
    """WebSocket 消息基类"""
    type: str  # 消息类型


class AudioChunkMessage(BaseModel):
    """客户端发送的音频数据块（Base64 编码）"""
    type: str = "audio_chunk"
    data: str  # base64 编码的音频数据
    session_id: str


class ManualAskMessage(BaseModel):
    """用户手动触发提问"""
    type: str = "manual_ask"
    session_id: str
    question: Optional[str] = None  # 可选的手动输入问题


class ConfigUpdateMessage(BaseModel):
    """更新会话配置"""
    type: str = "config_update"
    session_id: str
    system_prompt: Optional[str] = None
    course_name: Optional[str] = None
    course_materials: Optional[str] = None


# ===== REST API 模型 =====

class SessionConfig(BaseModel):
    """会话配置"""
    system_prompt: str = ""
    course_name: str = ""
    course_materials: str = ""


class SessionConfigResponse(BaseModel):
    """会话配置响应"""
    session_id: str
    system_prompt: str
    course_name: str
    course_materials_preview: str  # 课件内容预览（前200字）
    is_listening: bool


class TranscriptItem(BaseModel):
    """识别文本条目"""
    text: str
    is_question: bool = False


class UploadResponse(BaseModel):
    """文件上传响应"""
    filename: str
    extracted_text_length: int
    preview: str  # 前200字预览
