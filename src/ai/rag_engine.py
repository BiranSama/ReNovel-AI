import os
import chromadb
from chromadb.utils import embedding_functions
import uuid

from src import paths

class RAGEngine:
    def __init__(self):
        print("[RAG] 正在初始化向量数据库 (ChromaDB)...")
        self.client = chromadb.PersistentClient(path=str(paths.vectordb_dir()))
        self.emb_fn = embedding_functions.DefaultEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name="novel_memory",
            embedding_function=self.emb_fn
        )
        print(f"[RAG] 数据库加载成功。现有记忆条目: {self.collection.count()}")

    def index_chapter(self, project_id: str, chapter_id: str, text: str):
        if not text.strip(): return
        # 过滤短句，保留有意义的段落
        segments = [line.strip() for line in text.split('\n') if len(line.strip()) > 5]
        if not segments: return

        # 生成唯一 ID
        ids = [f"{project_id}_{chapter_id}_{i}" for i in range(len(segments))]
        metadatas = [{"project_id": project_id, "chapter_id": chapter_id, "line_index": i} for i in range(len(segments))]
        
        try:
            self.collection.upsert(ids=ids, documents=segments, metadatas=metadatas)
            print(f"[RAG] ✅ 已记忆章节 {chapter_id} ({len(segments)} 条)")
        except Exception as e:
            print(f"[RAG Error] 存储失败: {e}")

    def search_context(self, query: str, project_id: str, n_results=5) -> str:
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where={"project_id": project_id} # 严格隔离
            )
            if not results['documents'] or not results['documents'][0]: return ""
            
            retrieved_docs = results['documents'][0]
            context_text = "\n".join([f"- {doc}" for doc in retrieved_docs])
            print(f"[RAG] 🧠 联想到了 {len(retrieved_docs)} 条相关记忆")
            return f"【前文剧情/相关记忆 (RAG)】：\n{context_text}\n"
        except Exception as e:
            print(f"[RAG Error] 搜索失败: {e}")
            return ""

    def delete_project_memory(self, project_id: str):
        try:
            self.collection.delete(where={"project_id": project_id})
            print(f"[RAG] 已清除项目 {project_id} 的记忆")
        except Exception as e:
            print(f"[RAG Error] 删除失败: {e}")

    # --- 新增：记忆克隆 (用于副本创建) ---
    def clone_project_memory(self, old_pid: str, new_pid: str):
        """
        将旧项目的所有记忆复制一份给新项目，实现记忆隔离与演变
        """
        print(f"[RAG] 正在克隆记忆: {old_pid} -> {new_pid} ...")
        try:
            # 1. 获取旧项目的所有数据
            # ChromaDB 的 get 方法可以获取所有匹配的 embedding 和 metadata
            existing_data = self.collection.get(where={"project_id": old_pid}, include=["documents", "metadatas", "embeddings"])
            
            if not existing_data['ids']:
                print("[RAG] 原项目无记忆，跳过克隆")
                return

            count = len(existing_data['ids'])
            
            # 2. 构建新数据
            new_ids = []
            new_metadatas = []
            new_documents = existing_data['documents']
            new_embeddings = existing_data['embeddings']

            for i in range(count):
                # 生成新的唯一 ID，但保持原来的章节结构逻辑
                # 原 ID 格式: {old_pid}_{chapter_id}_{index}
                # 我们只需要替换 ID 前缀，或者干脆生成全新的 UUID 防止冲突
                # 为了简单且安全，我们使用 UUID
                new_ids.append(str(uuid.uuid4()))
                
                # 复制元数据，但修改 project_id
                meta = existing_data['metadatas'][i].copy()
                meta['project_id'] = new_pid
                new_metadatas.append(meta)

            # 3. 批量插入 (Chroma 建议分批插入，防止一次太大)
            batch_size = 500
            for i in range(0, count, batch_size):
                end = min(i + batch_size, count)
                self.collection.upsert(
                    ids=new_ids[i:end],
                    embeddings=new_embeddings[i:end], # 直接复用向量，省去重新计算的时间！
                    documents=new_documents[i:end],
                    metadatas=new_metadatas[i:end]
                )
            
            print(f"[RAG] ✅ 记忆克隆完成，共复制 {count} 条。新项目 ({new_pid}) 拥有了独立的记忆空间。")
            
        except Exception as e:
            print(f"[RAG Error] 克隆失败: {e}")

if __name__ == "__main__":
    # 测试代码
    rag = RAGEngine()