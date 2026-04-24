"""
LLM 模块 - 大语言模型服务
负责：
1. 检测文本中是否包含问题（问题检测）
2. 结合课件内容和预设提示词生成答案（流式输出）
"""
import logging
from typing import AsyncGenerator, List, Dict, Optional
from openai import AsyncOpenAI
from .config import settings

logger = logging.getLogger(__name__)

# 默认系统提示词
DEFAULT_SYSTEM_PROMPT = """你是一个智能课堂助手，正在帮助学生实时理解课堂内容。

你的任务：
1. 当老师提出问题时，根据课件内容和课程背景，给出简洁、准确的参考答案
2. 答案要适合学生在课堂上快速理解和回答
3. 如果有课件内容，优先基于课件内容作答
4. 回答要简洁，通常不超过200字，除非问题需要详细解释

注意：你的回答是给学生作为参考的，请用第一人称"我认为..."或直接给出答案。"""

# 问题检测提示词
QUESTION_DETECT_PROMPT = """判断以下文本是否包含老师向学生提出的问题或需要学生回答的内容。

文本：{text}

只需回答 "YES" 或 "NO"。
- YES：文本中包含疑问句、提问、或明显的互动邀请（如"大家觉得呢"、"谁来回答"、"这道题怎么解"等）
- NO：文本是普通陈述，没有提问"""


class LLMService:
    """LLM 服务，封装问题检测和答案生成"""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
        self.model = settings.llm_model

    async def detect_question(self, text: str) -> bool:
        """
        检测文本中是否包含问题

        Args:
            text: ASR 识别出的文本

        Returns:
            True 表示包含问题，False 表示不包含
        """
        if not text or len(text.strip()) < 5:
            return False

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": QUESTION_DETECT_PROMPT.format(text=text),
                    }
                ],
                max_tokens=5,
                temperature=0,
            )
            result = response.choices[0].message.content.strip().upper()
            is_question = result.startswith("YES")
            logger.info(f"问题检测: '{text[:50]}...' -> {is_question}")
            return is_question
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
        """
        流式生成答案

        Args:
            question_text: 老师提出的问题文本
            context_texts: 最近几条识别文本（上下文）
            system_prompt: 用户自定义的系统提示词
            course_materials: 预设的课件内容
            history: 对话历史

        Yields:
            答案文本片段（流式）
        """
        # 构建系统提示词
        final_system_prompt = system_prompt.strip() if system_prompt.strip() else DEFAULT_SYSTEM_PROMPT

        if course_materials.strip():
            final_system_prompt += f"\n\n## 课件内容\n\n{course_materials}"

        # 构建用户消息
        context_str = ""
        if context_texts:
            recent = context_texts[-5:]  # 最近5条上下文
            context_str = "\n".join(f"- {t}" for t in recent)

        user_message = f"""## 课堂上下文（最近内容）
{context_str if context_str else "（无）"}

## 老师的问题
{question_text}

请给出简洁的参考答案："""

        messages = [{"role": "system", "content": final_system_prompt}]

        if history:
            messages.extend(history[-6:])  # 最多保留3轮历史

        messages.append({"role": "user", "content": user_message})

        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=0.7,
                max_tokens=500,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content

        except Exception as e:
            logger.error(f"LLM 生成失败: {e}")
            yield f"[生成失败: {str(e)}]"


# 单例
llm_service = LLMService()
