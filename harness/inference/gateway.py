"""Inference Gateway component.

Hard boundary between the harness and inference model serving layers.
Instantiates and routes requests to configured inference providers (HTTP, Local, Mock).
"""
from typing import Any, Dict, List, Optional
from configs.settings import settings
from .providers.base import BaseInferenceProvider
from .providers.http_provider import HttpInferenceProvider
from .providers.local_qwen import LocalQwenInferenceProvider
from .providers.mock_provider import MockInferenceProvider


class InferenceGateway:
    """Gateway orchestrating model generation requests across pluggable backend providers."""

    def __init__(self, provider: Optional[BaseInferenceProvider] = None):
        if provider is not None:
            self.provider = provider
        elif settings.INFERENCE_PROVIDER == "gemini":
            self.provider = HttpInferenceProvider(
                endpoint_url=settings.GEMINI_API_URL,
                api_key=settings.INFERENCE_API_KEY,
                timeout=settings.INFERENCE_TIMEOUT,
                model=settings.GEMINI_MODEL,
            )
        elif settings.INFERENCE_PROVIDER == "openrouter":
            self.provider = HttpInferenceProvider(
                endpoint_url=settings.OPENROUTER_API_URL,
                api_key=settings.INFERENCE_API_KEY,
                timeout=settings.INFERENCE_TIMEOUT,
                model=settings.OPENROUTER_MODEL,
                extra_headers={
                    "HTTP-Referer": settings.OPENROUTER_SITE_URL,
                    "X-Title": settings.OPENROUTER_APP_NAME,
                },
            )
        elif settings.INFERENCE_PROVIDER == "http":
            self.provider = HttpInferenceProvider(
                endpoint_url=settings.INFERENCE_HTTP_URL,
                api_key=settings.INFERENCE_API_KEY,
                timeout=settings.INFERENCE_TIMEOUT,
            )
        elif settings.INFERENCE_PROVIDER == "local_qwen":
            self.provider = LocalQwenInferenceProvider(
                model_id=settings.QWEN_MODEL_ID,
                adapter_path=settings.ADAPTER_PATH or None,
                use_4bit=settings.USE_4BIT,
            )
        else:
            self.provider = MockInferenceProvider()

    def generate_response(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        return self.provider.generate(messages, **kwargs)

    @staticmethod
    def llm_enabled() -> bool:
        """True when a real model is configured (anything but mock). Callers
        must still catch failures and fall back to deterministic behavior."""
        return settings.INFERENCE_PROVIDER in ("gemini", "openrouter", "http", "local_qwen")
