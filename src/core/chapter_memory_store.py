"""章节记忆的存储：每章一条（摘要、出场角色、关键事件、伏笔、生成时的正文指纹），与项目数据在同一个数据库。"""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

import aiosqlite

from src import paths


@dataclass
class CharacterNote:
    """某一章里关于某个角色的记录。"""
    name: str
    aliases: list[str] = field(default_factory=list)  # 本章出现的其他称呼
    traits: str = ""                                  # 本章体现的性格
    status: str = ""                                  # 本章结束时的状态变化


@dataclass
class ChapterMemory:
    chapter_id: str
    summary: str = ""
    characters: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    fingerprint: str = ""  # 生成记忆时正文的指纹；正文变了才需要重新整理
    notes: list[CharacterNote] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)  # 本章埋下、尚未揭晓的悬念或伏笔

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
            columns = {row[1] for row in await (await db.execute("PRAGMA table_info(chapter_memories)")).fetchall()}
            added = [column for column in ("notes", "hooks") if column not in columns]
            for column in added:
                await db.execute(f"ALTER TABLE chapter_memories ADD COLUMN {column} TEXT")
            if added:  # 旧记忆是按旧格式整理的，没有这些内容：清掉指纹，下次「整理记忆」时重新整理
                await db.execute("UPDATE chapter_memories SET fingerprint = ''")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS character_overrides (
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    aliases TEXT,
                    traits TEXT,
                    notes TEXT,
                    hidden INTEGER DEFAULT 0,
                    updated_at TEXT,
                    PRIMARY KEY (project_id, name)
                )
            """)
            await db.commit()

    async def save(self, project_id: str, memory: ChapterMemory) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO chapter_memories "
                "(chapter_id, project_id, fingerprint, summary, characters, events, updated_at, notes, hooks) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (memory.chapter_id, project_id, memory.fingerprint, memory.summary,
                 json.dumps(memory.characters, ensure_ascii=False), json.dumps(memory.events, ensure_ascii=False),
                 datetime.now().isoformat(timespec="seconds"),
                 json.dumps([asdict(n) for n in memory.notes], ensure_ascii=False),
                 json.dumps(memory.hooks, ensure_ascii=False)))
            await db.commit()

    async def for_project(self, project_id: str) -> dict[str, ChapterMemory]:
        """本项目各章的记忆，按章节 id 索引。"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT chapter_id, summary, characters, events, fingerprint, notes, hooks FROM chapter_memories "
                "WHERE project_id = ?", (project_id,))
            rows = await cursor.fetchall()
        return {r[0]: ChapterMemory(r[0], r[1] or "", json.loads(r[2] or "[]"), json.loads(r[3] or "[]"), r[4] or "",
                                    [CharacterNote(**n) for n in json.loads(r[5] or "[]")], json.loads(r[6] or "[]"))
                for r in rows}

    async def has_any(self, project_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT 1 FROM chapter_memories WHERE project_id = ? LIMIT 1", (project_id,))
            return await cursor.fetchone() is not None

    async def clone(self, old_pid: str, new_pid: str, chapter_map: dict[str, str]) -> None:
        """复制项目时一并复制记忆与角色档案的手动修订，章节 id 换成副本的。"""
        for chapter_id, memory in (await self.for_project(old_pid)).items():
            if chapter_id in chapter_map:
                memory.chapter_id = chapter_map[chapter_id]
                await self.save(new_pid, memory)
        for override in (await self.overrides(old_pid)).values():
            await self.save_override(new_pid, override)

    # --- 角色档案的手动修订：优先于自动汇总的内容 ---
    async def overrides(self, project_id: str) -> dict[str, "CharacterOverride"]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT name, aliases, traits, notes, hidden FROM character_overrides "
                                      "WHERE project_id = ?", (project_id,))
            rows = await cursor.fetchall()
        return {r[0]: CharacterOverride(r[0], json.loads(r[1] or "[]"), r[2] or "", r[3] or "", bool(r[4]))
                for r in rows}

    async def save_override(self, project_id: str, override: "CharacterOverride") -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO character_overrides VALUES (?, ?, ?, ?, ?, ?, ?)",
                (project_id, override.name, json.dumps(override.aliases, ensure_ascii=False), override.traits,
                 override.notes, int(override.hidden), datetime.now().isoformat(timespec="seconds")))
            await db.commit()


@dataclass
class CharacterOverride:
    """用户对角色档案的修订：别名（可把两个称呼合并成一个角色）、性格、备注、隐藏（误识别的角色）。"""
    name: str
    aliases: list[str] = field(default_factory=list)
    traits: str = ""
    notes: str = ""
    hidden: bool = False
