import networkx as nx
import json
import os
from src.utils.logger import ConsoleLogger as Log
from src import paths

class GraphEngine:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.file_path = str(paths.graph_file(project_id))
        self.graph = nx.MultiDiGraph()
        self.load_graph()

    def load_graph(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.graph = nx.node_link_graph(data, edges="links")
                Log.system(f"图谱已加载: {self.graph.number_of_nodes()} 节点")
            except: Log.system("图谱加载失败，初始化新图谱")
        else: Log.system("初始化新图谱")

    def save_graph(self):
        try:
            data = nx.node_link_data(self.graph, edges="links")
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e: Log.system(f"图谱保存失败: {e}")

    def add_relation(self, source: str, target: str, relation: str,
                    chapter_id: int, reveal_chapter: int = None,
                    is_secret: bool = False, desc: str = "") -> bool:
        """添加关系；同一对实体间的同一种关系只保留一条（取最早出现 / 揭示的章节）。返回是否新增。"""
        if reveal_chapter is None: reveal_chapter = chapter_id

        # 强力清洗
        source = str(source).strip(); target = str(target).strip(); relation = str(relation).strip()
        if not source or not target or not relation: return False

        if self.graph.has_edge(source, target):
            for data in self.graph[source][target].values():
                if data.get('relation') == relation:
                    data['start_chapter'] = min(data.get('start_chapter', chapter_id), chapter_id)
                    data['reveal_chapter'] = min(data.get('reveal_chapter', reveal_chapter), reveal_chapter)
                    data['is_secret'] = bool(data.get('is_secret')) or bool(is_secret)
                    if desc and not data.get('desc'): data['desc'] = desc
                    return False

        self.graph.add_edge(
            source, target,
            relation=relation,
            desc=desc,
            start_chapter=chapter_id,
            reveal_chapter=reveal_chapter,
            is_secret=bool(is_secret)
        )
        return True

    # --- 增量更新：记录每章抽取时的内容指纹，内容没变的章节不再重复分析 ---
    def chapter_fingerprint(self, chapter_id: str):
        return self.graph.graph.get('extracted', {}).get(chapter_id)

    def mark_extracted(self, chapter_id: str, fingerprint: str):
        self.graph.graph.setdefault('extracted', {})[chapter_id] = fingerprint

    def is_built(self) -> bool:
        return bool(self.graph.graph.get('extracted')) or self.graph.number_of_edges() > 0

    def entity_names(self, limit: int = 50) -> list[str]:
        """关联最多的实体名，供抽取时统一称呼。"""
        return sorted(self.graph.nodes(), key=lambda n: self.graph.degree(n), reverse=True)[:limit]

    def get_visualization_data(self):
        if self.graph.number_of_nodes() == 0: return {"nodes": [], "links": []}
        nodes = [{"name": n, "symbolSize": min(self.graph.degree(n)*3+10, 60), "category": 1 if self.graph.degree(n)>5 else 0, "draggable": True} for n in self.graph.nodes()]
        links = [{"source": u, "target": v, "value": data.get('relation', ''), "lineStyle": {"width": 2 if data.get('is_secret') else 1}} for u, v, data in self.graph.edges(data=True)]
        return {"nodes": nodes, "links": links}

    def entities_in(self, text: str, limit: int = 8) -> list[str]:
        """文本中出现的图谱实体（两个字及以上），按关联数从多到少。"""
        found = [n for n in self.graph.nodes() if len(str(n)) >= 2 and str(n) in text]
        return sorted(found, key=lambda n: self.graph.degree(n), reverse=True)[:limit]

    def context_for_text(self, text: str, current_chapter: int, mode: str = 'reader') -> str:
        """文本中出现的各实体的关系，按视角过滤。"""
        lines = [self.query_context(e, current_chapter, mode) for e in self.entities_in(text)]
        return "\n".join(line for line in lines if line)

    def query_context(self, entity: str, current_chapter: int, mode: str = 'reader') -> str:
        if entity not in self.graph: return ""
        lines = []
        for neighbor in self.graph.successors(entity):
            edges = self.graph[entity][neighbor]
            for _, data in edges.items():
                if self._check_visibility(data, current_chapter, mode):
                    info = f"- {entity} {data.get('relation')} {neighbor}"
                    if data.get('desc'): info += f" ({data.get('desc')})"
                    if mode == 'author' and data.get('is_secret'): info += " [🔒伏笔]"
                    lines.append(info)
        return "\n".join(lines)

    def _check_visibility(self, edge_data, current_chapter, mode):
        if mode == 'author': return True
        if current_chapter < edge_data.get('reveal_chapter', 0): return False
        return True
