"""
LLM 模块 - 大语言模型服务
支持动态 API Key（由前端传入），懒加载客户端
默认使用 MiniMax 接口
"""
import logging
from typing import AsyncGenerator, List, Dict, Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = """你是一个智能课堂助手，正在帮助学生实时理解课堂内容。
你的任务：
1. 当老师提出问题时，根据课件内容和课程背景，给出简洁、准确的参考答案
2. 答案要适合学生在课堂上快速理解和回答
3. 如果有课件内容，优先基于课件内容作答
4. 回答要简洁，通常不超过200字，除非问题需要详细解释
注意：你的回答是给学生作为参考的，请用第一人称"我认为..."或直接给出答案。"""

QUESTION_DETECT_PROMPT = """判断以下文本是否包含老师向学生提出的问题或需要学生回答的内容。
文本：{text}
只需回答 "YES" 或 "NO"。
- YES：文本中包含疑问句、提问、或明显的互动邀请（如"大家觉得呢"、"谁来回答"、"这道题怎么解"等）
- NO：文本是普通陈述，没有提问"""

# 默认使用 MiniMax
DEFAULT_API_BASE_URL = "https://api.minimax.chat/v1"
DEFAULT_MODEL = "MiniMax-Text-01"


class LLMService:
    """LLM 服务，支持动态 API Key（懒加载客户端）"""

    def __init__(self):
        self._api_key: str = ""
        self._base_url: str = DEFAULT_API_BASE_URL
        self._model: str = DEFAULT_MODEL
        self._client: Optional[AsyncOpenAI] = None

    def configure(self, api_key: str, base_url: str = "", model: str = ""):
        """由 WebSocket 会话调用，动态更新 API 配置"""
        key_changed = api_key and api_key != self._api_key
        url_changed = base_url and base_url != self._base_url
        if api_key:
            self._api_key = api_key
        if base_url:
            self._base_url = base_url
        if model:
            self._model = model
        if key_changed or url_changed:
            self._client = None  # 配置变更时重置客户端

    def _get_client(self) -> AsyncOpenAI:
        """获取客户端（懒加载，避免启动时因无 Key 而报错）"""
        if self._client is None:
            if not self._api_key:
                raise ValueError("API Key 未配置，请在「课程配置」中填写 API Key 后点击保存")
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self._client

    async def detect_question(self, text: str) -> bool:
        if not text or len(text.strip()) < 5:
            return False
        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": QUESTION_DETECT_PROMPT.format(text=text)}],
                max_tokens=5,
                temperature=0,
            )
            result = response.choices[0].message.content.strip().upper()
            is_question = result.startswith("YES")
            logger.info(f"问题检测: '{text[:50]}' -> {is_question}")
            return is_question
        except ValueError as e:
            logger.warning(f"问题检测跳过（未配置 Key）: {e}")
            return False
        except Exception as e:
            logger.error(f"问题检测失败: {e}")
            return False

    async def generate_answer_stream(
        self,
        question_text: str,
        context_texts: List[str],
        system_prompt: str = "",
        course_materials: str = "",
        history: Optional[List[Dict]] = None,
    ) -> AsyncGenerator[str, None]:
        final_system_prompt = system_prompt.strip() if system_prompt.strip() else DEFAULT_SYSTEM_PROMPT
        if course_materials.strip():
            final_system_prompt += f"\n\n## 课件内容\n\n{course_materials}"

        context_str = ""
        if context_texts:
            recent = context_texts[-5:]
            context_str = "\n".join(f"- {t}" for t in recent)

        user_message = f"""## 课堂上下文（最近内容）
{context_str if context_str else "（无）"}

## 老师的问题
{question_text}

请给出简洁的参考答案："""

        messages = [{"role": "system", "content": final_system_prompt}]
        if history:
            messages.extend(history[-6:])
        messages.append({"role": "user", "content": user_message})

        try:
            client = self._get_client()
            stream = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                stream=True,
                temperature=0.7,
                max_tokens=500,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except ValueError as e:
            yield f"[错误：{str(e)}]"
        except Exception as e:
            logger.error(f"LLM 生成失败: {e}")
            yield f"[生成失败: {str(e)}]"


# 全局单例（懒加载，启动时不初始化客户端）
llm_service = LLMService()
