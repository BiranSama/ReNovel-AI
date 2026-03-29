import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.rag.pipeline import RAGPipeline
from src.shared.types import Chunk, RetrievalResult


@pytest.fixture
def mock_embedder():
    embedder = MagicMock()
    embedder.embed = MagicMock(return_value=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    embedder.embed_query = MagicMock(return_value=[0.1, 0.2, 0.3])
    return embedder


@pytest.fixture
def mock_chunker():
    chunker = MagicMock()
    chunker.chunk = MagicMock(return_value=[
        Chunk(id="chunk-1", content="测试内容1", metadata={"project_id": "proj-001"}),
        Chunk(id="chunk-2", content="测试内容2", metadata={"project_id": "proj-001"}),
    ])
    return chunker


@pytest.fixture
def mock_vector_store():
    store = MagicMock()
    store.upsert = AsyncMock(return_value=2)
    store.query = AsyncMock(return_value=(
        [Chunk(id="chunk-1", content="相关内容", metadata={})],
        [0.9],
    ))
    store.delete = AsyncMock(return_value=5)
    store.get_by_project = AsyncMock(return_value=[])
    return store


@pytest.fixture
def rag_pipeline(mock_embedder, mock_chunker, mock_vector_store):
    return RAGPipeline(
        embedder=mock_embedder,
        chunker=mock_chunker,
        vector_store=mock_vector_store,
    )


class TestRAGPipeline:
    @pytest.mark.asyncio
    async def test_index_success(self, rag_pipeline, mock_chunker, mock_embedder, mock_vector_store):
        count = await rag_pipeline.index(
            project_id="proj-001",
            chapter_id="chap-001",
            text="这是一段测试文本。",
        )
        
        assert count == 2
        mock_chunker.chunk.assert_called_once()
        mock_embedder.embed.assert_called_once()
        mock_vector_store.upsert.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_index_empty_text(self, rag_pipeline, mock_chunker, mock_vector_store):
        count = await rag_pipeline.index(
            project_id="proj-001",
            chapter_id="chap-001",
            text="",
        )
        
        assert count == 0
        mock_chunker.chunk.assert_not_called()
        mock_vector_store.upsert.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_index_whitespace_text(self, rag_pipeline, mock_chunker, mock_vector_store):
        count = await rag_pipeline.index(
            project_id="proj-001",
            chapter_id="chap-001",
            text="   \n\t  ",
        )
        
        assert count == 0
    
    @pytest.mark.asyncio
    async def test_index_no_chunks(self, rag_pipeline, mock_chunker, mock_vector_store):
        mock_chunker.chunk.return_value = []
        
        count = await rag_pipeline.index(
            project_id="proj-001",
            chapter_id="chap-001",
            text="文本",
        )
        
        assert count == 0
        mock_vector_store.upsert.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_retrieve_success(self, rag_pipeline, mock_embedder, mock_vector_store):
        result = await rag_pipeline.retrieve(
            query="测试查询",
            project_id="proj-001",
            top_k=5,
        )
        
        assert isinstance(result, RetrievalResult)
        assert len(result.chunks) == 1
        assert result.query == "测试查询"
        mock_embedder.embed_query.assert_called_once_with("测试查询")
        mock_vector_store.query.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_retrieve_with_reranker(self, rag_pipeline, mock_vector_store):
        mock_vector_store.query.return_value = (
            [
                Chunk(id="c1", content="测试内容查询相关", metadata={}),
                Chunk(id="c2", content="其他内容", metadata={}),
            ],
            [0.8, 0.7],
        )
        
        result = await rag_pipeline.retrieve(
            query="查询",
            project_id="proj-001",
            top_k=5,
            use_reranker=True,
        )
        
        assert len(result.chunks) == 2
    
    @pytest.mark.asyncio
    async def test_retrieve_without_reranker(self, rag_pipeline, mock_vector_store):
        await rag_pipeline.retrieve(
            query="测试查询",
            project_id="proj-001",
            top_k=5,
            use_reranker=False,
        )
        
        mock_vector_store.query.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_delete_project(self, rag_pipeline, mock_vector_store):
        count = await rag_pipeline.delete_project("proj-001")
        
        assert count == 5
        mock_vector_store.delete.assert_called_once_with(where={"project_id": "proj-001"})
    
    @pytest.mark.asyncio
    async def test_format_context_empty(self, rag_pipeline):
        result = RetrievalResult(chunks=[], scores=[], query="test", total_tokens=0)
        
        context = rag_pipeline.format_context(result)
        
        assert context == ""
    
    @pytest.mark.asyncio
    async def test_format_context_with_chunks(self, rag_pipeline):
        chunks = [
            Chunk(id="c1", content="第一段内容", metadata={}),
            Chunk(id="c2", content="第二段内容", metadata={}),
        ]
        result = RetrievalResult(chunks=chunks, scores=[0.9, 0.8], query="test", total_tokens=0)
        
        context = rag_pipeline.format_context(result, max_tokens=1000)
        
        assert "第一段内容" in context
        assert "第二段内容" in context
        assert "RAG" in context
    
    @pytest.mark.asyncio
    async def test_format_context_respects_max_tokens(self, rag_pipeline):
        chunks = [
            Chunk(id="c1", content="A" * 1000, metadata={}),
            Chunk(id="c2", content="B" * 1000, metadata={}),
        ]
        result = RetrievalResult(chunks=chunks, scores=[0.9, 0.8], query="test", total_tokens=0)
        
        context = rag_pipeline.format_context(result, max_tokens=500)
        
        assert len(context) < 3000
    
    @pytest.mark.asyncio
    async def test_clone_project_memory(self, rag_pipeline, mock_vector_store, mock_embedder):
        mock_vector_store.get_by_project.return_value = [
            Chunk(
                id="old-chunk-1",
                content="内容1",
                metadata={"project_id": "old-proj"},
                embedding=[0.1, 0.2],
            ),
        ]
        mock_vector_store.upsert = AsyncMock(return_value=1)
        
        count = await rag_pipeline.clone_project_memory("old-proj", "new-proj")
        
        assert count == 1
        mock_vector_store.get_by_project.assert_called_once_with("old-proj")
    
    @pytest.mark.asyncio
    async def test_clone_project_memory_empty(self, rag_pipeline, mock_vector_store):
        mock_vector_store.get_by_project.return_value = []
        
        count = await rag_pipeline.clone_project_memory("old-proj", "new-proj")
        
        assert count == 0
