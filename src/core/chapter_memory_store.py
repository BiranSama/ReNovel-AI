"""章节记忆的存储：每章一条（摘要、出场角色、关键事件、生成时的正文指纹），与项目数据在同一个数据库。"""
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import aiosqlite

from src import paths


@dataclass
class ChapterMemory:
    chapter_id: str
    summary: str = ""
    characters: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    fingerprint: str = ""  # 生成记忆时正文的指纹；正文变了才需要重新整理

    @property
    def is_empty(self) -> bool:
        return not (self.summary or self.characters or self.events)


class ChapterMemoryStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(paths.db_file())

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chapter_memories (
                    chapter_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    fingerprint TEXT,
                    summary TEXT,
                    characters TEXT,
                    events TEXT,
                    updated_at TEXT
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_chapter_memories_project ON chapter_memories (project_id)")
            await db.commit()

    async def save(self, project_id: str, memory: ChapterMemory) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO chapter_memories VALUES (?, ?, ?, ?, ?, ?, ?)",
                (memory.chapter_id, project_id, memory.fingerprint, memory.summary,
                 json.dumps(memory.characters, ensure_ascii=False), json.dumps(memory.events, ensure_ascii=False),
                 datetime.now().isoformat(timespec="seconds")))
            await db.commit()

    async def for_project(self, project_id: str) -> dict[str, ChapterMemory]:
        """本项目各章的记忆，按章节 id 索引。"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT chapter_id, summary, characters, events, fingerprint FROM chapter_memories WHERE project_id = ?",
                (project_id,))
            rows = await cursor.fetchall()
        return {r[0]: ChapterMemory(r[0], r[1] or "", json.loads(r[2] or "[]"), json.loads(r[3] or "[]"), r[4] or "")
                for r in rows}

    async def has_any(self, project_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT 1 FROM chapter_memories WHERE project_id = ? LIMIT 1", (project_id,))
            return await cursor.fetchone() is not None

    async def clone(self, old_pid: str, new_pid: str, chapter_map: dict[str, str]) -> None:
        """复制项目时一并复制记忆，章节 id 换成副本的。"""
        for chapter_id, memory in (await self.for_project(old_pid)).items():
            if chapter_id in chapter_map:
                memory.chapter_id = chapter_map[chapter_id]
                await self.save(new_pid, memory)
