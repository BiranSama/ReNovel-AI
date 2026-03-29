import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.infrastructure.llm.gateway import LLMGateway, LLMGatewayError
from src.infrastructure.llm.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerConfig
from src.infrastructure.llm.rate_limiter import RateLimiter, RateLimitConfig
from src.shared.types import LLMConfig, LLMRequest, LLMResponse, Provider


class TestLLMGateway:
    @pytest.fixture
    def gateway(self):
        return LLMGateway()

    @pytest.fixture
    def sample_config(self):
        return LLMConfig(
            provider=Provider.OPENAI,
            model="gpt-4",
            api_key="test-key",
        )

    @pytest.fixture
    def sample_request(self, sample_config):
        return LLMRequest(
            messages=[{"role": "user", "content": "Hello"}],
            config=sample_config,
        )

    def test_init(self, gateway: LLMGateway):
        assert gateway._providers == {}
        assert gateway._rate_limiter is not None
        assert gateway._circuit_breaker is not None

    def test_get_provider_caches(self, gateway: LLMGateway, sample_config: LLMConfig):
        with patch.object(gateway, '_create_provider') as mock_create:
            mock_provider = MagicMock()
            mock_create.return_value = mock_provider
            
            provider1 = gateway.get_provider(sample_config)
            provider2 = gateway.get_provider(sample_config)
            
            assert provider1 is provider2
            mock_create.assert_called_once()

    def test_create_provider_openai(self, gateway: LLMGateway):
        config = LLMConfig(
            provider=Provider.OPENAI,
            model="gpt-4",
            api_key="test-key",
        )
        
        provider = gateway._create_provider(config)
        
        assert provider is not None

    def test_create_provider_google(self, gateway: LLMGateway):
        config = LLMConfig(
            provider=Provider.GOOGLE,
            model="gemini-pro",
            api_key="test-key",
        )
        
        provider = gateway._create_provider(config)
        
        assert provider is not None

    @pytest.mark.asyncio
    async def test_invoke_success(
        self,
        gateway: LLMGateway,
        sample_request: LLMRequest,
    ):
        mock_provider = MagicMock()
        mock_response = LLMResponse(
            content="Response content",
            usage={"total_tokens": 100},
            model="gpt-4",
            latency_ms=500,
            finish_reason="stop",
        )
        mock_provider.invoke = AsyncMock(return_value=mock_response)
        
        with patch.object(gateway, 'get_provider', return_value=mock_provider):
            response = await gateway.invoke(sample_request)
            
            assert response.content == "Response content"
            assert response.usage["total_tokens"] == 100

    @pytest.mark.asyncio
    async def test_invoke_records_failure_on_error(
        self,
        gateway: LLMGateway,
        sample_request: LLMRequest,
    ):
        mock_provider = MagicMock()
        mock_provider.invoke = AsyncMock(side_effect=Exception("API Error"))
        
        initial_failures = gateway._circuit_breaker._failure_count
        
        with patch.object(gateway, 'get_provider', return_value=mock_provider):
            with pytest.raises(LLMGatewayError):
                await gateway.invoke(sample_request)
            
            assert gateway._circuit_breaker._failure_count > initial_failures

    def test_get_stats(self, gateway: LLMGateway):
        stats = gateway.get_stats()
        
        assert "rate_limiter" in stats
        assert "circuit_breaker" in stats
        assert "cached_providers" in stats

    @pytest.mark.asyncio
    async def test_get_available_models(self, gateway: LLMGateway):
        mock_provider = MagicMock()
        mock_provider.get_available_models = AsyncMock(
            return_value=["gpt-4", "gpt-3.5-turbo"]
        )
        
        with patch.object(gateway, 'get_provider', return_value=mock_provider):
            models = await gateway.get_available_models("openai")
            
            assert "gpt-4" in models
            assert "gpt-3.5-turbo" in models

    @pytest.mark.asyncio
    async def test_get_available_models_invalid_provider(self, gateway: LLMGateway):
        models = await gateway.get_available_models("invalid_provider")
        
        assert models == []


class TestCircuitBreaker:
    @pytest.fixture
    def circuit_breaker(self):
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=30,
        )
        return CircuitBreaker(config=config)

    def test_initial_state(self, circuit_breaker: CircuitBreaker):
        assert circuit_breaker._state == CircuitState.CLOSED
        assert circuit_breaker._failure_count == 0

    @pytest.mark.asyncio
    async def test_can_execute_when_closed(self, circuit_breaker: CircuitBreaker):
        result = await circuit_breaker.can_execute()
        
        assert result is True

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self, circuit_breaker: CircuitBreaker):
        for _ in range(circuit_breaker.config.failure_threshold):
            await circuit_breaker.record_failure()
        
        assert circuit_breaker._state == CircuitState.OPEN

    def test_get_state(self, circuit_breaker: CircuitBreaker):
        assert circuit_breaker.get_state() == "closed"

    def test_get_stats(self, circuit_breaker: CircuitBreaker):
        stats = circuit_breaker.get_stats()
        
        assert "state" in stats
        assert "failure_count" in stats


class TestRateLimiter:
    @pytest.fixture
    def rate_limiter(self):
        config = RateLimitConfig(
            requests_per_minute=60,
            tokens_per_minute=10000,
        )
        return RateLimiter(config=config)

    def test_initial_state(self, rate_limiter: RateLimiter):
        assert rate_limiter.config.requests_per_minute == 60
        assert rate_limiter.config.tokens_per_minute == 10000

    def test_get_current_usage(self, rate_limiter: RateLimiter):
        usage = rate_limiter.get_current_usage()
        
        assert "requests_per_minute" in usage
        assert "tokens_per_minute" in usage
