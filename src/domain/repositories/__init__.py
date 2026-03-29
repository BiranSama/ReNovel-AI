from typing import Protocol, Optional, runtime_checkable

from src.domain.entities.project import Project
from src.domain.entities.chapter import Chapter


@runtime_checkable
class ProjectRepository(Protocol):
    async def save(self, project: Project) -> Project:
        ...
    
    async def find_by_id(self, project_id: str) -> Optional[Project]:
        ...
    
    async def find_all(
        self,
        limit: int = 100,
        offset: int = 0,
        include_archived: bool = False
    ) -> list[Project]:
        ...
    
    async def delete(self, project_id: str) -> bool:
        ...
    
    async def exists(self, project_id: str) -> bool:
        ...


@runtime_checkable
class ChapterRepository(Protocol):
    async def save(self, chapter: Chapter) -> Chapter:
        ...
    
    async def find_by_id(self, chapter_id: str) -> Optional[Chapter]:
        ...
    
    async def find_by_project(
        self,
        project_id: str,
        include_content: bool = True
    ) -> list[Chapter]:
        ...
    
    async def update_content(self, chapter_id: str, content: str) -> bool:
        ...
    
    async def delete(self, chapter_id: str) -> bool:
        ...
    
    async def delete_by_project(self, project_id: str) -> int:
        ...
    
    async def count_by_project(self, project_id: str) -> int:
        ...
