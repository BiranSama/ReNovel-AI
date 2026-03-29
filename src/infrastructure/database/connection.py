import aiosqlite
from contextlib import asynccontextmanager
from typing import AsyncIterator
import os


class Database:
    def __init__(self, db_path: str = "data/projects/novelforge.db"):
        self.db_path = db_path
        self._ensure_dir()
    
    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await self._ensure_schema(db)
            yield db
    
    async def _ensure_schema(self, db: aiosqlite.Connection):
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT,
                updated_at TEXT,
                settings TEXT
            );
            
            CREATE TABLE IF NOT EXISTS chapters (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title TEXT,
                order_index INTEGER DEFAULT 0,
                content TEXT,
                word_count INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                metadata TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS segments (
                id TEXT PRIMARY KEY,
                chapter_id TEXT NOT NULL,
                original TEXT,
                revised TEXT,
                order_index INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                instruction TEXT,
                review_score REAL,
                review_suggestion TEXT,
                FOREIGN KEY(chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS characters (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                aliases TEXT,
                description TEXT,
                first_appearance_chapter INTEGER,
                attributes TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS relations (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation_type TEXT,
                description TEXT,
                start_chapter INTEGER DEFAULT 1,
                reveal_chapter INTEGER,
                is_secret INTEGER DEFAULT 0,
                confidence REAL DEFAULT 1.0,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(source_id) REFERENCES characters(id) ON DELETE CASCADE,
                FOREIGN KEY(target_id) REFERENCES characters(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS batch_tasks (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                chapter_ids TEXT,
                instruction TEXT,
                status TEXT DEFAULT 'pending',
                progress REAL DEFAULT 0,
                current_chapter TEXT,
                error TEXT,
                created_at TEXT,
                completed_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS plot_events (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                chapter_id TEXT NOT NULL,
                chapter_index INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                characters TEXT,
                location TEXT,
                story_time TEXT,
                importance INTEGER DEFAULT 1,
                affects_future INTEGER DEFAULT 0,
                affected_by TEXT,
                metadata TEXT,
                created_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS character_states (
                id TEXT PRIMARY KEY,
                character_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                chapter_id TEXT NOT NULL,
                chapter_index INTEGER NOT NULL,
                emotional_state TEXT DEFAULT 'neutral',
                knowledge TEXT,
                beliefs TEXT,
                goals TEXT,
                location TEXT,
                relationships TEXT,
                physical_state TEXT DEFAULT 'healthy',
                inventory TEXT,
                secrets TEXT,
                notes TEXT,
                created_at TEXT,
                FOREIGN KEY(character_id) REFERENCES characters(id) ON DELETE CASCADE,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS chapter_summaries (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                chapter_id TEXT NOT NULL,
                chapter_index INTEGER NOT NULL,
                summary TEXT NOT NULL,
                key_events TEXT,
                key_characters TEXT,
                word_count INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            );
            
            CREATE INDEX IF NOT EXISTS idx_chapters_project ON chapters(project_id);
            CREATE INDEX IF NOT EXISTS idx_chapters_order ON chapters(project_id, order_index);
            CREATE INDEX IF NOT EXISTS idx_segments_chapter ON segments(chapter_id);
            CREATE INDEX IF NOT EXISTS idx_characters_project ON characters(project_id);
            CREATE INDEX IF NOT EXISTS idx_relations_project ON relations(project_id);
            CREATE INDEX IF NOT EXISTS idx_batch_project ON batch_tasks(project_id);
            CREATE INDEX IF NOT EXISTS idx_plot_events_project ON plot_events(project_id);
            CREATE INDEX IF NOT EXISTS idx_plot_events_chapter ON plot_events(chapter_id);
            CREATE INDEX IF NOT EXISTS idx_plot_events_type ON plot_events(project_id, event_type);
            CREATE INDEX IF NOT EXISTS idx_character_states_character ON character_states(character_id);
            CREATE INDEX IF NOT EXISTS idx_character_states_chapter ON character_states(chapter_id);
            CREATE INDEX IF NOT EXISTS idx_chapter_summaries_project ON chapter_summaries(project_id);
        """)
        await db.commit()
    
    async def execute(self, query: str, params: tuple = ()) -> None:
        async with self.connection() as db:
            await db.execute(query, params)
            await db.commit()
    
    async def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        async with self.connection() as db:
            async with db.execute(query, params) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    
    async def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        async with self.connection() as db:
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]


db = Database()
