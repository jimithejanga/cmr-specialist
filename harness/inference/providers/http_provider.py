"""HTTP Inference Provider for communicating with remote inference servers (e.g., OgunLABS GPU, vLLM, Ollama, OpenAI)."""
from typing import Any, Dict, List, Optional
import requests
from .base import BaseInferenceProvider


class HttpInferenceProvider(BaseInferenceProvider):
    """Communicates with remote inference endpoints over HTTP."""

    def __init__(self, endpoint_url: str, api_key: Optional[str] = None, timeout: int = 120,
                 model: Optional[str] = None, extra_headers: Optional[Dict[str, str]] = None):
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.timeout = timeout
        self.model = model
        self.extra_headers = extra_headers or {}

    def generate(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)

        payload = {
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.2),
            "top_p": kwargs.get("top_p", 0.9),
            "max_tokens": kwargs.get("max_new_tokens", 512),
        }
        model = kwargs.get("model", self.model)
        if model:  # required by Gemini / most OpenAI-compatible endpoints
            payload["model"] = model

        try:
            response = requests.post(self.endpoint_url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            # OpenAI compatible response format
            if "choices" in data and len(data["choices"]) > 0:
                choice = data["choices"][0]
                if "message" in choice and "content" in choice["message"]:
                    return choice["message"]["content"].strip()
                if "text" in choice:
                    return choice["text"].strip()

            # Direct response format
            if "response" in data:
                return str(data["response"]).strip()
            if "answer" in data:
                return str(data["answer"]).strip()

            return str(data).strip()
        except Exception as exc:
            raise RuntimeError(f"HTTP Inference request failed to {self.endpoint_url}: {exc}") from exc
