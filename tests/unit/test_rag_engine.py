"""向量记忆（SQLite + numpy）：重建章节时旧片段不残留、副本记忆、换模型后重新生成向量、
向量生成失败时不丢原文、旧 ChromaDB 数据迁移；异步接口不阻塞事件循环。用假的向量模型，不联网。"""
import asyncio
import time

import numpy as np
import pytest

from src.ai.embeddings import EmbeddingError, normalize
from src.ai.rag_engine import RAGEngine
from src.core.managers import Services

LINES = ["张三推开门走进了屋子。", "李四坐在窗边看书。", "王五在门外等了很久。"]


class CharEmbedder:
    """按字符计数的确定性向量：共用字越多越相似。"""

    def __init__(self, name="fake:chars", fail=False):
        self.name, self.fail, self.calls = name, fail, []

    def embed(self, texts):
        if self.fail:
            raise EmbeddingError("模型下载失败")
        self.calls.append(list(texts))
        vectors = np.zeros((len(texts), 256), dtype=np.float32)
        for row, text in enumerate(texts):
            for ch in text:
                vectors[row, ord(ch) % 256] += 1
        return normalize(vectors)


@pytest.fixture
def rag(tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVEL_DATA_DIR", str(tmp_path))
    return RAGEngine(embedder=CharEmbedder())


def test_search_finds_most_similar_lines_within_project(rag):
    rag.index_chapter("p1", "c1", "\n".join(LINES))
    rag.index_chapter("p2", "c1", "张三推开门走进了另一间屋子。")
    assert rag.search("李四在窗边看书", "p1", n_results=1) == [LINES[1]]
    assert "另一间" not in "".join(rag.search("张三推开门", "p1"))  # 项目之间严格隔离


def test_search_can_be_limited_to_chapters(rag):
    rag.index_chapter("p1", "c1", LINES[0])
    rag.index_chapter("p1", "c2", LINES[1])
    assert rag.search("李四看书", "p1", chapter_ids={"c1"}) == [LINES[0]]


def test_short_lines_and_empty_queries(rag):
    rag.index_chapter("p1", "c1", "嗯。\n" + LINES[0])
    assert rag.store.chapter_texts("p1", "c1") == [LINES[0]]
    assert rag.search("  ", "p1") == [] and rag.search("张三", None) == []


def test_reindexing_a_shorter_chapter_drops_old_lines(rag):
    rag.index_chapter("p1", "c1", "\n".join(LINES))
    rag.index_chapter("p1", "c2", "赵六骑马离开了长安。")
    rag.index_chapter("p1", "c1", LINES[0])

    assert rag.store.chapter_texts("p1", "c1") == [LINES[0]]
    assert rag.store.chapter_texts("p1", "c2") == ["赵六骑马离开了长安。"]  # 其他章节不受影响
    assert "王五" not in "".join(rag.search("王五在门外", "p1"))  # 删掉的内容检索不到


def test_clearing_a_chapter_removes_its_memory(rag):
    rag.index_chapter("p1", "c1", "\n".join(LINES))
    rag.index_chapter("p1", "c1", "")
    assert rag.store.chapter_texts("p1", "c1") == [] and rag.search("张三", "p1") == []


def test_cloned_memory_follows_backup_chapter_ids(rag):
    rag.index_chapter("p1", "c1", "\n".join(LINES))
    embedder = rag.embedder()
    calls = len(embedder.calls)
    rag.clone_project_memory("p1", "p2", {"c1": "b1"})
    assert len(embedder.calls) == calls  # 直接复用向量，不重新计算
    assert rag.store.chapter_texts("p2", "b1") == LINES

    rag.index_chapter("p2", "b1", LINES[1])  # 副本的章节改写后，旧片段被替换
    assert rag.store.count("p2") == 1 and rag.store.count("p1") == 3


def test_embedding_failure_keeps_text_and_fills_vectors_later(tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVEL_DATA_DIR", str(tmp_path))
    embedder = CharEmbedder(fail=True)
    rag = RAGEngine(embedder=embedder)
    rag.index_chapter("p1", "c1", "\n".join(LINES))
    assert rag.store.chapter_texts("p1", "c1") == LINES and "模型下载失败" in rag.last_error
    assert rag.search("李四", "p1") == []  # 检索失败不抛异常

    embedder.fail = False
    assert rag.search("李四坐在窗边", "p1", n_results=1) == [LINES[1]]
    assert rag.last_error == ""


def test_switching_model_reembeds_old_fragments(tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVEL_DATA_DIR", str(tmp_path))
    config = {"provider": "local"}
    built = []

    def fake_create(conf):
        built.append(dict(conf))
        return CharEmbedder(name=f"fake:{conf['provider']}")

    monkeypatch.setattr("src.ai.rag_engine.create_embedder", fake_create)
    rag = RAGEngine(lambda: config)
    rag.index_chapter("p1", "c1", "\n".join(LINES))

    config["provider"] = "api"  # 设置里切换了向量来源
    assert rag.search("李四坐在窗边", "p1", n_results=1) == [LINES[1]]
    assert [b["provider"] for b in built] == ["local", "api"]
    assert rag.store.stale("p1", "fake:api") == []  # 旧片段已用新模型重新生成


def test_reopening_store_keeps_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVEL_DATA_DIR", str(tmp_path))
    RAGEngine(embedder=CharEmbedder()).index_chapter("p1", "c1", "\n".join(LINES))
    assert RAGEngine(embedder=CharEmbedder()).search("李四坐在窗边", "p1", n_results=1) == [LINES[1]]


def test_legacy_chroma_data_is_rebuilt_from_saved_chapters(tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVEL_DATA_DIR", str(tmp_path))
    (tmp_path / "vectordb").mkdir()
    (tmp_path / "vectordb" / "chroma.sqlite3").write_bytes(b"")  # 旧版本留下的数据

    services = Services()
    services.rag = RAGEngine(embedder=CharEmbedder())

    async def run():
        await services.pm.init_db()
        pid = await services.pm.create_project("书")
        await services.pm.import_content(pid, "第一章 开端\n" + "\n".join(LINES) + "\n第二章 发展\n赵六骑马离开了长安。\n")
        assert services.rag.needs_migration()
        await services.migrate_legacy_memory()
        return pid

    pid = asyncio.run(run())
    assert services.rag.store.count(pid) == 4
    assert not services.rag.needs_migration()  # 只迁移一次


def test_async_api_keeps_event_loop_responsive(rag, monkeypatch):
    """检索很慢（如首次下载向量模型）时，事件循环仍能处理其他任务，界面不会卡住。"""
    monkeypatch.setattr(rag, "search", lambda *args: time.sleep(0.5) or ["结果"])

    async def run():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.05)
                ticks += 1

        task = asyncio.create_task(ticker())
        result = await rag.asearch("问题", "p1")
        task.cancel()
        return result, ticks

    result, ticks = asyncio.run(run())
    assert result == ["结果"]
    assert ticks >= 5  # 同步调用会让 ticker 在这 0.5 秒里一次都跑不了


def test_async_calls_are_serialized(rag, monkeypatch):
    """多个标签页同时读写向量库时依次执行，不会并发访问。"""
    active, peak = 0, 0

    def slow(*args):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        time.sleep(0.05)
        active -= 1

    monkeypatch.setattr(rag, "index_chapter", slow)

    async def run():
        await asyncio.gather(*(rag.aindex_chapter("p1", f"c{i}", "x") for i in range(5)))

    asyncio.run(run())
    assert peak == 1
