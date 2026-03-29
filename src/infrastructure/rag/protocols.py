from typing import Protocol, Optional, runtime_checkable

from src.shared.types import Chunk, RetrievalResult


@runtime_checkable
class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...
    
    def embed_query(self, query: str) -> list[float]:
        ...
    
    def get_dimension(self) -> int:
        ...


@runtime_checkable
class Chunker(Protocol):
    def chunk(self, text: str, metadata: dict) -> list[Chunk]:
        ...
    
    def get_chunk_size(self) -> int:
        ...


@runtime_checkable
class VectorStore(Protocol):
    async def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict]
    ) -> int:
        ...
    
    async def query(
        self,
        query_embedding: list[float],
        n_results: int,
        where: Optional[dict] = None
    ) -> tuple[list[Chunk], list[float]]:
        ...
    
    async def delete(self, ids: Optional[list[str]] = None, where: Optional[dict] = None) -> int:
        ...
    
    async def count(self, where: Optional[dict] = None) -> int:
        ...


@runtime_checkable
class RAGPipeline(Protocol):
    async def index(
        self,
        project_id: str,
        chapter_id: str,
        text: str
    ) -> int:
        ...
    
    async def retrieve(
        self,
        query: str,
        project_id: str,
        top_k: int = 5,
        use_reranker: bool = True
    ) -> RetrievalResult:
        ...
    
    async def delete_project(self, project_id: str) -> int:
        ...
    
    def format_context(
        self,
        result: RetrievalResult,
        max_tokens: int = 2000
    ) -> str:
        ...
