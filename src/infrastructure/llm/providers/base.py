from abc import ABC, abstractmethod
from typing import AsyncIterator
from src.shared.types import LLMConfig, LLMResponse


class BaseProvider(ABC):
    def __init__(self, config: LLMConfig):
        self.config = config
        self._apply_proxy()
    
    def _apply_proxy(self) -> None:
        import os
        proxy = self.config.proxy
        if proxy and proxy.strip():
            os.environ['http_proxy'] = proxy
            os.environ['https_proxy'] = proxy
            os.environ['HTTP_PROXY'] = proxy
            os.environ['HTTPS_PROXY'] = proxy
    
    @abstractmethod
    async def invoke(self, messages: list[dict]) -> LLMResponse:
        ...
    
    @abstractmethod
    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        ...
    
    @abstractmethod
    async def get_available_models(self) -> list[str]:
        ...
    
    def _build_usage_dict(self, response) -> dict:
        usage = getattr(response, 'usage_metadata', None) or getattr(response, 'usage', None)
        if usage is None:
            return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        
        return {
            "prompt_tokens": getattr(usage, 'prompt_tokens', 0) or 0,
            "completion_tokens": getattr(usage, 'completion_tokens', 0) or 0,
            "total_tokens": getattr(usage, 'total_tokens', 0) or 0,
        }
