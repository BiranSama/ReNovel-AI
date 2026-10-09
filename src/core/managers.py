"""应用级服务：启动时创建一次，所有浏览器标签页共享。每个标签页自己的状态在 src/ui/session.py。"""
import asyncio

from src import paths
from src.core.project_manager import ProjectManager
from src.llm import LLMClient
from src.core.tavern_parser import TavernParser
from src.core.settings import AppSettings
from src.ai.rag_engine import RAGEngine
from src.services.context import ContextBuilder
from src.services.refine import RefinePipeline
from src.services.batch import BatchService
from src.services.chat import ChatService
from src.services.graph import GraphService
from src.services.chapter_memory import ChapterMemoryService
from src.services.characters import CharacterService
from src.core.chapter_memory_store import ChapterMemoryStore
from src.utils.logger import ConsoleLogger as Log
# 容错导入 GraphEngine
try:
    from src.core.graph_engine import GraphEngine
except ImportError:
    GraphEngine = None


class GraphStore:
    """按项目缓存图谱引擎：同一项目在所有标签页共享一份，切换项目不再影响其他标签页。"""

    def __init__(self):
        self._engines = {}

    def get(self, project_id):
        if not GraphEngine or not project_id:
            return None
        if project_id not in self._engines:
            self._engines[project_id] = GraphEngine(project_id)
        return self._engines[project_id]


class Services:
    def __init__(self):
        paths.ensure_dirs()
        self.pm = ProjectManager()
        self.llm = LLMClient()
        self.tavern = TavernParser()
        self.settings = AppSettings()
        self.rag = RAGEngine(lambda: self.settings.config.get("embedding", {}))
        self.graphs = GraphStore()
        self.chapter_store = ChapterMemoryStore()
        context = ContextBuilder(self.rag, self.graphs.get, projects=self.pm, chapter_store=self.chapter_store)
        self.refine = RefinePipeline(self.llm, self.settings, context)
        self.chat = ChatService(self.llm, self.settings, context)
        self.graph = GraphService(self.llm, self.settings, self.pm)
        self.chapter_memory = ChapterMemoryService(self.llm, self.settings, self.pm, self.chapter_store)
        self.characters = CharacterService(self.pm, self.chapter_store, self.graphs.get)
        self.batch = BatchService(self.pm, self.refine, self.rag, self.chapter_store, self.chapter_memory)

    async def init_db(self):
        """在 app.on_startup 时调用"""
        await self.pm.init_db()
        await self.chapter_store.init_db()
        if self.rag.needs_migration():
            projects = await self.pm.get_projects()
            self.rag.begin_rebuild(p["id"] for p in projects)  # 在页面能打开之前登记，检索和复制会等重建完
            asyncio.create_task(self.migrate_legacy_memory(projects))

    async def migrate_legacy_memory(self, projects=None):
        """旧版本的 ChromaDB 记忆：从已保存的章节正文重建到新的向量库（后台逐个项目进行，不影响启动）。

        重建期间这个项目的检索和复制会等它完成，免得用到不完整的记忆，或复制出缺章节的副本。
        """
        if projects is None:
            projects = await self.pm.get_projects()
            self.rag.begin_rebuild(p["id"] for p in projects)
        Log.system("[RAG] 发现旧版本的向量记忆，正在从已保存的章节重建……")
        try:
            for project in projects:
                for chapter in await self.pm.get_chapters(project["id"]):
                    text = await self.pm.get_chapter_content(chapter["id"]) or ""
                    await self.rag.aindex_chapter(project["id"], chapter["id"], text)
                self.rag.finish_rebuild(project["id"])
            self.rag.mark_migrated()
            Log.system("[RAG] 记忆迁移完成，旧的 data/vectordb 目录可以删除")
        finally:
            for project in projects:  # 出错时也不能让检索、复制一直等下去
                self.rag.finish_rebuild(project["id"])
