import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.services.chapter_service import ChapterService
from src.domain.entities import Chapter, Segment
from src.shared.types import Result


@pytest.fixture
def mock_chapter_repo():
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=None)
    repo.find_by_project = AsyncMock(return_value=[])
    repo.save = AsyncMock()
    repo.count_by_project = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_rag_pipeline():
    pipeline = MagicMock()
    pipeline.index = AsyncMock(return_value=5)
    return pipeline


@pytest.fixture
def mock_memory_repo():
    repo = MagicMock()
    repo.get_events_by_chapter = AsyncMock(return_value=[])
    repo.get_chapter_summary = AsyncMock(return_value=None)
    repo.delete_events_by_chapter = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def chapter_service(mock_chapter_repo, mock_rag_pipeline, mock_memory_repo):
    return ChapterService(
        chapter_repo=mock_chapter_repo,
        rag_pipeline=mock_rag_pipeline,
        memory_repo=mock_memory_repo,
    )


@pytest.fixture
def chapter_service_minimal(mock_chapter_repo):
    return ChapterService(
        chapter_repo=mock_chapter_repo,
        rag_pipeline=None,
        memory_repo=None,
    )


@pytest.fixture
def sample_chapter():
    return Chapter(
        id="chap-001",
        project_id="proj-001",
        title="第一章 初遇",
        order_index=1,
        content="张三走进咖啡馆，看到了李四。\n\n他们开始交谈。",
    )


class TestChapterService:
    @pytest.mark.asyncio
    async def test_get_chapter_success(self, chapter_service, mock_chapter_repo, sample_chapter):
        mock_chapter_repo.find_by_id.return_value = sample_chapter
        
        result = await chapter_service.get_chapter("chap-001")
        
        assert result.is_ok()
        assert result.value.title == "第一章 初遇"
        mock_chapter_repo.find_by_id.assert_called_once_with("chap-001")
    
    @pytest.mark.asyncio
    async def test_get_chapter_not_found(self, chapter_service, mock_chapter_repo):
        mock_chapter_repo.find_by_id.return_value = None
        
        result = await chapter_service.get_chapter("nonexistent")
        
        assert result.is_err()
        assert "not found" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_get_chapters_by_project(self, chapter_service, mock_chapter_repo, sample_chapter):
        mock_chapter_repo.find_by_project.return_value = [sample_chapter]
        
        chapters = await chapter_service.get_chapters_by_project("proj-001")
        
        assert len(chapters) == 1
        mock_chapter_repo.find_by_project.assert_called_once_with("proj-001")
    
    @pytest.mark.asyncio
    async def test_save_chapter_content_success(self, chapter_service, mock_chapter_repo, sample_chapter):
        mock_chapter_repo.find_by_id.return_value = sample_chapter
        mock_chapter_repo.save = AsyncMock(side_effect=lambda c: c)
        
        new_content = "新的章节内容"
        result = await chapter_service.save_chapter_content("chap-001", new_content)
        
        assert result.is_ok()
        assert result.value.content == new_content
    
    @pytest.mark.asyncio
    async def test_save_chapter_content_with_rag_update(self, chapter_service, mock_chapter_repo, sample_chapter, mock_rag_pipeline):
        mock_chapter_repo.find_by_id.return_value = sample_chapter
        mock_chapter_repo.save = AsyncMock(side_effect=lambda c: c)
        
        new_content = "新的章节内容"
        result = await chapter_service.save_chapter_content("chap-001", new_content, update_rag=True)
        
        assert result.is_ok()
        mock_rag_pipeline.index.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_save_chapter_content_without_rag_update(self, chapter_service, mock_chapter_repo, sample_chapter, mock_rag_pipeline):
        mock_chapter_repo.find_by_id.return_value = sample_chapter
        mock_chapter_repo.save = AsyncMock(side_effect=lambda c: c)
        
        new_content = "新的章节内容"
        result = await chapter_service.save_chapter_content("chap-001", new_content, update_rag=False)
        
        assert result.is_ok()
        mock_rag_pipeline.index.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_save_chapter_content_not_found(self, chapter_service, mock_chapter_repo):
        mock_chapter_repo.find_by_id.return_value = None
        
        result = await chapter_service.save_chapter_content("nonexistent", "内容")
        
        assert result.is_err()
    
    @pytest.mark.asyncio
    async def test_split_to_segments_success(self, chapter_service, mock_chapter_repo, sample_chapter):
        mock_chapter_repo.find_by_id.return_value = sample_chapter
        
        result = await chapter_service.split_to_segments("chap-001")
        
        assert result.is_ok()
        segments = result.value
        assert len(segments) == 2
        assert all(isinstance(s, Segment) for s in segments)
    
    @pytest.mark.asyncio
    async def test_split_to_segments_empty_content(self, chapter_service, mock_chapter_repo):
        empty_chapter = Chapter(
            id="chap-002",
            project_id="proj-001",
            title="空章节",
            order_index=2,
            content="",
        )
        mock_chapter_repo.find_by_id.return_value = empty_chapter
        
        result = await chapter_service.split_to_segments("chap-002")
        
        assert result.is_ok()
        assert len(result.value) == 0
    
    @pytest.mark.asyncio
    async def test_split_to_segments_not_found(self, chapter_service, mock_chapter_repo):
        mock_chapter_repo.find_by_id.return_value = None
        
        result = await chapter_service.split_to_segments("nonexistent")
        
        assert result.is_err()
    
    @pytest.mark.asyncio
    async def test_merge_segments(self, chapter_service):
        segments = [
            Segment(id="seg-001", chapter_id="chap-001", original="第一段", order_index=0, revised="修订第一段"),
            Segment(id="seg-002", chapter_id="chap-001", original="第二段", order_index=1),
            Segment(id="seg-003", chapter_id="chap-001", original="第三段", order_index=2, revised=""),
        ]
        
        merged = await chapter_service.merge_segments(segments)
        
        assert "修订第一段" in merged
        assert "第二段" in merged
    
    @pytest.mark.asyncio
    async def test_get_chapter_count(self, chapter_service, mock_chapter_repo):
        mock_chapter_repo.count_by_project.return_value = 5
        
        count = await chapter_service.get_chapter_count("proj-001")
        
        assert count == 5
        mock_chapter_repo.count_by_project.assert_called_once_with("proj-001")
    
    @pytest.mark.asyncio
    async def test_get_chapter_with_context(
        self,
        chapter_service,
        mock_chapter_repo,
        mock_memory_repo,
        sample_chapter,
    ):
        mock_chapter_repo.find_by_id.return_value = sample_chapter
        mock_memory_repo.get_events_by_chapter.return_value = ["event1"]
        mock_memory_repo.get_chapter_summary.return_value = {"summary": "摘要"}
        
        result = await chapter_service.get_chapter_with_context(
            "chap-001",
            include_events=True,
            include_summary=True,
        )
        
        assert result.is_ok()
        data = result.value
        assert data["chapter"] == sample_chapter
        assert data["events"] == ["event1"]
        assert data["summary"] == {"summary": "摘要"}
    
    @pytest.mark.asyncio
    async def test_get_chapter_with_context_no_memory_repo(self, chapter_service_minimal, mock_chapter_repo, sample_chapter):
        mock_chapter_repo.find_by_id.return_value = sample_chapter
        
        result = await chapter_service_minimal.get_chapter_with_context(
            "chap-001",
            include_events=True,
            include_summary=True,
        )
        
        assert result.is_ok()
        data = result.value
        assert data["events"] == []
        assert data["summary"] is None
    
    @pytest.mark.asyncio
    async def test_delete_chapter_memory_success(self, chapter_service, mock_memory_repo):
        mock_memory_repo.delete_events_by_chapter.return_value = 3
        
        result = await chapter_service.delete_chapter_memory("chap-001")
        
        assert result.is_ok()
        assert result.value == 3
    
    @pytest.mark.asyncio
    async def test_delete_chapter_memory_no_repo(self, chapter_service_minimal):
        result = await chapter_service_minimal.delete_chapter_memory("chap-001")
        
        assert result.is_err()
        assert "not configured" in result.error.lower()
