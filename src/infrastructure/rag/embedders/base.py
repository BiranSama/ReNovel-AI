from abc import ABC, abstractmethod
from typing import Optional


class BaseEmbedder(ABC):
    def __init__(self, dimension: Optional[int] = None):
        self._dimension = dimension
    
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...
    
    @abstractmethod
    def embed_query(self, query: str) -> list[float]:
        ...
    
    def get_dimension(self) -> int:
        if self._dimension is None:
            sample = self.embed(["test"])
            self._dimension = len(sample[0])
        return self._dimension
