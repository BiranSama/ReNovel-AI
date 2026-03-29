import time
from typing import AsyncIterator
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from .base import BaseProvider
from src.shared.types import LLMConfig, LLMResponse


class GoogleProvider(BaseProvider):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._llm = self._create_llm()
    
    def _create_llm(self) -> ChatGoogleGenerativeAI:
        return ChatGoogleGenerativeAI(
            model=self.config.model,
            google_api_key=self.config.api_key,
            temperature=self.config.temperature,
            top_p=0.9,
            convert_system_message_to_human=True,
            transport='rest',
        )
    
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
        return [
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-2.0-flash",
            "gemini-2.0-pro",
        ]
    
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
