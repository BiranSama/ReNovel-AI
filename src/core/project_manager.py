import aiosqlite
import uuid
import re
import json
from datetime import datetime

DB_PATH = "data/projects/novelforge.db"

class ProjectManager:
    def __init__(self):
        self.db_path = DB_PATH

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
            
            await db.execute(
                "INSERT INTO projects (id, title, description, created_at, world_settings) VALUES (?, ?, ?, ?, ?)",
                (new_pid, new_title, original_project['description'], datetime.now().isoformat(), original_project['world_settings'])
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
            
    async def get_chapters(self, project_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT id, title, order_index FROM chapters WHERE project_id = ? ORDER BY order_index ASC", (project_id,))
            return [dict(row) for row in await cursor.fetchall()]

    async def get_chapter_content(self, chapter_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT content FROM chapters WHERE id = ?", (chapter_id,))
            row = await cursor.fetchone()
            return row[0] if row else ""

    async def update_chapter_content(self, chapter_id: str, new_content: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE chapters SET content = ? WHERE id = ?", (new_content, chapter_id))
            await db.commit()

    # --- 新增：进度存取 ---
    async def save_progress(self, project_id: str, chapter_id: str):
        """记录当前精修到了哪一章"""
        async with aiosqlite.connect(self.db_path) as db:
            # 先读取旧配置
            async with db.execute("SELECT world_settings FROM projects WHERE id = ?", (project_id,)) as cursor:
                row = await cursor.fetchone()
                current_settings = json.loads(row[0]) if row and row[0] else {}
            
            current_settings['last_polished_chapter_id'] = chapter_id
            
            await db.execute("UPDATE projects SET world_settings = ? WHERE id = ?", (json.dumps(current_settings), project_id))
            await db.commit()

    async def get_progress(self, project_id: str):
        """获取上次精修的章节ID"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT world_settings FROM projects WHERE id = ?", (project_id,)) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    settings = json.loads(row[0])
                    return settings.get('last_polished_chapter_id')
        return None

    # --- 导入逻辑 (保持不变) ---
    def _clean_text(self, text: str) -> str:
        return text.replace("\xa0", " ").replace("\u3000", " ").replace("\r\n", "\n").replace("\r", "\n")

    async def import_content(self, project_id: str, content: str):
        content = self._clean_text(content)
        patterns = [
            r'(?m)^\s*(?:第[0-9零一二三四五六七八九十百千]+[章卷]|Chapter\s*\d+|Vol\.\d+).*?$',
            r'(?m)^\s*\d+\.\s+.{0,30}$',
            r'(?m)^\s*[【\[]\s*.*?\s*[】\]].*?$',
            r'(?m)^\s*(?!.*[。，？！……：]$).{2,20}\s*$' 
        ]
        matches = []
        for p in patterns:
            regex = re.compile(p)
            temp_matches = list(regex.finditer(content))
            if len(temp_matches) > 2:
                matches = temp_matches
                break
        
        async with aiosqlite.connect(self.db_path) as db:
            if not matches:
                await db.execute("INSERT INTO chapters (id, project_id, title, order_index, content) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), project_id, "全文", 0, content))
            else:
                if matches[0].start() > 0:
                    preface = content[:matches[0].start()].strip()
                    if preface:
                        await db.execute("INSERT INTO chapters (id, project_id, title, order_index, content) VALUES (?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), project_id, "【序章】", -1, preface))

                for i, match in enumerate(matches):
                    title = match.group().strip()
                    start = match.end()
                    end = matches[i+1].start() if i + 1 < len(matches) else len(content)
                    chapter_content = content[start:end].strip()
                    if len(chapter_content) < 10: continue
                    await db.execute("INSERT INTO chapters (id, project_id, title, order_index, content) VALUES (?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), project_id, title, i, chapter_content))
            await db.commit()
            return len(matches) if matches else 1