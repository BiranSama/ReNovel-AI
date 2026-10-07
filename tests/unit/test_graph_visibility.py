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


def test_entities_in_text_are_found(engine):
    assert engine.entities_in("这天张三遇见了王五。") == ["张三", "王五"]  # 按关联数排序
    assert engine.entities_in("无关的句子") == []


def test_context_for_text_respects_view(engine):
    assert engine.context_for_text("张三推门而入", current_chapter=5, mode="reader") == "- 张三 朋友 李四"
    assert "[🔒伏笔]" in engine.context_for_text("张三推门而入", current_chapter=5, mode="author")


def test_same_relation_is_not_duplicated(engine):
    assert engine.add_relation("张三", "李四", "朋友", chapter_id=7) is False
    assert engine.add_relation("张三", "李四", "同学", chapter_id=7) is True  # 不同关系仍然保留
    assert engine.graph.number_of_edges() == 3


def test_duplicate_keeps_earliest_reveal_and_fills_missing_desc(engine):
    engine.add_relation("张三", "王五", "生父", chapter_id=4, reveal_chapter=4, desc="另一种说法")
    assert engine.query_context("张三", current_chapter=5, mode="reader").endswith("- 张三 生父 王五 (身世之谜)")


def test_chapter_fingerprints_survive_reload(engine):
    assert not GraphEngine("empty").is_built()
    engine.mark_extracted("c1", "abc")
    engine.save_graph()
    reloaded = GraphEngine("p1")
    assert reloaded.chapter_fingerprint("c1") == "abc" and reloaded.is_built()


def test_incoming_relations_are_included(engine):
    assert engine.query_context("李四", current_chapter=5, mode="reader") == "- 张三 朋友 李四"
    # 两个实体都出现时，同一条关系只列一次
    assert engine.context_for_text("张三和李四", current_chapter=5, mode="reader") == "- 张三 朋友 李四"


def test_remove_chapter_only_drops_relations_from_that_chapter(engine):
    engine.add_relation("李四", "赵六", "师徒", chapter_id=2, from_chapter="c2")
    engine.add_relation("张三", "赵六", "同门", chapter_id=2, from_chapter="c2")
    engine.add_relation("张三", "赵六", "同门", chapter_id=3, from_chapter="c3")
    engine.mark_extracted("c2", "abc")

    engine.remove_chapter("c2")
    assert not engine.graph.has_edge("李四", "赵六")
    same_school = next(iter(engine.graph["张三"]["赵六"].values()))
    assert same_school["start_chapter"] == 3 and set(same_school["sources"]) == {"c3"}
    assert engine.graph.has_edge("张三", "李四")  # 没有来源记录的关系（手动添加 / 旧版本）不动
    assert engine.chapter_fingerprint("c2") is None
