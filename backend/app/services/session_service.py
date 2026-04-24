"""
会话管理服务
管理每个 WebSocket 连接的听课会话状态，包括：
- 识别文本历史
- 预设提示词
- 课件内容
- 对话历史
"""
import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """单个听课会话的状态"""
    session_id: str
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    # 用户预设
    system_prompt: str = ""
    course_name: str = ""
    course_materials: str = ""  # 提取后的课件文本

    # 实时上下文
    transcript_buffer: List[str] = field(default_factory=list)  # 最近识别的文本
    full_transcript: List[str] = field(default_factory=list)    # 完整识别历史

    # LLM 对话历史
    chat_history: List[Dict] = field(default_factory=list)

    # 状态标志
    is_listening: bool = False
    is_generating: bool = False

    def add_transcript(self, text: str):
        """添加一条识别文本"""
        if not text.strip():
            return
        self.transcript_buffer.append(text)
        self.full_transcript.append(text)
        # 只保留最近 20 条上下文
        if len(self.transcript_buffer) > 20:
            self.transcript_buffer = self.transcript_buffer[-20:]
        self.last_active = time.time()

    def add_chat_turn(self, question: str, answer: str):
        """记录一轮问答到对话历史"""
        self.chat_history.append({"role": "user", "content": question})
        self.chat_history.append({"role": "assistant", "content": answer})
        # 只保留最近 10 轮
        if len(self.chat_history) > 20:
            self.chat_history = self.chat_history[-20:]

    def get_context(self) -> List[str]:
        """获取最近的上下文文本"""
        return self.transcript_buffer[-10:]


class SessionManager:
    """全局会话管理器"""

    def __init__(self):
        self._sessions: Dict[str, Session] = {}

    def create(self, session_id: str) -> Session:
        session = Session(session_id=session_id)
        self._sessions[session_id] = session
        logger.info(f"创建会话: {session_id}")
        return session

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            return self.create(session_id)
        return self._sessions[session_id]

    def delete(self, session_id: str):
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"删除会话: {session_id}")

    def cleanup_old(self, max_age_seconds: int = 3600):
        """清理超时的会话"""
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s.last_active > max_age_seconds
        ]
        for sid in expired:
            self.delete(sid)
        if expired:
            logger.info(f"清理了 {len(expired)} 个过期会话")


session_manager = SessionManager()
