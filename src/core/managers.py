"""应用级服务：启动时创建一次，所有浏览器标签页共享。每个标签页自己的状态在 src/ui/session.py。"""
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

    def forget(self, project_id) -> None:
        """丢掉缓存的引擎，下次使用时重新读取图谱文件（例如复制项目时图谱文件是后写入的）。"""
        self._engines.pop(project_id, None)


class Services:
    def __init__(self):
        paths.ensure_dirs()
        self.pm = ProjectManager()
        self.llm = LLMClient()
        self.tavern = TavernParser()
        self.rag = RAGEngine()
        self.settings = AppSettings()
        self.graphs = GraphStore()
        context = ContextBuilder(self.rag, self.graphs.get)
        self.refine = RefinePipeline(self.llm, self.settings, context)
        self.chat = ChatService(self.llm, self.settings, context)
        self.graph = GraphService(self.llm, self.settings, self.pm)
        self.batch = BatchService(self.pm, self.refine, self.rag, graphs=self.graphs)

    async def init_db(self):
        """在 app.on_startup 时调用"""
        await self.pm.init_db()
