from typing import Optional
from src.di.container import container
from src.application.services.project_service import ProjectService
from src.application.services.chapter_service import ChapterService
from src.shared.types import Result


class ProjectController:
    def __init__(self):
        self._project_service: Optional[ProjectService] = None
        self._chapter_service: Optional[ChapterService] = None
    
    @property
    def project_service(self) -> ProjectService:
        if self._project_service is None:
            self._project_service = container.project_service()
        return self._project_service
    
    @property
    def chapter_service(self) -> ChapterService:
        if self._chapter_service is None:
            self._chapter_service = container.chapter_service()
        return self._chapter_service
    
    async def init_database(self) -> None:
        from src.infrastructure.database.connection import db
        await db.init_tables()
    
    async def get_projects(self) -> Result[list[dict], str]:
        try:
            projects = await self.project_service.get_all_projects()
            return Result.ok([p.to_dict() for p in projects])
        except Exception as e:
            return Result.err(str(e))
    
    async def get_chapters(self, project_id: str) -> Result[list[dict], str]:
        try:
            chapters = await self.chapter_service.get_chapters_by_project(project_id)
            return Result.ok([c.to_dict() for c in chapters])
        except Exception as e:
            return Result.err(str(e))
    
    async def create_project(self, title: str) -> Result[dict, str]:
        try:
            project = await self.project_service.create_project(title)
            return Result.ok(project.to_dict())
        except Exception as e:
            return Result.err(str(e))
    
    async def import_novel(self, upload_event) -> Result[str, str]:
        try:
            content = upload_event.content.read().decode('utf-8')
            filename = upload_event.name
            
            project = await self.project_service.create_project(
                title=filename.replace('.txt', ''),
            )
            
            chapters = self._split_into_chapters(content)
            
            for i, chapter_content in enumerate(chapters, 1):
                await self.project_service.add_chapter(
                    project_id=project.id,
                    index=i,
                    title=f"第{i}章",
                    content=chapter_content,
                )
            
            return Result.ok(f"导入成功: {len(chapters)} 章")
        except Exception as e:
            return Result.err(str(e))
    
    def _split_into_chapters(self, content: str) -> list[str]:
        import re
        pattern = r'(第[一二三四五六七八九十百千\d]+章|Chapter\s*\d+)'
        parts = re.split(pattern, content, flags=re.IGNORECASE)
        
        if len(parts) <= 1:
            return [content]
        
        chapters = []
        for i in range(1, len(parts), 2):
            if i + 1 < len(parts):
                title = parts[i].strip()
                text = parts[i + 1].strip()
                chapters.append(f"{title}\n\n{text}")
        
        if not chapters:
            return [content]
        
        return chapters
