"""阶段 3 的完成标准：用一本测试小说验证——
- 在第 N 章改写时，Writer 的提示词里只出现前文信息（前情提要、前文片段、截至上一章的角色状态、已揭示的关系）
- Reviewer 的提示词里带有与本段相关的角色设定和前文事件，并要求指出具体冲突

用真实的项目数据库、章节记忆、向量记忆和图谱，只有模型和向量模型是假的。
"""
import asyncio
import json

import numpy as np
import pytest

from src.ai.embeddings import normalize
from src.ai.rag_engine import RAGEngine
from src.core.chapter_memory_store import CharacterNote, ChapterMemory, ChapterMemoryStore, CharacterOverride
from src.core.graph_engine import GraphEngine
from src.core.project_manager import ProjectManager
from src.core.settings import AppSettings
from src.services.context import ContextBuilder
from src.services.refine import RefinePipeline, RefineRequest

NOVEL = """第一章 入城
张三初入长安，在城门口遇见了卖剑的李四。
第二章 拜师
张三拜王五为师，学会了一套快剑。
第三章 比剑
张三与李四在擂台上比剑，张三用右手持剑。
第四章 反目
后文才发生：李四背叛张三，张三右手被废。
"""

MEMORIES = [
    ("入城", ["张三", "李四"], ["张三在城门口遇见李四"], [CharacterNote("张三", ["三郎"], "莽撞", "初入长安")]),
    ("拜师", ["张三", "王五"], ["张三拜王五为师"], [CharacterNote("张三", [], "勤奋", "学会快剑")]),
    ("比剑", ["张三", "李四"], ["张三与李四比剑"], []),
    ("后文反目", ["张三", "李四"], ["李四背叛张三"], [CharacterNote("张三", [], "", "后文：右手被废")]),
]


class CharEmbedder:
    name = "fake:chars"

    def embed(self, texts):
        vectors = np.zeros((len(texts), 256), dtype=np.float32)
        for row, text in enumerate(texts):
            for ch in text:
                vectors[row, ord(ch) % 256] += 1
        return normalize(vectors)


class RecordingLLM:
    def __init__(self):
        self.prompts = {}

    async def stream(self, config, messages):
        self.prompts.setdefault(config["model"], []).append(messages[-1]["content"])
        yield "改写后的正文。"

    async def complete(self, config, messages):
        self.prompts.setdefault(config["model"], []).append(messages[-1]["content"])
        return json.dumps({"score": 9, "suggestion": "好", "conflicts": []})


class Config:
    def load_config(self):
        return {r: {"api_key": "k", "model": r} for r in ("writer", "reviewer", "analyzer")} | {"enable_reviewer": True}

    def save_config(self, config):
        pass


@pytest.fixture
def book(tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVEL_DATA_DIR", str(tmp_path))
    (tmp_path / "projects").mkdir()
    pm = ProjectManager()
    pm.db_path = str(tmp_path / "t.db")
    store = ChapterMemoryStore(pm.db_path)
    rag = RAGEngine(embedder=CharEmbedder())

    async def init():
        await pm.init_db()
        await store.init_db()
        pid = await pm.create_project("剑客")
        await pm.import_content(pid, NOVEL)
        chapters = await pm.get_chapters(pid)
        for chapter, (summary, characters, events, notes) in zip(chapters, MEMORIES):
            await store.save(pid, ChapterMemory(chapter["id"], summary, characters, events, "f", notes))
            rag.index_chapter(pid, chapter["id"], await pm.get_chapter_content(chapter["id"]))
        await store.save_override(pid, CharacterOverride("张三", notes="惯用右手"))
        return pid

    pid = asyncio.run(init())
    graph = GraphEngine(pid)
    graph.add_relation("张三", "李四", "朋友", chapter_id=1)
    graph.add_relation("李四", "张三", "背叛", chapter_id=4, is_secret=True)
    context = ContextBuilder(rag, lambda project_id: graph, projects=pm, chapter_store=store)
    llm = RecordingLLM()
    pipeline = RefinePipeline(llm, AppSettings(Config()), context)
    return pid, pipeline, llm


def rewrite_chapter_three(book):
    pid, pipeline, llm = book
    text = "张三与李四在擂台上比剑，张三用右手持剑。"
    asyncio.run(pipeline.refine(RefineRequest(text=text, instruction="润色", project_id=pid, chapter_index=3)))
    return llm.prompts["writer"][0], llm.prompts["reviewer"][0]


def test_writer_prompt_only_contains_earlier_chapters(book):
    writer, _ = rewrite_chapter_three(book)
    context = writer.split("【指令】")[0]
    assert "【前情提要】\n- 第一章 入城：入城\n- 第二章 拜师：拜师" in context
    assert "张三初入长安" in context or "张三拜王五为师" in context  # 前文片段
    assert "三郎" in context and "惯用右手" in context and "莽撞；勤奋" in context  # 角色档案
    assert "经历：第一章 入城 初入长安；第二章 拜师 学会快剑" in context
    assert "- 张三 朋友 李四" in context
    for spoiler in ("后文", "背叛", "右手被废", "反目"):
        assert spoiler not in context, spoiler  # 第四章的任何信息都不能出现


def test_reviewer_prompt_has_profiles_events_and_conflict_instruction(book):
    _, reviewer = rewrite_chapter_three(book)
    assert "【角色档案】" in reviewer and "设定：惯用右手" in reviewer
    assert "【前文事件】\n- 第一章 入城：张三在城门口遇见李四\n- 第二章 拜师：张三拜王五为师" in reviewer
    assert "后文：右手被废" in reviewer  # 作者视角：完整的状态变化，用来检查伏笔
    assert "背叛" in reviewer and "🔒伏笔" in reviewer
    assert "conflicts" in reviewer and "OOC" in reviewer and "时间线" in reviewer


def test_first_chapter_has_no_earlier_context(book):
    pid, pipeline, llm = book
    asyncio.run(pipeline.refine(RefineRequest(text="张三初入长安。", instruction="润色", project_id=pid, chapter_index=1)))
    writer = llm.prompts["writer"][0].split("【指令】")[0]
    assert "前情提要" not in writer and "相关记忆" not in writer
    assert "经历" not in writer  # 第一章之前没有任何状态变化


def test_conflicts_are_fed_back_to_writer(tmp_path, monkeypatch, book):
    pid, pipeline, llm = book
    replies = iter([json.dumps({"score": 3, "suggestion": "改", "conflicts": ["第2章已拜师，此处却说没有师父"]}),
                    json.dumps({"score": 9, "suggestion": "好"})])

    async def complete(config, messages):
        return next(replies)

    llm.complete = complete
    result = asyncio.run(pipeline.refine(RefineRequest(text="张三说自己没有师父。", instruction="润色",
                                                       project_id=pid, chapter_index=3)))
    assert result.attempts == 2
    assert "冲突：第2章已拜师，此处却说没有师父" in llm.prompts["writer"][1]


def test_reader_profiles_ignore_aliases_and_traits_from_later_chapters(tmp_path, monkeypatch, book):
    pid, pipeline, llm = book
    store = pipeline.context.chapter_store

    async def reveal_later():
        chapter4 = (await pipeline.context.projects.get_chapters(pid))[3]
        memory = (await store.for_project(pid))[chapter4["id"]]
        memory.notes.append(CharacterNote("张三", ["鬼面人"], "阴狠", ""))
        await store.save(pid, memory)

    asyncio.run(reveal_later())
    writer, reviewer = rewrite_chapter_three(book)
    context = writer.split("【指令】")[0]
    assert "鬼面人" not in context and "阴狠" not in context  # 第四章才揭示的身份与性格
    assert "惯用右手" in context  # 用户手动填写的设定保留
    assert "鬼面人" in reviewer and "阴狠" in reviewer  # 作者视角可以看到
