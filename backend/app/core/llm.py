import os
import json
import asyncio
from typing import AsyncGenerator, List, Dict, Any, Optional
from openai import AsyncOpenAI, OpenAIError
from dotenv import load_dotenv

load_dotenv()

class LLMService:
    def __init__(self, api_key: Optional[str] = None, api_base_url: Optional[str] = None):
        # 优先使用传入的 API Key 和 Base URL，否则回退到环境变量
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.api_base_url = api_base_url or os.getenv("LLM_API_BASE_URL", "https://api.openai.com/v1")

        if not self.api_key:
            raise ValueError("LLM_API_KEY is not set. Please provide it in the config or .env file.")

        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.api_base_url)
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    async def _get_llm_response(self, messages: List[Dict[str, str]], stream: bool = False) -> AsyncGenerator[str, None]:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=stream,
                temperature=0.7,
            )

            if stream:
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
            else:
                if response.choices and response.choices[0].message.content:
                    yield response.choices[0].message.content
                else:
                    yield ""
        except OpenAIError as e:
            print(f"OpenAI API Error: {e}")
            yield f"对不起，LLM 服务出现错误：{e}"
        except Exception as e:
            print(f"LLM Service Error: {e}")
            yield f"对不起，LLM 服务出现未知错误：{e}"

    async def detect_question(self, text: str) -> bool:
        prompt = f"""你是一个问题检测器。请判断以下文本是否包含一个明确的问题，需要 AI 回答。只回答 '是' 或 '否'。

文本: {text}
"""
        messages = [
            {"role": "system", "content": "你是一个问题检测器。"},
            {"role": "user", "content": prompt}
        ]
        response_gen = self._get_llm_response(messages)
        response = "".join([chunk async for chunk in response_gen]).strip().lower()
        return "是" in response or "yes" in response

    async def generate_answer_stream(
        self,
        question_text: str,
        context_texts: List[str],
        system_prompt: str,
        course_materials: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[str, None]:
        full_context = "\n".join(context_texts)
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            messages.append({"role": "system", "content": "你是一个AI助教，请根据提供的课程内容和对话历史，简洁明了地回答学生的问题。"})

        if course_materials:
            messages.append({"role": "system", "content": f"以下是课程材料，请优先参考这些材料来回答问题：\n{course_materials}"})

        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": f"根据以上信息和对话历史，请回答以下问题：\n{question_text}\n\n相关讨论内容：\n{full_context}"})

        async for chunk in self._get_llm_response(messages, stream=True):
            yield chunk

