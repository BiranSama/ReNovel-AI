import time
from typing import AsyncIterator, Optional
from dataclasses import dataclass

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.shared.types import LLMConfig, LLMRequest, LLMResponse, Provider
from src.infrastructure.llm.protocols import LLMGateway as LLMGatewayProtocol
from src.infrastructure.llm.providers.base import BaseProvider
from src.infrastructure.llm.providers.openai_provider import OpenAIProvider
from src.infrastructure.llm.providers.google_provider import GoogleProvider
from src.infrastructure.llm.rate_limiter import RateLimiter
from src.infrastructure.llm.circuit_breaker import CircuitBreaker
from src.infrastructure.llm.token_counter import TokenCounter


class LLMGatewayError(Exception):
    pass


class RateLimitExceededError(LLMGatewayError):
    pass


class CircuitOpenError(LLMGatewayError):
    pass


class TransientError(LLMGatewayError):
    pass


RETRY_CONFIG = {
    "stop": stop_after_attempt(3),
    "wait": wait_exponential(multiplier=1, min=1, max=10),
    "retry": retry_if_exception_type(TransientError),
    "reraise": True,
}


class LLMGateway(LLMGatewayProtocol):
    def __init__(
        self,
        rate_limiter: Optional[RateLimiter] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        token_counter: Optional[TokenCounter] = None,
    ):
        self._providers: dict[str, BaseProvider] = {}
        self._rate_limiter = rate_limiter or RateLimiter()
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._token_counter = token_counter or TokenCounter()
    
    def get_provider(self, config: LLMConfig) -> BaseProvider:
        cache_key = f"{config.provider.value}:{config.model}"
        
        if cache_key not in self._providers:
            self._providers[cache_key] = self._create_provider(config)
        
        return self._providers[cache_key]
    
    def _create_provider(self, config: LLMConfig) -> BaseProvider:
        if config.provider == Provider.OPENAI:
            return OpenAIProvider(config)
        elif config.provider == Provider.GOOGLE:
            return GoogleProvider(config)
        else:
            raise ValueError(f"Unsupported provider: {config.provider}")
    
    @retry(**RETRY_CONFIG)
    async def invoke(self, request: LLMRequest) -> LLMResponse:
        estimated_tokens = self._token_counter.count_messages_tokens(request.messages)
        
        await self._rate_limiter.acquire(estimated_tokens)
        
        if not await self._circuit_breaker.can_execute():
            raise CircuitOpenError(
                f"Circuit breaker is open. State: {self._circuit_breaker.get_state()}"
            )
        
        provider = self.get_provider(request.config)
        
        try:
            response = await provider.invoke(request.messages)
            await self._circuit_breaker.record_success()
            self._rate_limiter.record_usage(response.usage.get('total_tokens', 0))
            return response
        except CircuitOpenError:
            raise
        except Exception as e:
            await self._circuit_breaker.record_failure()
            error_str = str(e).lower()
            if "timeout" in error_str or "connection" in error_str or "rate" in error_str:
                raise TransientError(f"Transient error: {e}") from e
            raise LLMGatewayError(f"LLM invocation failed: {e}") from e
    
    @retry(**RETRY_CONFIG)
    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        estimated_tokens = self._token_counter.count_messages_tokens(request.messages)
        
        await self._rate_limiter.acquire(estimated_tokens)
        
        if not await self._circuit_breaker.can_execute():
            raise CircuitOpenError(
                f"Circuit breaker is open. State: {self._circuit_breaker.get_state()}"
            )
        
        provider = self.get_provider(request.config)
        
        try:
            total_tokens = 0
            async for chunk in provider.stream(request.messages):
                total_tokens += self._token_counter.count_tokens(chunk)
                yield chunk
            
            await self._circuit_breaker.record_success()
            self._rate_limiter.record_usage(total_tokens)
        except CircuitOpenError:
            raise
        except Exception as e:
            await self._circuit_breaker.record_failure()
            error_str = str(e).lower()
            if "timeout" in error_str or "connection" in error_str or "rate" in error_str:
                raise TransientError(f"Transient error: {e}") from e
            raise LLMGatewayError(f"LLM streaming failed: {e}") from e
    
    async def get_available_models(self, provider: str) -> list[str]:
        try:
            provider_enum = Provider(provider)
        except ValueError:
            return []
        
        dummy_config = LLMConfig(
            provider=provider_enum,
            model="",
            api_key="",
        )
        
        try:
            prov = self.get_provider(dummy_config)
            return await prov.get_available_models()
        except Exception:
            return []
    
    def get_stats(self) -> dict:
        return {
            "rate_limiter": self._rate_limiter.get_current_usage(),
            "circuit_breaker": self._circuit_breaker.get_stats(),
            "cached_providers": list(self._providers.keys()),
        }
