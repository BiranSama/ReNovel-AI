from typing import Optional

from .base import BaseEmbedder


class LocalEmbedder(BaseEmbedder):
    def __init__(self, dimension: Optional[int] = None):
        super().__init__(dimension)
        self._embedding_fn = None
    
    def _get_embedding_fn(self):
        if self._embedding_fn is None:
            from chromadb.utils import embedding_functions
            self._embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        return self._embedding_fn
    
    def embed(self, texts: list[str]) -> list[list[float]]:
        fn = self._get_embedding_fn()
        embeddings = fn(texts)
        
        if self._dimension is None and len(embeddings) > 0:
            self._dimension = len(embeddings[0])
        
        return embeddings
    
    def embed_query(self, query: str) -> list[float]:
        results = self.embed([query])
        return results[0]
