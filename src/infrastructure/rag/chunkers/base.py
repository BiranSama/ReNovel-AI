from abc import ABC, abstractmethod
from src.shared.types import Chunk


class BaseChunker(ABC):
    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    @abstractmethod
    def chunk(self, text: str, metadata: dict) -> list[Chunk]:
        ...
    
    def get_chunk_size(self) -> int:
        return self.chunk_size
