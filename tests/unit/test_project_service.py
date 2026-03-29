import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.services.project_service import ProjectService
from src.domain.entities import Project, Chapter
from src.shared.types import Result


@pytest.fixture
def mock_project_repo():
    repo = MagicMock()
    repo.save = AsyncMock()
    repo.find_by_id = AsyncMock(return_value=None)
    repo.find_all = AsyncMock(return_value=[])
    repo.exists = AsyncMock(return_value=False)
    repo.delete = AsyncMock()
    return repo


@pytest.fixture
def mock_chapter_repo():
    repo = MagicMock()
    repo.find_by_project = AsyncMock(return_value=[])
    repo.save = AsyncMock()
    repo.delete_by_project = AsyncMock()
    return repo


@pytest.fixture
def project_service(mock_project_repo, mock_chapter_repo):
    return ProjectService(
        project_repo=mock_project_repo,
        chapter_repo=mock_chapter_repo,
    )


@pytest.fixture
def sample_project():
    return Project(
        id="proj-001",
        title="测试小说",
        description="这是一个测试项目",
        settings={"model": "gpt-4"},
    )


@pytest.fixture
def sample_chapters():
    return [
        Chapter(id="chap-001", project_id="proj-001", title="第一章", order_index=1, content="内容1"),
        Chapter(id="chap-002", project_id="proj-001", title="第二章", order_index=2, content="内容2"),
    ]


class TestProjectService:
    @pytest.mark.asyncio
    async def test_create_project(self, project_service, mock_project_repo):
        mock_project_repo.save = AsyncMock(side_effect=lambda p: p)
        
        result = await project_service.create_project(
            title="新小说",
            description="测试描述",
        )
        
        assert result.is_ok()
        assert result.value.title == "新小说"
        assert result.value.description == "测试描述"
        assert result.value.id is not None
        mock_project_repo.save.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_project_success(self, project_service, mock_project_repo, sample_project):
        mock_project_repo.find_by_id.return_value = sample_project
        
        result = await project_service.get_project("proj-001")
        
        assert result.is_ok()
        assert result.value.title == "测试小说"
        mock_project_repo.find_by_id.assert_called_once_with("proj-001")
    
    @pytest.mark.asyncio
    async def test_get_project_not_found(self, project_service, mock_project_repo):
        mock_project_repo.find_by_id.return_value = None
        
        result = await project_service.get_project("nonexistent")
        
        assert result.is_err()
        assert "not found" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_list_projects(self, project_service, mock_project_repo, sample_project):
        mock_project_repo.find_all.return_value = [sample_project]
        
        result = await project_service.list_projects()
        
        assert result.is_ok()
        assert len(result.value) == 1
        assert result.value[0].title == "测试小说"
        mock_project_repo.find_all.assert_called_once_with(include_archived=False)
    
    @pytest.mark.asyncio
    async def test_list_projects_include_archived(self, project_service, mock_project_repo):
        await project_service.list_projects(include_archived=True)
        
        mock_project_repo.find_all.assert_called_once_with(include_archived=True)
    
    @pytest.mark.asyncio
    async def test_duplicate_project_success(
        self,
        project_service,
        mock_project_repo,
        mock_chapter_repo,
        sample_project,
        sample_chapters,
    ):
        mock_project_repo.find_by_id.return_value = sample_project
        mock_chapter_repo.find_by_project.return_value = sample_chapters
        mock_project_repo.save = AsyncMock(side_effect=lambda p: p)
        
        result = await project_service.duplicate_project("proj-001", suffix="(副本)")
        
        assert result.is_ok()
        assert "(副本)" in result.value.title
        mock_chapter_repo.save.assert_called()
    
    @pytest.mark.asyncio
    async def test_duplicate_project_not_found(self, project_service, mock_project_repo):
        mock_project_repo.find_by_id.return_value = None
        
        result = await project_service.duplicate_project("nonexistent")
        
        assert result.is_err()
        assert "not found" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_delete_project_success(self, project_service, mock_project_repo, mock_chapter_repo):
        mock_project_repo.exists.return_value = True
        
        result = await project_service.delete_project("proj-001")
        
        assert result.is_ok()
        mock_chapter_repo.delete_by_project.assert_called_once_with("proj-001")
        mock_project_repo.delete.assert_called_once_with("proj-001")
    
    @pytest.mark.asyncio
    async def test_delete_project_not_found(self, project_service, mock_project_repo):
        mock_project_repo.exists.return_value = False
        
        result = await project_service.delete_project("nonexistent")
        
        assert result.is_err()
        assert "not found" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_archive_project_success(self, project_service, mock_project_repo, sample_project):
        mock_project_repo.find_by_id.return_value = sample_project
        
        result = await project_service.archive_project("proj-001")
        
        assert result.is_ok()
        assert result.value.is_archived() is True
        mock_project_repo.save.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_archive_project_not_found(self, project_service, mock_project_repo):
        mock_project_repo.find_by_id.return_value = None
        
        result = await project_service.archive_project("nonexistent")
        
        assert result.is_err()
        assert "not found" in result.error.lower()
