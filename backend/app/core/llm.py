"""
LLM 模块 - 大语言模型服务
负责：
1. 检测文本中是否包含问题（问题检测）
2. 结合课件内容和预设提示词生成答案（流式输出）
3. 支持动态 API 配置（从前端传入）
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
    
    def __init__(self, api_key: Optional[str] = None, api_base_url: Optional[str] = None):
        """
        初始化 LLM 服务
        Args:
            api_key: 可选的 API Key（优先使用前端传入的 Key）
            api_base_url: 可选的 API Base URL（优先使用前端传入的 URL）
        """
        # 优先使用前端传入的配置，否则使用环境变量
        final_api_key = api_key or settings.llm_api_key
        final_api_base_url = api_base_url or settings.llm_base_url
        
        if not final_api_key:
            raise ValueError("LLM_API_KEY 未配置，请在前端配置面板中填写 API Key")
        
        self.client = AsyncOpenAI(
            api_key=final_api_key,
            base_url=final_api_base_url,
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
        
        # 添加课件内容到系统提示词
        if course_materials and course_materials.strip():
            final_system_prompt += f"\n\n【课件内容参考】\n{course_materials}"
        
        # 构建消息列表
        messages = []
        
        # 添加历史记录
        if history:
            messages.extend(history)
        
        # 添加当前问题
        context_str = "\n".join(context_texts[-5:]) if context_texts else ""
        user_message = f"问题：{question_text}"
        if context_str:
            user_message += f"\n\n【最近的课堂内容】\n{context_str}"
        
        messages.append({"role": "user", "content": user_message})
        
        try:
            # 流式调用 LLM
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                system=final_system_prompt,
                stream=True,
                temperature=0.7,
                max_tokens=500,
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error(f"答案生成失败: {e}")
            yield f"[错误] 生成答案失败：{str(e)}"
