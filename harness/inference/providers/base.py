"""Base class for Inference Providers."""
from abc import ABC, abstractmethod
from typing import Dict, List, Any


class BaseInferenceProvider(ABC):
    """Abstract interface for model inference providers."""

    @abstractmethod
    def generate(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        """Generates text from a list of standard prompt messages."""
        pass
