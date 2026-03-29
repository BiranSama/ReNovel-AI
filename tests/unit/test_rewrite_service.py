import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.services.rewrite_service import (
    RewriteService,
    RewriteRequest,
    RewriteResult,
    RewriteMode,
)
from src.infrastructure.memory import ConsistencyReport, ConsistencyIssue
from src.shared.types import Result, LLMResponse


class TestRewriteService:
    @pytest.fixture
    def mock_llm_gateway(self, sample_llm_response):
        gateway = MagicMock()
        gateway.invoke = AsyncMock(return_value=sample_llm_response)
        gateway.stream = AsyncMock(return_value=iter(["chunk1", "chunk2"]))
        return gateway
    
    @pytest.fixture
    def mock_rag_pipeline(self):
        pipeline = MagicMock()
        pipeline.index = AsyncMock(return_value=5)
        pipeline.retrieve = AsyncMock(return_value=MagicMock(
            chunks=[],
            scores=[],
            query="test",
            total_tokens=0,
        ))
        return pipeline
    
    @pytest.fixture
    def mock_event_extractor(self):
        extractor = MagicMock()
        extractor.extract = AsyncMock(return_value=MagicMock(
            events=[],
            character_states=[],
            chapter_summary=None,
        ))
        return extractor
    
    @pytest.fixture
    def mock_consistency_checker(self):
        checker = MagicMock()
        checker.check = AsyncMock(return_value=ConsistencyReport(
            is_consistent=True,
            issues=[],
            summary="No issues",
        ))
        return checker
    
    @pytest.fixture
    def mock_context_builder(self):
        builder = MagicMock()
        
        class MockContext:
            def build_prompt(self):
                return "test prompt"
        
        builder.build = AsyncMock(return_value=MockContext())
        return builder
    
    @pytest.fixture
    def mock_memory_repo(self):
        repo = MagicMock()
        repo.get_events_before_chapter = AsyncMock(return_value=[])
        repo.get_events_after_chapter = AsyncMock(return_value=[])
        repo.get_latest_character_states = AsyncMock(return_value=[])
        repo.save_plot_events = AsyncMock()
        repo.save_character_states = AsyncMock()
        repo.save_chapter_summary = AsyncMock()
        return repo
    
    @pytest.fixture
    def mock_character_repo(self):
        repo = MagicMock()
        repo.get_characters = AsyncMock(return_value=[])
        return repo
    
    @pytest.fixture
    def rewrite_service(
        self,
        mock_llm_gateway,
        sample_llm_config,
        mock_rag_pipeline,
        mock_event_extractor,
        mock_consistency_checker,
        mock_context_builder,
        mock_memory_repo,
        mock_character_repo,
    ):
        return RewriteService(
            llm_gateway=mock_llm_gateway,
            llm_config=sample_llm_config,
            rag_pipeline=mock_rag_pipeline,
            event_extractor=mock_event_extractor,
            consistency_checker=mock_consistency_checker,
            context_builder=mock_context_builder,
            memory_repo=mock_memory_repo,
            character_repo=mock_character_repo,
        )

    @pytest.mark.asyncio
    async def test_rewrite_returns_ok_result(
        self,
        rewrite_service: RewriteService,
    ):
        request = RewriteRequest(
            project_id="proj-001",
            chapter_id="chap-001",
            chapter_index=1,
            original_text="原文内容",
            instruction="润色",
        )
        
        result = await rewrite_service.rewrite(request)
        
        assert result.is_ok()
        assert result.value is not None
        assert isinstance(result.value, RewriteResult)

    @pytest.mark.asyncio
    async def test_rewrite_handles_llm_error(
        self,
        sample_llm_config,
        mock_rag_pipeline,
        mock_event_extractor,
        mock_consistency_checker,
        mock_context_builder,
        mock_memory_repo,
        mock_character_repo,
    ):
        failing_gateway = MagicMock()
        failing_gateway.invoke = AsyncMock(side_effect=Exception("API Error"))
        
        service = RewriteService(
            llm_gateway=failing_gateway,
            llm_config=sample_llm_config,
            rag_pipeline=mock_rag_pipeline,
            event_extractor=mock_event_extractor,
            consistency_checker=mock_consistency_checker,
            context_builder=mock_context_builder,
            memory_repo=mock_memory_repo,
            character_repo=mock_character_repo,
        )
        
        request = RewriteRequest(
            project_id="proj-001",
            chapter_id="chap-001",
            chapter_index=1,
            original_text="原文",
            instruction="润色",
        )
        
        result = await service.rewrite(request)
        
        assert result.is_err()
        assert "LLM 调用失败" in result.error


class TestRewriteRequest:
    def test_default_values(self):
        request = RewriteRequest(
            project_id="proj-001",
            chapter_id="chap-001",
            chapter_index=1,
            original_text="原文",
            instruction="润色",
        )
        
        assert request.mode == RewriteMode.POLISH
        assert request.enable_consistency_check is True
        assert request.enable_memory_extraction is True

    def test_custom_values(self):
        request = RewriteRequest(
            project_id="proj-001",
            chapter_id="chap-001",
            chapter_index=1,
            original_text="原文",
            instruction="续写",
            mode=RewriteMode.CONTINUE,
            enable_consistency_check=False,
            enable_memory_extraction=False,
        )
        
        assert request.mode == RewriteMode.CONTINUE
        assert request.enable_consistency_check is False


class TestRewriteResult:
    def test_result_creation(self):
        result = RewriteResult(
            rewritten_text="改写后的文本",
            original_text="原文",
            instruction="润色",
            tokens_used=100,
        )
        
        assert result.rewritten_text == "改写后的文本"
        assert result.consistency_report is None
        assert result.extraction_result is None
