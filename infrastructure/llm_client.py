"""LLM客户端 — 统一API封装

支持 OpenAI-compatible API (deepseek/qwen/等)
通过 LLMConfig 按任务类型路由不同模型。
"""

import os
import json
import time
import threading
import atexit
from typing import Optional
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """LLM 调用结果"""
    content: str
    model: str
    usage: dict = None
    error: str = ""


class LLMClient:
    """统一LLM客户端 — OpenAI-compatible API

    支持双 endpoint：
    - 文字模型 → LLM_API_KEY / LLM_BASE_URL (默认 DeepSeek)
    - 视觉模型 → VISION_API_KEY / VISION_BASE_URL (阿里百炼)
    """

    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
        # 视觉模型专用 endpoint
        self.vision_api_key = os.getenv("VISION_API_KEY", self.api_key)
        self.vision_base_url = os.getenv("VISION_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self._session = None
        self._vision_session = None
        self._session_lock = threading.Lock()

    def close(self):
        """释放 Session 资源"""
        if self._session:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None
        if self._vision_session:
            try:
                self._vision_session.close()
            except Exception:
                pass
            self._vision_session = None

    def __del__(self):
        # 安全关闭 — try/except 防止 GC 时模块已清理
        try:
            self.close()
        except Exception:
            pass

    @property
    def session(self):
        if self._session is None:
            with self._session_lock:
                if self._session is None:
                    import requests
                    self._session = requests.Session()
                    self._session.headers.update({
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    })
        return self._session

    @property
    def vision_session(self):
        if self._vision_session is None:
            with self._session_lock:
                if self._vision_session is None:
                    import requests
                    self._vision_session = requests.Session()
                    self._vision_session.headers.update({
                        "Authorization": f"Bearer {self.vision_api_key}",
                        "Content-Type": "application/json",
                    })
        return self._vision_session

    def chat(
        self,
        messages: list[dict],
        model: str = "deepseek-v4-flash",
        temperature: float = 0.3,
        max_tokens: int = 2000,
        max_retries: int = 2,
    ) -> LLMResponse:
        """调用 Chat Completions API（文字模型，走 LLM_ENDPOINT）"""
        return self._chat_with_session(
            session=self.session,
            base_url=self.base_url,
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=max_retries,
        )

    def _chat_with_session(
        self,
        session,
        base_url: str,
        messages: list[dict],
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        max_retries: int = 2,
    ) -> LLMResponse:
        """内部：使用指定 session 和 base_url 调用 Chat API"""
        url = f"{base_url.rstrip('/')}/chat/completions"

        for attempt in range(max_retries + 1):
            try:
                resp = session.post(
                    url,
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                    timeout=120,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    choice = data["choices"][0]
                    return LLMResponse(
                        content=choice["message"]["content"],
                        model=data.get("model", model),
                        usage=data.get("usage"),
                    )
                else:
                    error_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)
                        continue
                    return LLMResponse(content="", model=model, error=error_msg)

            except Exception as e:
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                return LLMResponse(content="", model=model, error=str(e))

        return LLMResponse(content="", model=model, error="max retries exceeded")

    def chat_vision(
        self,
        system_prompt: str,
        image_urls: list[str],
        model: str = None,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """多模态调用 — 图片+文本（走阿里百炼 VISION_ENDPOINT）

        Args:
            system_prompt: 系统提示
            image_urls: 图片URL列表
            model: 视觉模型
            temperature: 温度

        Returns:
            LLMResponse
        """
        if model is None:
            model = os.getenv("LLM_IMAGE_MODEL", "qwen3-vl-plus")
        content = [{"type": "text", "text": system_prompt}]
        for url in image_urls:
            content.append({
                "type": "image_url",
                "image_url": {"url": url}
            })

        return self._chat_with_session(
            session=self.vision_session,
            base_url=self.vision_base_url,
            messages=[{"role": "user", "content": content}],
            model=model,
            temperature=temperature,
        )

    def chat_json_vision(
        self,
        system_prompt: str,
        image_urls: list[str],
        model: str = None,
        temperature: float = 0.3,
    ) -> dict:
        """多模态调用+解析JSON（走阿里百炼 VISION_ENDPOINT）"""
        if model is None:
            model = os.getenv("LLM_IMAGE_MODEL", "qwen3-vl-plus")
        resp = self.chat_vision(
            system_prompt=system_prompt,
            image_urls=image_urls,
            model=model,
            temperature=temperature,
        )
        if resp.error:
            return {"error": resp.error, "raw": resp.content}
        return self._parse_json_response(resp.content)

    def _parse_json_response(self, content: str) -> dict:
        """解析 LLM 返回的 JSON（修复常见格式问题）"""
        content = content.strip()

        # 去除 markdown 代码块
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        # 修复常见LLM JSON错误
        import re
        if content.startswith("{{") and content.endswith("}}"):
            content = content[1:-1]
        content = re.sub(r',\s*}', '}', content)
        content = re.sub(r',\s*]', ']', content)

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r'\{.*\}', content, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    pass
            return {"raw": content, "parse_error": True}

    def chat_json(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = 0.3,
    ) -> dict:
        """调用文字模型并解析JSON响应（走 LLM_ENDPOINT）"""
        if model is None:
            model = os.getenv("LLM_TEXT_MODEL", os.getenv("LLM_LIGHT_MODEL", "deepseek-chat"))
        resp = self.chat(messages, model=model, temperature=temperature)
        if resp.error:
            return {"error": resp.error, "raw": resp.content}
        return self._parse_json_response(resp.content)

# 全局单例（线程安全）
_llm_client: Optional[LLMClient] = None
_llm_lock = threading.Lock()


def get_llm_client() -> LLMClient:
    """获取全局 LLM 客户端（线程安全）"""
    global _llm_client
    if _llm_client is None:
        with _llm_lock:
            if _llm_client is None:
                _llm_client = LLMClient()
    return _llm_client
