import uuid
from typing import Optional

from src.shared.types import Chunk, RetrievalResult
from src.infrastructure.rag.protocols import (
    Embedder,
    Chunker,
    VectorStore,
    RAGPipeline as RAGPipelineProtocol,
)
from src.infrastructure.rag.embedders import LocalEmbedder
from src.infrastructure.rag.chunkers import NovelChunker
from src.infrastructure.rag.vector_stores import ChromaDBStore


class RAGPipeline(RAGPipelineProtocol):
    def __init__(
        self,
        embedder: Optional[Embedder] = None,
        chunker: Optional[Chunker] = None,
        vector_store: Optional[VectorStore] = None,
    ):
        self.embedder = embedder or LocalEmbedder()
        self.chunker = chunker or NovelChunker()
        self.vector_store = vector_store or ChromaDBStore()
    
    async def index(
        self,
        project_id: str,
        chapter_id: str,
        text: str,
    ) -> int:
        if not text.strip():
            return 0
        
        metadata = {
            "project_id": project_id,
            "chapter_id": chapter_id,
        }
        
        chunks = self.chunker.chunk(text, metadata)
        
        if not chunks:
            return 0
        
        ids = [chunk.id for chunk in chunks]
        documents = [chunk.content for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]
        
        embeddings = self.embedder.embed(documents)
        
        for i, chunk in enumerate(chunks):
            chunk.embedding = embeddings[i]
        
        await self.vector_store.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        
        return len(chunks)
    
    async def retrieve(
        self,
        query: str,
        project_id: str,
        top_k: int = 5,
        use_reranker: bool = True,
    ) -> RetrievalResult:
        query_embedding = self.embedder.embed_query(query)
        
        chunks, scores = await self.vector_store.query(
            query_embedding=query_embedding,
            n_results=top_k,
            where={"project_id": project_id},
        )
        
        if use_reranker and len(chunks) > 1:
            chunks, scores = self._rerank(query, chunks, scores)
        
        return RetrievalResult(
            chunks=chunks,
            scores=scores,
            query=query,
            total_tokens=len(query),
        )
    
    async def delete_project(self, project_id: str) -> int:
        return await self.vector_store.delete(where={"project_id": project_id})
    
    def format_context(
        self,
        result: RetrievalResult,
        max_tokens: int = 2000,
    ) -> str:
        if not result.chunks:
            return ""
        
        context_parts = []
        current_length = 0
        
        for chunk, score in zip(result.chunks, result.scores):
            chunk_text = f"- {chunk.content}"
            chunk_length = len(chunk_text)
            
            if current_length + chunk_length > max_tokens * 2:
                break
            
            context_parts.append(chunk_text)
            current_length += chunk_length
        
        if not context_parts:
            return ""
        
        return f"【前文剧情/相关记忆 (RAG)】：\n" + "\n".join(context_parts) + "\n"
    
    def _rerank(
        self,
        query: str,
        chunks: list[Chunk],
        scores: list[float],
    ) -> tuple[list[Chunk], list[float]]:
        query_words = set(query.lower().split())
        
        reranked = []
        for chunk, score in zip(chunks, scores):
            content_words = set(chunk.content.lower().split())
            overlap = len(query_words & content_words)
            adjusted_score = score + (overlap * 0.01)
            reranked.append((chunk, adjusted_score))
        
        reranked.sort(key=lambda x: x[1], reverse=True)
        
        return (
            [item[0] for item in reranked],
            [item[1] for item in reranked],
        )
    
    async def clone_project_memory(self, old_pid: str, new_pid: str) -> int:
        chunks = await self.vector_store.get_by_project(old_pid)
        
        if not chunks:
            return 0
        
        new_chunks = []
        for chunk in chunks:
            new_metadata = chunk.metadata.copy()
            new_metadata["project_id"] = new_pid
            
            new_chunk = Chunk(
                id=str(uuid.uuid4()),
                content=chunk.content,
                metadata=new_metadata,
                embedding=chunk.embedding,
            )
            new_chunks.append(new_chunk)
        
        ids = [c.id for c in new_chunks]
        embeddings = [c.embedding for c in new_chunks if c.embedding]
        documents = [c.content for c in new_chunks]
        metadatas = [c.metadata for c in new_chunks]
        
        if embeddings:
            await self.vector_store.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
        
        return len(new_chunks)
