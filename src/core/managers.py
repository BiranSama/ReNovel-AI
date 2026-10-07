from src.core.project_manager import ProjectManager
from src.ai.llm_client import LLMClient
from src.core.tavern_parser import TavernParser
from src.ai.rag_engine import RAGEngine
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
        self.pm = ProjectManager()
        self.llm = LLMClient()
        self.tavern = TavernParser()
        self.rag = RAGEngine()
        self.current_graph_engine = None # 当前项目的图谱引擎

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