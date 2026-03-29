import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RateLimitConfig:
    requests_per_minute: int = 60
    tokens_per_minute: int = 90000
    burst_size: int = 10


class RateLimiter:
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self._request_timestamps: list[float] = []
        self._token_usage: list[tuple[float, int]] = []
        self._lock = asyncio.Lock()
    
    async def acquire(self, estimated_tokens: int = 1000) -> None:
        async with self._lock:
            now = time.time()
            window_start = now - 60.0
            
            self._request_timestamps = [
                ts for ts in self._request_timestamps if ts > window_start
            ]
            
            self._token_usage = [
                (ts, tokens) for ts, tokens in self._token_usage if ts > window_start
            ]
            
            current_requests = len(self._request_timestamps)
            current_tokens = sum(tokens for _, tokens in self._token_usage)
            
            if current_requests >= self.config.requests_per_minute:
                oldest = self._request_timestamps[0]
                wait_time = oldest + 60.0 - now + 0.1
                await asyncio.sleep(wait_time)
            
            if current_tokens + estimated_tokens > self.config.tokens_per_minute:
                oldest = self._token_usage[0][0]
                wait_time = oldest + 60.0 - now + 0.1
                await asyncio.sleep(wait_time)
            
            self._request_timestamps.append(time.time())
    
    def record_usage(self, tokens: int) -> None:
        self._token_usage.append((time.time(), tokens))
    
    def get_current_usage(self) -> dict:
        now = time.time()
        window_start = now - 60.0
        
        recent_requests = len([
            ts for ts in self._request_timestamps if ts > window_start
        ])
        
        recent_tokens = sum(
            tokens for ts, tokens in self._token_usage if ts > window_start
        )
        
        return {
            "requests_per_minute": recent_requests,
            "tokens_per_minute": recent_tokens,
            "limit_requests": self.config.requests_per_minute,
            "limit_tokens": self.config.tokens_per_minute,
        }
