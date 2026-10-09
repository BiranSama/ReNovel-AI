"""文风档案的存储：每个项目一份（风格描述 + 代表段落），与项目数据在同一个数据库。"""
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import aiosqlite

from src import paths


@dataclass
class StyleProfile:
    description: str = ""                               # 风格描述：视角、句式、用词、修辞、节奏等
    samples: list[str] = field(default_factory=list)    # 代表段落，改写时作为示例
    source: str = ""                                    # 来源：提炼自原文 / 预设名 / 手动

    @property
    def is_empty(self) -> bool:
        return not (self.description.strip() or any(s.strip() for s in self.samples))


class StyleStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(paths.db_file())

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS style_profiles (
                    project_id TEXT PRIMARY KEY,
                    description TEXT,
                    samples TEXT,
                    source TEXT,
                    updated_at TEXT
                )
            """)
            await db.commit()

    async def get(self, project_id: Optional[str]) -> Optional[StyleProfile]:
        if not project_id:
            return None
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT description, samples, source FROM style_profiles WHERE project_id = ?",
                                      (project_id,))
            row = await cursor.fetchone()
        return StyleProfile(row[0] or "", json.loads(row[1] or "[]"), row[2] or "") if row else None

    async def save(self, project_id: str, profile: StyleProfile) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO style_profiles VALUES (?, ?, ?, ?, ?)",
                (project_id, profile.description.strip(),
                 json.dumps([s.strip() for s in profile.samples if s.strip()], ensure_ascii=False),
                 profile.source, datetime.now().isoformat(timespec="seconds")))
            await db.commit()

    async def clone(self, old_pid: str, new_pid: str) -> None:
        profile = await self.get(old_pid)
        if profile:
            await self.save(new_pid, profile)
