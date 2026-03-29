from typing import Optional, AsyncIterator
from src.di.container import container
from src.application.services.rewrite_service import RewriteService, RewriteRequest, RewriteMode
from src.application.services.chapter_service import ChapterService
from src.shared.types import Result


class EditorController:
    def __init__(self):
        self._rewrite_service: Optional[RewriteService] = None
        self._chapter_service: Optional[ChapterService] = None
    
    @property
    def rewrite_service(self) -> RewriteService:
        if self._rewrite_service is None:
            self._rewrite_service = container.rewrite_service()
        return self._rewrite_service
    
    @property
    def chapter_service(self) -> ChapterService:
        if self._chapter_service is None:
            self._chapter_service = container.chapter_service()
        return self._chapter_service
    
    async def rewrite_segment(
        self,
        project_id: str,
        chapter_id: str,
        chapter_index: int,
        original_text: str,
        instruction: str,
    ) -> Result:
        request = RewriteRequest(
            project_id=project_id or "default",
            chapter_id=chapter_id or "default",
            chapter_index=chapter_index or 1,
            original_text=original_text,
            instruction=instruction,
            mode=RewriteMode.POLISH,
        )
        
        return await self.rewrite_service.rewrite(request)
    
    async def stream_rewrite(
        self,
        project_id: str,
        chapter_id: str,
        chapter_index: int,
        original_text: str,
        instruction: str,
    ) -> AsyncIterator[str]:
        request = RewriteRequest(
            project_id=project_id or "default",
            chapter_id=chapter_id or "default",
            chapter_index=chapter_index or 1,
            original_text=original_text,
            instruction=instruction,
            mode=RewriteMode.POLISH,
        )
        
        async for chunk in self.rewrite_service.stream_rewrite(request):
            yield chunk
    
    async def save_chapter(self, chapter_id: str, content: str) -> Result:
        return await self.chapter_service.save_chapter_content(
            chapter_id=chapter_id,
            content=content,
            update_rag=True,
        )
    
    async def get_chapter_content(self, chapter_id: str) -> Result[str, str]:
        result = await self.chapter_service.get_chapter(chapter_id)
        if result.is_ok():
            return Result.ok(result.value.content)
        return Result.err(result.error)
    
    async def check_consistency(
        self,
        text: str,
        project_id: str,
        chapter_index: int,
    ):
        return await self.rewrite_service.check_consistency(
            text=text,
            project_id=project_id,
            chapter_index=chapter_index,
        )
