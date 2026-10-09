import aiosqlite
import uuid
import json
from datetime import datetime
from typing import Optional

from src import paths
from src.services.importer import split_chapters

MAX_VERSIONS = 20  # 每章保留的历史版本数


class ProjectManager:
    def __init__(self):
        self.db_path = str(paths.db_file())

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT,
                    world_settings TEXT -- 我们用这个字段存 JSON 配置（含进度）
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chapters (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    title TEXT,
                    order_index INTEGER,
                    content TEXT,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chapter_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter_id TEXT NOT NULL,
                    content TEXT,
                    created_at TEXT
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_chapter_versions ON chapter_versions (chapter_id)")
            await db.commit()

    # --- 基础 CRUD ---
    async def create_project(self, title: str, description: str = "") -> str:
        project_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        # 初始化空的 settings
        settings = json.dumps({"last_polished_chapter_id": None})
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO projects (id, title, description, created_at, world_settings) VALUES (?, ?, ?, ?, ?)",
                (project_id, title, description, created_at, settings)
            )
            await db.commit()
        return project_id

    async def duplicate_project(self, project_id: str, suffix: str = "(精修副本)") -> str:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)) as cursor:
                original_project = await cursor.fetchone()
                if not original_project: return None
            
            new_pid = str(uuid.uuid4())
            new_title = f"{original_project['title']} {suffix}"
            settings = json.loads(original_project['world_settings'] or '{}')
            settings['backup_of'] = project_id              # 供“历史副本”列出
            settings['last_polished_chapter_id'] = None     # 副本的批量进度从头开始
            settings['polished_chapter_ids'] = []

            await db.execute(
                "INSERT INTO projects (id, title, description, created_at, world_settings) VALUES (?, ?, ?, ?, ?)",
                (new_pid, new_title, original_project['description'], datetime.now().isoformat(), json.dumps(settings))
            )
            
            async with db.execute("SELECT * FROM chapters WHERE project_id = ?", (project_id,)) as cursor:
                chapters = await cursor.fetchall()
                for ch in chapters:
                    new_cid = str(uuid.uuid4())
                    await db.execute(
                        "INSERT INTO chapters (id, project_id, title, order_index, content) VALUES (?, ?, ?, ?, ?)",
                        (new_cid, new_pid, ch['title'], ch['order_index'], ch['content'])
                    )
            await db.commit()
            return new_pid

    async def delete_project(self, project_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM chapters WHERE project_id = ?", (project_id,))
            await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            await db.commit()

    async def get_projects(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM projects ORDER BY created_at DESC")
            return [dict(row) for row in await cursor.fetchall()]
            
    async def get_backups(self, project_id: str):
        """由该项目创建的副本，新的在前。"""
        projects = await self.get_projects()
        return [p for p in projects if json.loads(p.get('world_settings') or '{}').get('backup_of') == project_id]

    async def add_chapter(self, project_id: str, title: str, content: str,
                          expected_tail: Optional[tuple[int, str]] = None) -> Optional[str]:
        """在全书末尾新增一章，返回章节 id。

        给出 expected_tail（现有章节数, 最后一章正文）时，全书末尾已经变了（新增了章节或改了最后一章）就不追加，返回 None。
        """
        chapter_id = str(uuid.uuid4())
        async with aiosqlite.connect(self.db_path) as db:
            # 独占事务：多个标签页同时追加章节时依次分配位置，不会得到相同的 order_index
            await db.execute("BEGIN IMMEDIATE")
            if expected_tail is not None:
                cursor = await db.execute("SELECT COUNT(*) FROM chapters WHERE project_id = ?", (project_id,))
                count = (await cursor.fetchone())[0]
                cursor = await db.execute("SELECT content FROM chapters WHERE project_id = ? "
                                          "ORDER BY order_index DESC LIMIT 1", (project_id,))
                row = await cursor.fetchone()
                if (count, (row[0] or "") if row else "") != tuple(expected_tail):
                    await db.rollback()
                    return None
            cursor = await db.execute("SELECT COALESCE(MAX(order_index), -1) + 1 FROM chapters WHERE project_id = ?",
                                      (project_id,))
            order_index = (await cursor.fetchone())[0]
            await db.execute("INSERT INTO chapters (id, project_id, title, order_index, content) VALUES (?, ?, ?, ?, ?)",
                             (chapter_id, project_id, title, order_index, content))
            await db.commit()
        return chapter_id

    async def get_chapters(self, project_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT id, title, order_index FROM chapters WHERE project_id = ? ORDER BY order_index ASC", (project_id,))
            return [dict(row) for row in await cursor.fetchall()]

    async def get_chapter_content(self, chapter_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT content FROM chapters WHERE id = ?", (chapter_id,))
            row = await cursor.fetchone()
            return (row[0] or "") if row else None  # 章节不存在返回 None；空章节返回 ""

    async def update_chapter_content(self, chapter_id: str, new_content: str, expected: Optional[str] = None) -> bool:
        """保存章节；内容有变化时把旧内容留作历史版本（每章保留最近 MAX_VERSIONS 个），可以恢复。

        给出 expected 时只在当前内容仍是它时写入（期间被别处保存过就不覆盖），返回是否写入。
        """
        async with aiosqlite.connect(self.db_path) as db:
            # 先拿写锁再读旧内容：两个标签页同时保存时依次进行，每个被替换掉的版本都能留进历史
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute("SELECT content FROM chapters WHERE id = ?", (chapter_id,))
            row = await cursor.fetchone()
            old = (row[0] or "") if row else ""
            if expected is not None and old != expected:
                await db.rollback()
                return False
            if old != new_content and old.strip():
                await db.execute("INSERT INTO chapter_versions (chapter_id, content, created_at) VALUES (?, ?, ?)",
                                 (chapter_id, old, datetime.now().isoformat(timespec="seconds")))
                await db.execute("DELETE FROM chapter_versions WHERE chapter_id = ? AND id NOT IN "
                                 "(SELECT id FROM chapter_versions WHERE chapter_id = ? ORDER BY id DESC LIMIT ?)",
                                 (chapter_id, chapter_id, MAX_VERSIONS))
            await db.execute("UPDATE chapters SET content = ? WHERE id = ?", (new_content, chapter_id))
            await db.commit()
        return True

    async def get_chapter_versions(self, chapter_id: str) -> list[dict]:
        """章节的历史版本，最新的在前。"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT id, content, created_at FROM chapter_versions WHERE chapter_id = ? "
                                      "ORDER BY id DESC", (chapter_id,))
            return [dict(row) for row in await cursor.fetchall()]

    # --- 新增：进度存取 ---
    async def save_progress(self, project_id: str, chapter_id: str):
        """记录批量精修已完成的章节（逐章累计，续跑时跳过这些章节）"""
        async with aiosqlite.connect(self.db_path) as db:
            # 先读取旧配置
            async with db.execute("SELECT world_settings FROM projects WHERE id = ?", (project_id,)) as cursor:
                row = await cursor.fetchone()
                current_settings = json.loads(row[0]) if row and row[0] else {}
            
            current_settings['last_polished_chapter_id'] = chapter_id
            done = current_settings.setdefault('polished_chapter_ids', [])
            if chapter_id not in done: done.append(chapter_id)

            await db.execute("UPDATE projects SET world_settings = ? WHERE id = ?", (json.dumps(current_settings), project_id))
            await db.commit()

    async def get_polished_chapter_ids(self, project_id: str) -> list:
        """批量精修已完成的章节 id"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT world_settings FROM projects WHERE id = ?", (project_id,)) as cursor:
                row = await cursor.fetchone()
        return json.loads(row[0]).get('polished_chapter_ids', []) if row and row[0] else []

    async def get_progress(self, project_id: str):
        """获取上次精修的章节ID"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT world_settings FROM projects WHERE id = ?", (project_id,)) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    settings = json.loads(row[0])
                    return settings.get('last_polished_chapter_id')
        return None

    # --- 导入 ---
    async def import_content(self, project_id: str, content: str) -> int:
        """按 split_chapters 切分并写入章节，返回章节数。"""
        chapters = split_chapters(content)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                "INSERT INTO chapters (id, project_id, title, order_index, content) VALUES (?, ?, ?, ?, ?)",
                [(str(uuid.uuid4()), project_id, c.title, c.order_index, c.content) for c in chapters],
            )
            await db.commit()
        return len(chapters)
