import networkx as nx
import json
import os
import re
import asyncio
from src.ai.llm_client import LLMClient
from src.utils.logger import ConsoleLogger as Log

class GraphEngine:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.file_path = f"data/projects/{project_id}_graph.json"
        self.graph = nx.MultiDiGraph()
        self.llm = LLMClient()
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
                    is_secret: bool = False, desc: str = ""):
        if reveal_chapter is None: reveal_chapter = chapter_id
        
        # 强力清洗
        source = str(source).strip(); target = str(target).strip()
        if not source or not target: return

        if source not in self.graph: self.graph.add_node(source)
        if target not in self.graph: self.graph.add_node(target)
        
        self.graph.add_edge(
            source, target, 
            relation=relation,
            desc=desc,
            start_chapter=chapter_id,
            reveal_chapter=reveal_chapter, 
            is_secret=is_secret
        )

    def get_visualization_data(self):
        if self.graph.number_of_nodes() == 0: return {"nodes": [], "links": []}
        nodes = [{"name": n, "symbolSize": min(self.graph.degree(n)*3+10, 60), "category": 1 if self.graph.degree(n)>5 else 0, "draggable": True} for n in self.graph.nodes()]
        links = [{"source": u, "target": v, "value": data.get('relation', ''), "lineStyle": {"width": 2 if data.get('is_secret') else 1}} for u, v, data in self.graph.edges(data=True)]
        return {"nodes": nodes, "links": links}

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

    async def build_graph_from_chapters(self, chapters, status_callback=None, config=None):
        total = len(chapters)
        from src.core.managers import mgr
        
        for i, chapter in enumerate(chapters):
            txt = chapter['content']
            if len(txt) < 50: continue
            if status_callback: status_callback(f"分析第 {i+1}/{total} 章...", (i / total))
            
            await self.extract_from_text_stream(txt, i+1, mgr.rag, config)
            
            if i % 3 == 0: self.save_graph()
            await asyncio.sleep(0.5)

        self.save_graph()
        if status_callback: status_callback("完成", 1.0)

    async def extract_from_text_stream(self, text: str, chapter_index: int, rag_engine=None, config=None):
        if not config:
            Log.system("GraphEngine: 无配置 (No Config)")
            return

        rag_context = ""
        if rag_engine and len(text) > 200:
            query = text[:100] + " " + text[-100:]
            rag_context = rag_engine.search_context(query, self.project_id, n_results=3)
            if rag_context:
                rag_context = f"【参考资料】\n{rag_context}\n请参考此资料进行消歧。"

        prompt = f"""
知识图谱提取。请提取【实体-关系-实体】三元组。
{rag_context}
【JSON格式】
[
  {{ "source": "A", "relation": "关系", "target": "B", "desc": "描述", "is_reveal": false }}
]
【待分析文本】
{text[:2500]} 
"""     
        ext_conf = config.copy()
        # 强制使用 JSON Mode (如果模型支持，否则靠 Prompt)
        ext_conf['system_prompt'] = "You are a data extractor. Output ONLY valid JSON list."
        
        try:
            json_str = ""
            async for token in self.llm.stream_rewrite(text, prompt, ext_conf):
                json_str += token
            
            # === 调试日志：看看 AI 到底回了什么 ===
            Log.system(f"RAW LLM RESP: {json_str[:100]}...")

            # === 暴力清洗：寻找 [] 之间的内容 ===
            match = re.search(r'\[.*\]', json_str, re.DOTALL)
            if match:
                json_str = match.group(0)
            else:
                Log.system("未找到 JSON 列表结构")
                return

            triples = json.loads(json_str)
            
            count = 0
            for t in triples:
                if not isinstance(t, dict): continue
                if 'source' not in t or 'target' not in t or 'relation' not in t: continue
                
                self.add_relation(
                    t['source'], t['target'], t['relation'],
                    chapter_id=chapter_index,
                    reveal_chapter=chapter_index, 
                    is_secret=t.get('is_reveal', False),
                    desc=t.get('desc', '')
                )
                count += 1
            Log.system(f"成功提取 {count} 条关系")
            
        except Exception as e:
            Log.system(f"Graph 提取异常: {e}")