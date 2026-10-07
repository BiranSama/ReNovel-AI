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

class GlobalManagers:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalManagers, cls).__new__(cls)
            cls._instance.init_modules()
        return cls._instance

    def init_modules(self):
        paths.ensure_dirs()
        self.pm = ProjectManager()
        self.llm = LLMClient()
        self.tavern = TavernParser()
        self.rag = RAGEngine()
        self.current_graph_engine = None # 当前项目的图谱引擎
        self.settings = AppSettings()  # 所有标签页共享
        context = ContextBuilder(self.rag, lambda: self.current_graph_engine)
        self.refine = RefinePipeline(self.llm, self.settings, context)
        self.chat = ChatService(self.llm, self.settings, context)
        self.graph = GraphService(self.llm, self.settings, self.pm)
        self.batch = BatchService(self.pm, self.refine, self.rag)

    async def init_db(self):
        """在 app.on_startup 时调用"""
        await self.pm.init_db()

    def load_graph(self, project_id):
        """加载指定项目的图谱引擎"""
        if GraphEngine:
            self.current_graph_engine = GraphEngine(project_id)
        else:
            print("GraphEngine module not found.")

# 全局单例
mgr = GlobalManagers()