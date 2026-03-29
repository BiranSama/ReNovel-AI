import uuid
import re
from .base import BaseChunker
from src.shared.types import Chunk


class NovelChunker(BaseChunker):
    def __init__(
        self,
        chunk_size: int = 500,
        overlap: int = 50,
        min_segment_length: int = 10,
    ):
        super().__init__(chunk_size, overlap)
        self.min_segment_length = min_segment_length
    
    def chunk(self, text: str, metadata: dict) -> list[Chunk]:
        paragraphs = self._split_paragraphs(text)
        chunks = []
        current_chunk = []
        current_length = 0
        chunk_index = 0
        
        for para in paragraphs:
            para_length = len(para)
            
            if para_length < self.min_segment_length:
                continue
            
            if current_length + para_length > self.chunk_size and current_chunk:
                chunk_text = "\n".join(current_chunk)
                chunks.append(self._create_chunk(chunk_text, metadata, chunk_index))
                chunk_index += 1
                
                if self.overlap > 0 and current_chunk:
                    overlap_text = current_chunk[-1] if len(current_chunk) > 0 else ""
                    current_chunk = [overlap_text] if overlap_text else []
                    current_length = len(overlap_text)
                else:
                    current_chunk = []
                    current_length = 0
            
            current_chunk.append(para)
            current_length += para_length
        
        if current_chunk:
            chunk_text = "\n".join(current_chunk)
            chunks.append(self._create_chunk(chunk_text, metadata, chunk_index))
        
        return chunks
    
    def _split_paragraphs(self, text: str) -> list[str]:
        paragraphs = re.split(r'\n\s*\n', text)
        result = []
        
        for para in paragraphs:
            para = para.strip()
            if len(para) >= self.min_segment_length:
                result.append(para)
        
        return result
    
    def _create_chunk(self, text: str, metadata: dict, index: int) -> Chunk:
        chunk_metadata = metadata.copy()
        chunk_metadata["chunk_index"] = index
        
        return Chunk(
            id=str(uuid.uuid4()),
            content=text,
            metadata=chunk_metadata,
        )
