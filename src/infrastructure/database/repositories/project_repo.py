import json
from datetime import datetime
from typing import Optional

from src.domain.entities import Project
from src.domain.repositories import ProjectRepository
from src.shared.types import ProjectStatus
from src.infrastructure.database.connection import Database, db


class SQLiteProjectRepository(ProjectRepository):
    def __init__(self, db: Database):
        self.db = db
    
    async def save(self, project: Project) -> Project:
        await self.db.execute("""
            INSERT OR REPLACE INTO projects 
            (id, title, description, status, created_at, updated_at, settings)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            project.id,
            project.title,
            project.description,
            project.status.value,
            project.created_at.isoformat(),
            project.updated_at.isoformat(),
            json.dumps(project.settings)
        ))
        return project
    
    async def find_by_id(self, project_id: str) -> Optional[Project]:
        row = await self.db.fetch_one(
            "SELECT * FROM projects WHERE id = ?",
            (project_id,)
        )
        if row:
            return self._row_to_entity(row)
        return None
    
    async def find_all(
        self,
        limit: int = 100,
        offset: int = 0,
        include_archived: bool = False
    ) -> list[Project]:
        if include_archived:
            query = "SELECT * FROM projects ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params = (limit, offset)
        else:
            query = "SELECT * FROM projects WHERE status != 'archived' ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params = (limit, offset)
        
        rows = await self.db.fetch_all(query, params)
        return [self._row_to_entity(row) for row in rows]
    
    async def delete(self, project_id: str) -> bool:
        await self.db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return True
    
    async def exists(self, project_id: str) -> bool:
        row = await self.db.fetch_one(
            "SELECT id FROM projects WHERE id = ?",
            (project_id,)
        )
        return row is not None
    
    def _row_to_entity(self, row: dict) -> Project:
        return Project(
            id=row["id"],
            title=row["title"],
            description=row["description"] or "",
            status=ProjectStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            settings=json.loads(row["settings"]) if row["settings"] else {}
        )
    
    async def get_characters(self, project_id: str) -> list[dict]:
        rows = await self.db.fetch_all(
            "SELECT * FROM characters WHERE project_id = ?",
            (project_id,),
        )
        return [
            {
                "id": row["id"],
                "project_id": row["project_id"],
                "name": row["name"],
                "aliases": json.loads(row.get("aliases", "[]")),
                "description": row.get("description", ""),
                "first_appearance_chapter": row.get("first_appearance_chapter"),
                "attributes": json.loads(row.get("attributes", "{}")),
            }
            for row in rows
        ]
    
    async def save_character(self, character_data: dict) -> None:
        await self.db.execute(
            """
            INSERT OR REPLACE INTO characters
            (id, project_id, name, aliases, description, first_appearance_chapter, attributes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                character_data["id"],
                character_data["project_id"],
                character_data["name"],
                json.dumps(character_data.get("aliases", [])),
                character_data.get("description", ""),
                character_data.get("first_appearance_chapter"),
                json.dumps(character_data.get("attributes", {})),
            ),
        )
    
    async def delete_character(self, character_id: str) -> bool:
        await self.db.execute(
            "DELETE FROM characters WHERE id = ?",
            (character_id,),
        )
        return True
