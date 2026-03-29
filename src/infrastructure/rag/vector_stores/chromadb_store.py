import os
from typing import Optional, Protocol
import chromadb

from src.shared.types import Chunk


class EmbedderProtocol(Protocol):
    def embed(self, documents: list[str]) -> list[list[float]]: ...

class ChromaDBStore:
    def __init__(
        self,
        persist_dir: str = "data/vectordb",
        collection_name: str = "novel_memory",
        embedder: Optional[EmbedderProtocol] = None,
    ):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.embedder = embedder
        
        os.makedirs(persist_dir, exist_ok=True)
        
        self.client = chromadb.PersistentClient(path=persist_dir)
        
        if embedder and hasattr(embedder, '_embedding_fn'):
            self._embedding_fn = embedder._embedding_fn
        else:
            from chromadb.utils import embedding_functions
            self._embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
        )
    
    async def upsert(
        self,
        ids: list[str],
        embeddings: Optional[list[list[float]]],
        documents: list[str],
        metadatas: list[dict],
    ) -> int:
        if not ids:
            return 0
        
        if embeddings:
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
        else:
            self.collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )
        
        return len(ids)
    
    async def query(
        self,
        query_embedding: Optional[list[float]],
        query_text: Optional[str] = None,
        n_results: int = 5,
        where: Optional[dict] = None,
    ) -> tuple[list[Chunk], list[float]]:
        query_args = {"n_results": n_results}
        if where:
            query_args["where"] = where
        
        if query_embedding:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                include=["documents", "metadatas", "distances"],
                **query_args,
            )
        elif query_text:
            results = self.collection.query(
                query_texts=[query_text],
                include=["documents", "metadatas", "distances"],
                **query_args,
            )
        else:
            return [], []
        
        chunks = []
        scores = []
        
        if not results['ids'] or not results['ids'][0]:
            return chunks, scores
        
        ids = results['ids'][0]
        documents = results['documents'][0]
        metadatas = results['metadatas'][0] if results['metadatas'] else []
        distances = results['distances'][0] if results.get('distances') else []
        
        for doc_id, doc, meta, dist in zip(
            ids, documents, metadatas or [{}] * len(ids), distances or [0.0] * len(ids)
        ):
            chunk = Chunk(
                id=doc_id,
                content=doc,
                metadata=meta,
            )
            chunks.append(chunk)
            scores.append(1.0 - dist)
        
        return chunks, scores
    
    async def delete(
        self,
        ids: Optional[list[str]] = None,
        where: Optional[dict] = None,
    ) -> int:
        if ids:
            self.collection.delete(ids=ids)
            return len(ids)
        elif where:
            existing = self.collection.get(where=where)
            count = len(existing['ids'])
            if count > 0:
                self.collection.delete(where=where)
            return count
        return 0
    
    async def count(self, where: Optional[dict] = None) -> int:
        if where:
            results = self.collection.get(where=where)
            return len(results['ids'])
        return self.collection.count()
    
    async def get_by_project(self, project_id: str) -> list[Chunk]:
        results = self.collection.get(
            where={"project_id": project_id},
            include=["documents", "metadatas"],
        )
        
        chunks = []
        ids = results['ids']
        documents = results['documents']
        metadatas = results['metadatas'] if results['metadatas'] else []
        
        for doc_id, doc, meta in zip(
            ids, documents, metadatas or [{}] * len(ids)
        ):
            chunk = Chunk(
                id=doc_id,
                content=doc,
                metadata=meta,
            )
            chunks.append(chunk)
        
        return chunks
    
