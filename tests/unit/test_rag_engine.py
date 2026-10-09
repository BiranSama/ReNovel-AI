"""向量记忆（真实 ChromaDB）：重建章节时旧片段不残留。首次运行会下载嵌入模型。"""
import pytest

from src.ai.rag_engine import RAGEngine

LINES = ["张三推开门走进了屋子。", "李四坐在窗边看书。", "王五在门外等了很久。"]


@pytest.fixture
def rag(tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVEL_DATA_DIR", str(tmp_path))
    return RAGEngine()


def chapter_docs(rag, chapter_id):
    return sorted(rag.collection.get(where={"chapter_id": chapter_id})["documents"])


def test_reindexing_a_shorter_chapter_drops_old_lines(rag):
    rag.index_chapter("p1", "c1", "\n".join(LINES))
    rag.index_chapter("p1", "c2", "赵六骑马离开了长安。")
    rag.index_chapter("p1", "c1", LINES[0])

    assert chapter_docs(rag, "c1") == [LINES[0]]
    assert chapter_docs(rag, "c2") == ["赵六骑马离开了长安。"]  # 其他章节不受影响


def test_clearing_a_chapter_removes_its_memory(rag):
    rag.index_chapter("p1", "c1", "\n".join(LINES))
    rag.index_chapter("p1", "c1", "")
    assert chapter_docs(rag, "c1") == []


def test_cloned_memory_is_replaced_when_backup_chapter_is_reindexed(rag):
    rag.index_chapter("p1", "c1", "\n".join(LINES))
    rag.clone_project_memory("p1", "p2")  # 副本的片段 id 是新生成的
    rag.index_chapter("p2", "c1", LINES[1])
    assert sorted(rag.collection.get(where={"project_id": "p2"})["documents"]) == [LINES[1]]
    assert len(rag.collection.get(where={"project_id": "p1"})["ids"]) == 3
