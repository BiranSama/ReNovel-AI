from typing import Optional, Protocol
from src.domain.entities import Chapter, Segment
from src.shared.types import Result


class ChapterRepositoryProtocol(Protocol):
    async def find_by_id(self, chapter_id: str) -> Optional[Chapter]: ...
    async def find_by_project(self, project_id: str) -> list[Chapter]: ...
    async def save(self, chapter: Chapter) -> Chapter: ...
    async def count_by_project(self, project_id: str) -> int: ...


class MemoryRepositoryProtocol(Protocol):
    async def get_events_by_chapter(self, chapter_id: str) -> list: ...
    async def get_chapter_summary(self, chapter_id: str) -> Optional[dict]: ...
    async def delete_events_by_chapter(self, chapter_id: str) -> int: ...


class RAGPipelineProtocol(Protocol):
    async def index(self, project_id: str, chapter_id: str, text: str) -> int: ...


class ChapterService:
    def __init__(
        self,
        chapter_repo: ChapterRepositoryProtocol,
        rag_pipeline: Optional[RAGPipelineProtocol] = None,
        memory_repo: Optional[MemoryRepositoryProtocol] = None,
    ):
        self.chapter_repo = chapter_repo
        self.rag_pipeline = rag_pipeline
        self.memory_repo = memory_repo
    
    async def get_chapter(self, chapter_id: str) -> Result[Chapter, str]:
        chapter = await self.chapter_repo.find_by_id(chapter_id)
        if not chapter:
            return Result.err(f"Chapter {chapter_id} not found")
        return Result.ok(chapter)
    
    async def get_chapters_by_project(self, project_id: str) -> list[Chapter]:
        return await self.chapter_repo.find_by_project(project_id)
    
    async def save_chapter_content(
        self,
        chapter_id: str,
        content: str,
        update_rag: bool = True
    ) -> Result[Chapter, str]:
        chapter = await self.chapter_repo.find_by_id(chapter_id)
        if not chapter:
            return Result.err(f"Chapter {chapter_id} not found")
        
        chapter.update_content(content)
        await self.chapter_repo.save(chapter)
        
        if update_rag and self.rag_pipeline:
            await self.rag_pipeline.index(
                chapter.project_id,
                chapter_id,
                content
            )
        
        return Result.ok(chapter)
    
    async def split_to_segments(self, chapter_id: str) -> Result[list[Segment], str]:
        chapter = await self.chapter_repo.find_by_id(chapter_id)
        if not chapter:
            return Result.err(f"Chapter {chapter_id} not found")
        
        segments = self._text_to_segments(chapter_id, chapter.content)
        return Result.ok(segments)
    
    async def merge_segments(self, segments: list[Segment]) -> str:
        lines = []
        for seg in segments:
            content = seg.revised if seg.revised else seg.original
            if content.strip():
                lines.append(content)
        return "\n\n".join(lines)
    
    def _text_to_segments(self, chapter_id: str, text: str) -> list[Segment]:
        if not text:
            return []
        
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return [
            Segment.create(chapter_id=chapter_id, original=line, order_index=i)
            for i, line in enumerate(lines)
        ]
    
    async def get_chapter_count(self, project_id: str) -> int:
        return await self.chapter_repo.count_by_project(project_id)
    
    async def get_chapter_with_context(
        self,
        chapter_id: str,
        include_events: bool = True,
        include_summary: bool = True,
    ) -> Result[dict, str]:
        chapter = await self.chapter_repo.find_by_id(chapter_id)
        if not chapter:
            return Result.err(f"Chapter {chapter_id} not found")
        
        result = {
            "chapter": chapter,
            "events": [],
            "summary": None,
        }
        
        if include_events and self.memory_repo:
            result["events"] = await self.memory_repo.get_events_by_chapter(chapter_id)
        
        if include_summary and self.memory_repo:
            result["summary"] = await self.memory_repo.get_chapter_summary(chapter_id)
        
        return Result.ok(result)
    
    async def delete_chapter_memory(self, chapter_id: str) -> Result[int, str]:
        if not self.memory_repo:
            return Result.err("Memory repository not configured")
        count = await self.memory_repo.delete_events_by_chapter(chapter_id)
        return Result.ok(count)
