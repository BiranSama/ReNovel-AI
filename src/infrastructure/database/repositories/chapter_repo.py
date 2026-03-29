import json
from datetime import datetime
from typing import Optional

from src.domain.entities import Chapter
from src.domain.repositories import ChapterRepository
from src.infrastructure.database.connection import Database, db


class SQLiteChapterRepository(ChapterRepository):
    def __init__(self, db: Database):
        self.db = db
    
    async def save(self, chapter: Chapter) -> Chapter:
        await self.db.execute("""
            INSERT OR REPLACE INTO chapters 
            (id, project_id, title, order_index, content, word_count, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            chapter.id,
            chapter.project_id,
            chapter.title,
            chapter.order_index,
            chapter.content,
            chapter.word_count,
            chapter.created_at.isoformat(),
            chapter.updated_at.isoformat(),
            json.dumps(chapter.metadata)
        ))
        return chapter
    
    async def find_by_id(self, chapter_id: str) -> Optional[Chapter]:
        row = await self.db.fetch_one(
            "SELECT * FROM chapters WHERE id = ?",
            (chapter_id,)
        )
        if row:
            return self._row_to_entity(row)
        return None
    
    async def find_by_project(
        self,
        project_id: str,
        include_content: bool = True
    ) -> list[Chapter]:
        if include_content:
            query = "SELECT * FROM chapters WHERE project_id = ? ORDER BY order_index ASC"
        else:
            query = "SELECT id, project_id, title, order_index, word_count, created_at, updated_at, metadata FROM chapters WHERE project_id = ? ORDER BY order_index ASC"
        
        rows = await self.db.fetch_all(query, (project_id,))
        return [self._row_to_entity(row) for row in rows]
    
    async def update_content(self, chapter_id: str, content: str) -> bool:
        await self.db.execute("""
            UPDATE chapters 
            SET content = ?, word_count = ?, updated_at = ?
            WHERE id = ?
        """, (
            content,
            len(content),
            datetime.now().isoformat(),
            chapter_id
        ))
        return True
    
    async def delete(self, chapter_id: str) -> bool:
        await self.db.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))
        return True
    
    async def delete_by_project(self, project_id: str) -> int:
        result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM chapters WHERE project_id = ?",
            (project_id,)
        )
        count = result["count"] if result else 0
        await self.db.execute("DELETE FROM chapters WHERE project_id = ?", (project_id,))
        return count
    
    async def count_by_project(self, project_id: str) -> int:
        result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM chapters WHERE project_id = ?",
            (project_id,)
        )
        return result["count"] if result else 0
    
    def _row_to_entity(self, row: dict) -> Chapter:
        return Chapter(
            id=row["id"],
            project_id=row["project_id"],
            title=row["title"],
            order_index=row["order_index"],
            content=row.get("content", ""),
            word_count=row.get("word_count", 0),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            metadata=json.loads(row["metadata"]) if row.get("metadata") else {}
        )
