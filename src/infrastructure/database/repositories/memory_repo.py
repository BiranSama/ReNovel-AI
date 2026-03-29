import json
from datetime import datetime
from typing import Optional

import aiosqlite

from src.domain.entities import PlotEvent, CharacterState, Character
from src.infrastructure.database.connection import db


class MemoryRepository:
    def __init__(self, db_connection=None):
        self.db = db_connection or db
    
    async def save_plot_event(self, event: PlotEvent) -> None:
        async with self.db.connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO plot_events 
                (id, project_id, chapter_id, chapter_index, event_type, title, summary,
                 characters, location, story_time, importance, affects_future, affected_by, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.project_id,
                    event.chapter_id,
                    event.chapter_index,
                    event.event_type.value,
                    event.title,
                    event.summary,
                    json.dumps(event.characters, ensure_ascii=False),
                    event.location,
                    event.story_time,
                    event.importance,
                    1 if event.affects_future else 0,
                    json.dumps(event.affected_by, ensure_ascii=False),
                    json.dumps(event.metadata, ensure_ascii=False),
                    datetime.now().isoformat(),
                ),
            )
            await conn.commit()
    
    async def save_plot_events(self, events: list[PlotEvent]) -> None:
        if not events:
            return
        
        now = datetime.now().isoformat()
        rows = [
            (
                event.id,
                event.project_id,
                event.chapter_id,
                event.chapter_index,
                event.event_type.value,
                event.title,
                event.summary,
                json.dumps(event.characters, ensure_ascii=False),
                event.location,
                event.story_time,
                event.importance,
                1 if event.affects_future else 0,
                json.dumps(event.affected_by, ensure_ascii=False),
                json.dumps(event.metadata, ensure_ascii=False),
                now,
            )
            for event in events
        ]
        
        async with self.db.connection() as conn:
            await conn.executemany(
                """
                INSERT OR REPLACE INTO plot_events 
                (id, project_id, chapter_id, chapter_index, event_type, title, summary,
                 characters, location, story_time, importance, affects_future, affected_by, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            await conn.commit()
    
    async def get_events_by_project(
        self,
        project_id: str,
        limit: int = 100,
    ) -> list[PlotEvent]:
        async with self.db.connection() as conn:
            async with conn.execute(
                """
                SELECT * FROM plot_events 
                WHERE project_id = ? 
                ORDER BY chapter_index ASC
                LIMIT ?
                """,
                (project_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_event(dict(row)) for row in rows]
    
    async def get_events_by_chapter(self, chapter_id: str) -> list[PlotEvent]:
        async with self.db.connection() as conn:
            async with conn.execute(
                "SELECT * FROM plot_events WHERE chapter_id = ?",
                (chapter_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_event(dict(row)) for row in rows]
    
    async def get_events_before_chapter(
        self,
        project_id: str,
        chapter_index: int,
        limit: int = 20,
    ) -> list[PlotEvent]:
        async with self.db.connection() as conn:
            async with conn.execute(
                """
                SELECT * FROM plot_events 
                WHERE project_id = ? AND chapter_index < ?
                ORDER BY chapter_index DESC
                LIMIT ?
                """,
                (project_id, chapter_index, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                events = [self._row_to_event(dict(row)) for row in rows]
                return list(reversed(events))
    
    async def get_events_after_chapter(
        self,
        project_id: str,
        chapter_index: int,
        limit: int = 20,
    ) -> list[PlotEvent]:
        async with self.db.connection() as conn:
            async with conn.execute(
                """
                SELECT * FROM plot_events 
                WHERE project_id = ? AND chapter_index > ?
                ORDER BY chapter_index ASC
                LIMIT ?
                """,
                (project_id, chapter_index, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_event(dict(row)) for row in rows]
    
    async def delete_events_by_chapter(self, chapter_id: str) -> int:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM plot_events WHERE chapter_id = ?",
                (chapter_id,),
            )
            await conn.commit()
            return cursor.rowcount
    
    async def save_character_state(self, state: CharacterState) -> None:
        async with self.db.connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO character_states
                (id, character_id, project_id, chapter_id, chapter_index, emotional_state,
                 knowledge, beliefs, goals, location, relationships, physical_state,
                 inventory, secrets, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.id,
                    state.character_id,
                    state.project_id,
                    state.chapter_id,
                    state.chapter_index,
                    state.emotional_state.value,
                    json.dumps(state.knowledge, ensure_ascii=False),
                    json.dumps(state.beliefs, ensure_ascii=False),
                    json.dumps(state.goals, ensure_ascii=False),
                    state.location,
                    json.dumps(state.relationships, ensure_ascii=False),
                    state.physical_state,
                    json.dumps(state.inventory, ensure_ascii=False),
                    json.dumps(state.secrets, ensure_ascii=False),
                    state.notes,
                    datetime.now().isoformat(),
                ),
            )
            await conn.commit()
    
    async def save_character_states(self, states: list[CharacterState]) -> None:
        if not states:
            return
        
        now = datetime.now().isoformat()
        rows = [
            (
                state.id,
                state.character_id,
                state.project_id,
                state.chapter_id,
                state.chapter_index,
                state.emotional_state.value,
                json.dumps(state.knowledge, ensure_ascii=False),
                json.dumps(state.beliefs, ensure_ascii=False),
                json.dumps(state.goals, ensure_ascii=False),
                state.location,
                json.dumps(state.relationships, ensure_ascii=False),
                state.physical_state,
                json.dumps(state.inventory, ensure_ascii=False),
                json.dumps(state.secrets, ensure_ascii=False),
                state.notes,
                now,
            )
            for state in states
        ]
        
        async with self.db.connection() as conn:
            await conn.executemany(
                """
                INSERT OR REPLACE INTO character_states
                (id, character_id, project_id, chapter_id, chapter_index, emotional_state,
                 knowledge, beliefs, goals, location, relationships, physical_state,
                 inventory, secrets, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            await conn.commit()
    
    async def get_character_states_by_chapter(
        self,
        chapter_id: str,
    ) -> list[CharacterState]:
        async with self.db.connection() as conn:
            async with conn.execute(
                "SELECT * FROM character_states WHERE chapter_id = ?",
                (chapter_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_state(dict(row)) for row in rows]
    
    async def get_latest_character_states(
        self,
        project_id: str,
        before_chapter_index: int,
    ) -> list[CharacterState]:
        async with self.db.connection() as conn:
            async with conn.execute(
                """
                SELECT cs.* FROM character_states cs
                INNER JOIN (
                    SELECT character_id, MAX(chapter_index) as max_chapter
                    FROM character_states
                    WHERE project_id = ? AND chapter_index < ?
                    GROUP BY character_id
                ) latest ON cs.character_id = latest.character_id 
                         AND cs.chapter_index = latest.max_chapter
                """,
                (project_id, before_chapter_index),
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_state(dict(row)) for row in rows]
    
    async def save_chapter_summary(
        self,
        project_id: str,
        chapter_id: str,
        chapter_index: int,
        summary: str,
        key_events: list[str],
        key_characters: list[str],
        word_count: int = 0,
    ) -> None:
        async with self.db.connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO chapter_summaries
                (id, project_id, chapter_id, chapter_index, summary, key_events, 
                 key_characters, word_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"summary_{chapter_id}",
                    project_id,
                    chapter_id,
                    chapter_index,
                    summary,
                    json.dumps(key_events, ensure_ascii=False),
                    json.dumps(key_characters, ensure_ascii=False),
                    word_count,
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                ),
            )
            await conn.commit()
    
    async def get_chapter_summary(self, chapter_id: str) -> Optional[dict]:
        async with self.db.connection() as conn:
            async with conn.execute(
                "SELECT * FROM chapter_summaries WHERE chapter_id = ?",
                (chapter_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    data = dict(row)
                    data["key_events"] = json.loads(data.get("key_events", "[]"))
                    data["key_characters"] = json.loads(data.get("key_characters", "[]"))
                    return data
                return None
    
    def _row_to_event(self, row: dict) -> PlotEvent:
        from src.domain.entities import EventType
        
        return PlotEvent(
            id=row["id"],
            project_id=row["project_id"],
            chapter_id=row["chapter_id"],
            chapter_index=row["chapter_index"],
            event_type=EventType(row["event_type"]),
            title=row["title"],
            summary=row["summary"],
            characters=json.loads(row.get("characters", "[]")),
            location=row.get("location"),
            story_time=row.get("story_time"),
            importance=row.get("importance", 1),
            affects_future=bool(row.get("affects_future", 0)),
            affected_by=json.loads(row.get("affected_by", "[]")),
            metadata=json.loads(row.get("metadata", "{}")),
        )
    
    def _row_to_state(self, row: dict) -> CharacterState:
        from src.domain.entities.character_state import EmotionalState
        
        return CharacterState(
            id=row["id"],
            character_id=row["character_id"],
            project_id=row["project_id"],
            chapter_id=row["chapter_id"],
            chapter_index=row["chapter_index"],
            emotional_state=EmotionalState(row.get("emotional_state", "neutral")),
            knowledge=json.loads(row.get("knowledge", "[]")),
            beliefs=json.loads(row.get("beliefs", "[]")),
            goals=json.loads(row.get("goals", "[]")),
            location=row.get("location"),
            relationships=json.loads(row.get("relationships", "{}")),
            physical_state=row.get("physical_state", "healthy"),
            inventory=json.loads(row.get("inventory", "[]")),
            secrets=json.loads(row.get("secrets", "[]")),
            notes=row.get("notes", ""),
        )
