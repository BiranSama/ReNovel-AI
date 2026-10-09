"""图谱构建：以已保存的章节为单位抽取，内容没变的章节不重复调用模型。"""
import asyncio
import json

import pytest

from src.core.graph_engine import GraphEngine
from src.core.project_manager import ProjectManager
from src.core.settings import AppSettings
from src.llm import LLMError
from src.services.graph import GraphParseError, GraphService, clone_graph, parse_triples, pieces

BODY = "张三与李四在长安城外相遇，两人一见如故，约定次日同去拜访王五。" * 3


class StubConfig:
    def load_config(self):
        return {"graph": {"api_key": "k", "model": "graph"}}

    def save_config(self, config):
        pass


FRIENDS = '好的：[{"source": "张三", "relation": "朋友", "target": "李四", "desc": "一见如故"}]'


class FakeLLM:
    def __init__(self, fail_after=None, reply=FRIENDS):
        self.prompts, self.fail_after, self.reply = [], fail_after, reply

    async def complete(self, config, messages):
        if self.fail_after is not None and len(self.prompts) >= self.fail_after:
            raise LLMError("额度不足")
        self.prompts.append(messages[-1]["content"])
        return self.reply


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVEL_DATA_DIR", str(tmp_path))
    (tmp_path / "projects").mkdir()
    pm = ProjectManager()
    pm.db_path = str(tmp_path / "t.db")

    async def init():
        await pm.init_db()
        pid = await pm.create_project("书")
        await pm.import_content(pid, f"第一章 相遇\n{BODY}\n第二章 拜访\n{BODY}\n第三章 短\n太短了。\n")
        return pid

    return pm, asyncio.run(init())


def service(pm, llm):
    return GraphService(llm, AppSettings(StubConfig()), pm)


def test_parse_triples_filters_invalid_items():
    raw = '前言 [{"source": "甲", "relation": "师徒", "target": "乙"}, {"source": "缺字段"}, "坏"] 结尾'
    assert parse_triples(raw) == [{"source": "甲", "relation": "师徒", "target": "乙"}]
    assert parse_triples("确实没有关系：[]") == []


@pytest.mark.parametrize("raw", ["没有 JSON", "[坏掉"])
def test_parse_triples_rejects_malformed_output(raw):
    with pytest.raises(GraphParseError):
        parse_triples(raw)


def test_pieces_cover_whole_text():
    assert pieces("abcdefg", 3) == ["abc", "def", "g"]


def test_update_extracts_saved_chapters_once(env):
    pm, pid = env
    llm, engine = FakeLLM(), GraphEngine(pid)
    added = asyncio.run(service(pm, llm).update(engine, pid))

    assert added == 1  # 两章抽到同一条关系，只保留一条
    assert len(llm.prompts) == 2  # 太短的第三章跳过
    assert "【待分析文本】\n" + BODY in llm.prompts[0]
    assert "【已知实体（同一实体请沿用这些名称）】\n张三、李四" in llm.prompts[1]
    edge = next(iter(engine.graph["张三"]["李四"].values()))
    assert edge["start_chapter"] == 1 and edge["desc"] == "一见如故"

    asyncio.run(service(pm, llm).update(GraphEngine(pid), pid))  # 重新加载后再更新
    assert len(llm.prompts) == 2  # 内容没变：不再调用模型


def test_only_changed_chapters_are_reanalyzed(env):
    pm, pid = env
    llm = FakeLLM()
    asyncio.run(service(pm, llm).update(GraphEngine(pid), pid))
    second = asyncio.run(pm.get_chapters(pid))[1]["id"]
    asyncio.run(pm.update_chapter_content(second, BODY + "王五出场。"))

    asyncio.run(service(pm, llm).update(GraphEngine(pid), pid))
    assert len(llm.prompts) == 3


def test_chapter_filter_limits_work(env):
    pm, pid = env
    llm = FakeLLM()
    first = asyncio.run(pm.get_chapters(pid))[0]["id"]
    asyncio.run(service(pm, llm).update(GraphEngine(pid), pid, chapter_ids={first}))
    assert len(llm.prompts) == 1


def test_llm_error_keeps_finished_chapters(env, tmp_path):
    pm, pid = env
    with pytest.raises(LLMError):
        asyncio.run(service(pm, FakeLLM(fail_after=1)).update(GraphEngine(pid), pid))
    saved = json.loads((tmp_path / "projects" / f"{pid}_graph.json").read_text(encoding="utf-8"))
    assert len(saved["graph"]["extracted"]) == 1  # 第一章的结果已保存，下次只需补第二章


def test_clone_graph_copies_file(env, tmp_path):
    pm, pid = env
    asyncio.run(service(pm, FakeLLM()).update(GraphEngine(pid), pid))
    clone_graph(pid, "copy")
    assert GraphEngine("copy").query_context("张三", 9, "author") == "- 张三 朋友 李四 (一见如故)"
    clone_graph("missing", "x")  # 没有图谱时不报错


def test_changed_chapter_replaces_its_old_relations(env):
    pm, pid = env
    first, second = [c["id"] for c in asyncio.run(pm.get_chapters(pid))[:2]]
    asyncio.run(service(pm, FakeLLM()).update(GraphEngine(pid), pid))

    # 第一章改写后不再是“朋友”：第二章也提到这层关系，所以关系保留、起始章节后移
    enemies = '[{"source": "张三", "relation": "仇人", "target": "李四"}]'
    asyncio.run(pm.update_chapter_content(first, BODY + "两人反目。"))
    engine = GraphEngine(pid)
    asyncio.run(service(pm, FakeLLM(reply=enemies)).update(engine, pid))
    relations = {d["relation"]: d for d in engine.graph["张三"]["李四"].values()}
    assert set(relations) == {"朋友", "仇人"}
    assert relations["朋友"]["start_chapter"] == 2 and relations["仇人"]["start_chapter"] == 1

    # 第二章也改了：“朋友”不再有任何来源，从图谱里删除
    asyncio.run(pm.update_chapter_content(second, BODY + "再无往来。"))
    asyncio.run(service(pm, FakeLLM(reply=enemies)).update(engine, pid))
    assert [d["relation"] for d in engine.graph["张三"]["李四"].values()] == ["仇人"]


def test_cleared_chapter_drops_its_relations(env):
    pm, pid = env
    chapters = asyncio.run(pm.get_chapters(pid))
    engine = GraphEngine(pid)
    asyncio.run(service(pm, FakeLLM()).update(engine, pid))
    for chapter in chapters[:2]:
        asyncio.run(pm.update_chapter_content(chapter["id"], ""))
    llm = FakeLLM()
    asyncio.run(service(pm, llm).update(engine, pid))
    assert llm.prompts == [] and engine.graph.number_of_nodes() == 0


def test_malformed_response_is_retried_next_time(env):
    pm, pid = env
    engine = GraphEngine(pid)
    asyncio.run(service(pm, FakeLLM(reply="抱歉，我无法完成")).update(engine, pid))
    first = asyncio.run(pm.get_chapters(pid))[0]["id"]
    assert engine.chapter_fingerprint(first) is None  # 没有记录指纹

    llm = FakeLLM()
    asyncio.run(service(pm, llm).update(engine, pid))
    assert len(llm.prompts) == 2 and engine.chapter_fingerprint(first)


def test_clone_graph_remaps_chapter_ids(env):
    pm, pid = env
    asyncio.run(service(pm, FakeLLM()).update(GraphEngine(pid), pid))
    ids = [c["id"] for c in asyncio.run(pm.get_chapters(pid))]
    clone_graph(pid, "copy", {old: f"new-{old}" for old in ids})

    copy = GraphEngine("copy")
    assert set(copy.graph.graph["extracted"]) == {f"new-{old}" for old in ids}
    edge = next(iter(copy.graph["张三"]["李四"].values()))
    assert set(edge["sources"]) == {f"new-{old}" for old in ids[:2]}
