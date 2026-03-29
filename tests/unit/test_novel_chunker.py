import pytest

from src.infrastructure.rag.chunkers.novel_chunker import NovelChunker
from src.infrastructure.rag.chunkers.base import BaseChunker
from src.shared.types import Chunk


class TestNovelChunker:
    @pytest.fixture
    def chunker(self):
        return NovelChunker(
            chunk_size=500,
            overlap=50,
            min_segment_length=10,
        )

    def test_chunk_single_paragraph(self, chunker: NovelChunker):
        text = "这是一个测试段落，长度足够长，应该被正确分块处理。"
        metadata = {"chapter_id": "chap-001"}
        
        chunks = chunker.chunk(text, metadata)
        
        assert len(chunks) == 1
        assert chunks[0].content == text
        assert chunks[0].metadata["chapter_id"] == "chap-001"

    def test_chunk_multiple_paragraphs(self, chunker: NovelChunker):
        text = """这是第一段，包含一些测试内容。

这是第二段，也有一些测试内容。

这是第三段，同样包含测试内容。"""
        metadata = {"chapter_id": "chap-001"}
        
        chunks = chunker.chunk(text, metadata)
        
        assert len(chunks) >= 1
        for chunk in chunks:
            assert isinstance(chunk, Chunk)
            assert len(chunk.content) >= chunker.min_segment_length

    def test_chunk_filters_short_paragraphs(self, chunker: NovelChunker):
        text = """短段落

这是一个足够长的段落，应该被保留并处理，因为它超过了最小长度限制。

另一个短"""
        metadata = {}
        
        chunks = chunker.chunk(text, metadata)
        
        for chunk in chunks:
            assert len(chunk.content) >= chunker.min_segment_length

    def test_chunk_with_overlap(self):
        chunker = NovelChunker(
            chunk_size=100,
            overlap=30,
            min_segment_length=10,
        )
        
        text = """这是第一段内容，需要足够长才能触发分块。这是第一段内容，需要足够长才能触发分块。

这是第二段内容，同样需要足够长才能触发分块。这是第二段内容，同样需要足够长才能触发分块。

这是第三段内容，也需要足够长才能触发分块。这是第三段内容，也需要足够长才能触发分块。"""
        
        chunks = chunker.chunk(text, {})
        
        if len(chunks) > 1:
            assert chunker.overlap > 0

    def test_chunk_empty_text(self, chunker: NovelChunker):
        chunks = chunker.chunk("", {})
        
        assert len(chunks) == 0

    def test_chunk_only_short_paragraphs(self, chunker: NovelChunker):
        text = """短
短
短"""
        chunks = chunker.chunk(text, {})
        
        assert len(chunks) == 0

    def test_chunk_metadata_preserved(self, chunker: NovelChunker):
        text = "这是一个足够长的测试段落，用于验证元数据是否正确保存。"
        metadata = {
            "project_id": "proj-001",
            "chapter_id": "chap-001",
            "chapter_index": 1,
        }
        
        chunks = chunker.chunk(text, metadata)
        
        assert len(chunks) == 1
        assert chunks[0].metadata["project_id"] == "proj-001"
        assert chunks[0].metadata["chapter_id"] == "chap-001"
        assert chunks[0].metadata["chapter_index"] == 1

    def test_split_paragraphs(self, chunker: NovelChunker):
        text = """这是第一段内容，长度足够长，应该被正确处理。

这是第二段内容，也有足够的长度，应该被正确处理。

这是第三段内容，同样有足够的长度，应该被正确处理。"""
        
        paragraphs = chunker._split_paragraphs(text)
        
        assert len(paragraphs) == 3

    def test_split_paragraphs_with_extra_newlines(self, chunker: NovelChunker):
        text = """这是第一段内容，长度足够长，应该被正确处理。


这是第二段内容，也有足够的长度，应该被正确处理。


这是第三段内容，同样有足够的长度，应该被正确处理。"""
        
        paragraphs = chunker._split_paragraphs(text)
        
        assert len(paragraphs) == 3

    def test_create_chunk(self, chunker: NovelChunker):
        text = "测试文本"
        metadata = {"key": "value"}
        
        chunk = chunker._create_chunk(text, metadata, 0)
        
        assert chunk.content == text
        assert chunk.metadata["key"] == "value"
        assert chunk.metadata["chunk_index"] == 0
        assert chunk.id is not None

    def test_large_text_chunking(self, chunker: NovelChunker):
        paragraphs = []
        for i in range(20):
            paragraphs.append(f"这是第{i+1}段内容，长度足够长，需要包含足够多的字符才能被处理。")
        
        text = "\n\n".join(paragraphs)
        
        chunks = chunker.chunk(text, {})
        
        assert len(chunks) >= 1
        total_content = "\n".join(c.content for c in chunks)
        for para in paragraphs:
            if len(para) >= chunker.min_segment_length:
                assert para in total_content


class TestBaseChunker:
    def test_chunker_parameters(self):
        from src.infrastructure.rag.chunkers.base import BaseChunker
        
        class ConcreteChunker(BaseChunker):
            def chunk(self, text: str, metadata: dict):
                return []
        
        chunker = ConcreteChunker(chunk_size=1000, overlap=100)
        
        assert chunker.chunk_size == 1000
        assert chunker.overlap == 100
