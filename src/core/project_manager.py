import aiosqlite
import uuid
import json
from datetime import datetime

from src import paths
from src.services.importer import split_chapters

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

    async def update_chapter_content(self, chapter_id: str, new_content: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE chapters SET content = ? WHERE id = ?", (new_content, chapter_id))
            await db.commit()

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
