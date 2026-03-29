import time
import httpx
from typing import AsyncIterator
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from .base import BaseProvider
from src.shared.types import LLMConfig, LLMResponse


class OpenAIProvider(BaseProvider):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._llm = self._create_llm()
    
    def _create_llm(self) -> ChatOpenAI:
        kwargs = {
            'model': self.config.model,
            'api_key': self.config.api_key,
            'base_url': self.config.base_url or 'https://api.openai.com/v1',
            'temperature': self.config.temperature,
            'max_tokens': self.config.max_tokens,
            'timeout': self.config.timeout,
            'streaming': True,
        }
        return ChatOpenAI(**kwargs)
    
    async def invoke(self, messages: list[dict]) -> LLMResponse:
        start_time = time.time()
        lc_messages = self._convert_messages(messages)
        
        response = await self._llm.ainvoke(lc_messages)
        
        latency_ms = (time.time() - start_time) * 1000
        
        return LLMResponse(
            content=response.content,
            usage=self._build_usage_dict(response),
            model=self.config.model,
            latency_ms=latency_ms,
            finish_reason=getattr(response, 'stop_reason', 'stop') or 'stop',
        )
    
    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        lc_messages = self._convert_messages(messages)
        
        async for chunk in self._llm.astream(lc_messages):
            if hasattr(chunk, 'content') and chunk.content:
                yield chunk.content
    
    async def get_available_models(self) -> list[str]:
        base_url = self.config.base_url or 'https://api.openai.com/v1'
        
        if base_url.endswith('/v1'):
            url = f"{base_url}/models"
        else:
            url = f"{base_url}/v1/models"
        
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        
        try:
            async with httpx.AsyncClient(trust_env=True, timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return [item['id'] for item in data.get('data', [])]
        except Exception:
            pass
        
        return []
    
    def _convert_messages(self, messages: list[dict]) -> list:
        result = []
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            
            if role == 'system':
                result.append(SystemMessage(content=content))
            elif role == 'assistant':
                result.append(AIMessage(content=content))
            else:
                result.append(HumanMessage(content=content))
        
        return result
