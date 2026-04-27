"""
LLM 模块 - 大语言模型服务
支持动态 API Key（由前端传入），直接调用 OpenAI 兼容接口
默认使用 MiniMax 接口
"""
import json
import logging
from typing import AsyncGenerator, List, Dict, Optional

import httpx

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
DEFAULT_API_BASE_URL = "https://api.minimaxi.com/v1"
DEFAULT_MODEL = "MiniMax-M2.7"


class LLMService:
    """LLM 服务，支持动态 API Key"""

    def __init__(self):
        self._api_key: str = ""
        self._base_url: str = DEFAULT_API_BASE_URL
        self._model: str = DEFAULT_MODEL

    def is_configured(self) -> bool:
        """检查 LLM 服务是否已配置 API Key"""
        return bool(self._api_key)

    def configure(self, api_key: str, base_url: str = "", model: str = ""):
        """由 WebSocket 会话调用，动态更新 API 配置"""
        if api_key:
            self._api_key = api_key
        if base_url:
            self._base_url = base_url
        if model:
            self._model = model

    def _get_api_endpoint(self) -> str:
        base_url = self._base_url.rstrip("/")
        if not self._api_key:
            raise ValueError("API Key 未配置，请在前端课程配置中填写后点击保存")
        return f"{base_url}/chat/completions"

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _extract_delta_content(chunk_data: dict) -> str:
        try:
            choices = chunk_data.get("choices") or []
            if not choices:
                return ""
            delta = choices[0].get("delta") or {}
            return str(delta.get("content") or "")
        except Exception:
            return ""

    @staticmethod
    def _strip_think_segments(text: str, in_think: bool) -> tuple[str, bool]:
        result = ""
        i = 0
        while i < len(text):
            if not in_think:
                think_start = text.find("<think>", i)
                if think_start == -1:
                    result += text[i:]
                    break
                result += text[i:think_start]
                in_think = True
                i = think_start + len("<think>")
            else:
                think_end = text.find("</think>", i)
                if think_end == -1:
                    break
                in_think = False
                i = think_end + len("</think>")
                while i < len(text) and text[i] in ("\n", "\r", " "):
                    i += 1
        return result, in_think

    async def detect_question(self, text: str) -> bool:
        if not text or len(text.strip()) < 5:
            return False
        try:
            payload = {
                "model": self._model,
                "messages": [{"role": "user", "content": QUESTION_DETECT_PROMPT.format(text=text)}],
                "max_tokens": 5,
                "temperature": 0,
            }
            async with httpx.AsyncClient(timeout=30.0, trust_env=True) as client:
                response = await client.post(
                    self._get_api_endpoint(),
                    headers=self._build_headers(),
                    json=payload,
                )
            response.raise_for_status()
            result_json = response.json()
            result = result_json["choices"][0]["message"]["content"].strip().upper()
            is_question = result.startswith("YES")
            logger.info(f"问题检测: '{text[:50]}' -> {is_question}")
            return is_question
        except ValueError as e:
            logger.warning(f"问题检测跳过（未配置 Key）: {e}")
            return False
        except httpx.HTTPStatusError as e:
            logger.warning(f"问题检测接口返回错误: {e.response.status_code} {e.response.text[:200]}")
            return False
        except Exception as e:
            logger.error(f"问题检测失败: {e}")
            return False

    async def translate_text(self, text: str, target_lang: str = "en", source_lang: str = "") -> str:
        if not text or not text.strip():
            return ""

        target_lang = (target_lang or "en").strip().lower()
        source_lang = (source_lang or "").strip().lower()
        if source_lang and source_lang == target_lang:
            return ""

        prompt = (
            "请将以下课堂字幕翻译成目标语言，只返回译文，不要解释。\n"
            f"源语言: {source_lang or 'auto'}\n"
            f"目标语言: {target_lang}\n"
            f"文本: {text}"
        )

        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
            "temperature": 0.1,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0, trust_env=True) as client:
                response = await client.post(
                    self._get_api_endpoint(),
                    headers=self._build_headers(),
                    json=payload,
                )
            response.raise_for_status()
            result_json = response.json()
            translated = str(result_json["choices"][0]["message"]["content"]).strip()
            return translated
        except ValueError as e:
            logger.warning(f"翻译跳过（未配置 Key）: {e}")
            return ""
        except Exception as e:
            logger.warning(f"翻译失败，返回空译文: {e}")
            return ""

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
            payload = {
                "model": self._model,
                "messages": messages,
                "stream": True,
                "temperature": 0.7,
                "max_tokens": 500,
            }

            timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
            async with httpx.AsyncClient(timeout=timeout, trust_env=True) as client:
                async with client.stream(
                    "POST",
                    self._get_api_endpoint(),
                    headers=self._build_headers(),
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    in_think = False
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line.removeprefix("data:").strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk_data = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        text = self._extract_delta_content(chunk_data)
                        if not text:
                            continue
                        result, in_think = self._strip_think_segments(text, in_think)
                        if result:
                            yield result
        except ValueError as e:
            yield f"[错误：{str(e)}]"
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response else 0
            error_text = ""
            if e.response is not None:
                try:
                    error_text = (await e.response.aread()).decode("utf-8", errors="ignore")
                except Exception:
                    try:
                        error_text = e.response.text
                    except Exception:
                        error_text = ""
            detail = error_text[:300] if error_text else str(e)
            yield f"[生成失败: {status_code} {detail}]"
        except Exception as e:
            logger.error(f"LLM 生成失败: {e}")
            yield f"[生成失败: {str(e)}]"


# 全局单例（懒加载，启动时不初始化客户端）
llm_service = LLMService()
