"""知识图谱的特征测试：按章节的可见性（读者视角 / 作者视角）与落盘。

reader 视角只能看到 reveal_chapter 之前已揭示的关系（给 Writer 用，防止剧透），
author 视角看到全部并标注伏笔（给 Reviewer 用）。这是重构中要保留的核心设计。
"""
import pytest

from src.core.graph_engine import GraphEngine


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVEL_DATA_DIR", str(tmp_path))
    (tmp_path / "projects").mkdir()
    engine = GraphEngine("p1")
    engine.add_relation("张三", "李四", "朋友", chapter_id=1)
    engine.add_relation("张三", "王五", "生父", chapter_id=1, reveal_chapter=10, is_secret=True, desc="身世之谜")
    return engine


def test_reader_sees_only_revealed_relations(engine):
    assert engine.query_context("张三", current_chapter=5, mode="reader") == "- 张三 朋友 李四"


def test_reader_sees_relation_once_revealed(engine):
    context = engine.query_context("张三", current_chapter=10, mode="reader")
    assert "- 张三 生父 王五 (身世之谜)" in context
    assert "🔒" not in context


def test_author_sees_everything_with_secret_marker(engine):
    context = engine.query_context("张三", current_chapter=1, mode="author")
    assert "- 张三 朋友 李四" in context
    assert "- 张三 生父 王五 (身世之谜) [🔒伏笔]" in context


def test_unknown_entity_returns_empty(engine):
    assert engine.query_context("赵六", current_chapter=99, mode="author") == ""


def test_graph_round_trips_through_disk(engine):
    engine.save_graph()
    reloaded = GraphEngine("p1")
    assert reloaded.query_context("张三", 1, "author") == engine.query_context("张三", 1, "author")
    data = reloaded.get_visualization_data()
    assert {n["name"] for n in data["nodes"]} == {"张三", "李四", "王五"}
    assert len(data["links"]) == 2
