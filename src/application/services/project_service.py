from typing import Optional
from src.domain.entities import Project, Chapter
from src.domain.repositories import ProjectRepository, ChapterRepository
from src.shared.types import Result
from src.shared.exceptions import NotFoundError


class ProjectService:
    def __init__(
        self,
        project_repo: ProjectRepository,
        chapter_repo: ChapterRepository
    ):
        self.project_repo = project_repo
        self.chapter_repo = chapter_repo
    
    async def create_project(
        self,
        title: str,
        description: str = ""
    ) -> Result[Project, str]:
        try:
            project = Project.create(title, description)
            saved = await self.project_repo.save(project)
            return Result.ok(saved)
        except Exception as e:
            return Result.err(f"创建项目失败: {e}")
    
    async def get_project(self, project_id: str) -> Result[Project, str]:
        project = await self.project_repo.find_by_id(project_id)
        if not project:
            return Result.err(f"Project {project_id} not found")
        return Result.ok(project)
    
    async def list_projects(
        self,
        include_archived: bool = False
    ) -> Result[list[Project], str]:
        try:
            projects = await self.project_repo.find_all(include_archived=include_archived)
            return Result.ok(projects)
        except Exception as e:
            return Result.err(f"获取项目列表失败: {e}")
    
    async def duplicate_project(
        self,
        project_id: str,
        suffix: str = "(副本)"
    ) -> Result[Project, str]:
        original = await self.project_repo.find_by_id(project_id)
        if not original:
            return Result.err(f"Project {project_id} not found")
        
        new_project = Project.create(
            title=f"{original.title} {suffix}",
            description=original.description
        )
        new_project.settings = original.settings.copy()
        await self.project_repo.save(new_project)
        
        chapters = await self.chapter_repo.find_by_project(project_id)
        for ch in chapters:
            new_chapter = Chapter.create(
                project_id=new_project.id,
                title=ch.title,
                order_index=ch.order_index,
                content=ch.content
            )
            await self.chapter_repo.save(new_chapter)
        
        return Result.ok(new_project)
    
    async def delete_project(self, project_id: str) -> Result[bool, str]:
        if not await self.project_repo.exists(project_id):
            return Result.err(f"Project {project_id} not found")
        
        await self.chapter_repo.delete_by_project(project_id)
        await self.project_repo.delete(project_id)
        return Result.ok(True)
    
    async def archive_project(self, project_id: str) -> Result[Project, str]:
        project = await self.project_repo.find_by_id(project_id)
        if not project:
            return Result.err(f"Project {project_id} not found")
        
        project.archive()
        await self.project_repo.save(project)
        return Result.ok(project)
