from typing import Protocol, AsyncIterator, runtime_checkable

from src.shared.types import LLMRequest, LLMResponse


@runtime_checkable
class LLMGateway(Protocol):
    async def invoke(self, request: LLMRequest) -> LLMResponse:
        ...
    
    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        ...
    
    async def get_available_models(self, provider: str) -> list[str]:
        ...


@runtime_checkable
class RateLimiter(Protocol):
    async def acquire(self, estimated_tokens: int = 1000) -> None:
        ...
    
    def get_current_usage(self) -> dict:
        ...


@runtime_checkable
class CircuitBreaker(Protocol):
    async def can_execute(self) -> bool:
        ...
    
    async def record_success(self) -> None:
        ...
    
    async def record_failure(self) -> None:
        ...
    
    def get_state(self) -> str:
        ...
