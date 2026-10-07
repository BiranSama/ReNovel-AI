"""续写：新章节与段后续写的提示词（前文、后文、大纲、伏笔、文风、只用前文的参考资料）、审校与重试、采纳写入。"""
import asyncio
import json

import numpy as np
import pytest

from src.ai.embeddings import normalize
from src.ai.rag_engine import RAGEngine
from src.core.chapter_memory_store import ChapterMemory, ChapterMemoryStore
from src.core.project_manager import ProjectManager
from src.core.settings import AppSettings
from src.core.style_store import StyleProfile, StyleStore
from src.services.context import ContextBuilder
from src.services.continuation import ContinuationService, ContinueRequest
from src.services.refine import RefinePipeline

NOVEL = """第一章 入城
张三初入长安，在城门口遇见了卖剑的李四。
第二章 拜师
张三拜王五为师，学会了一套快剑。
第三章 反目
后文才发生：李四背叛张三。
"""
MEMORIES = [("入城", ["城门口的那把剑来历不明"]), ("拜师", ["王五似乎认识李四"]), ("后文反目", ["后文伏笔：密信"])]


class CharEmbedder:
    name = "fake:chars"

    def embed(self, texts):
        vectors = np.zeros((len(texts), 256), dtype=np.float32)
        for row, text in enumerate(texts):
            for ch in text:
                vectors[row, ord(ch) % 256] += 1
        return normalize(vectors)


class FakeLLM:
    def __init__(self, reviews=('{"score": 9, "suggestion": "好"}',)):
        self.prompts, self.reviews = {}, list(reviews)

    async def stream(self, config, messages):
        self.prompts.setdefault(config["model"], []).append(messages[-1]["content"])
        yield "续写的正文。"

    async def complete(self, config, messages):
        self.prompts.setdefault(config["model"], []).append(messages[-1]["content"])
        return self.reviews.pop(0) if len(self.reviews) > 1 else self.reviews[0]


class Config:
    def load_config(self):
        return {r: {"api_key": "k", "model": r} for r in ("writer", "reviewer")} | \
            {"enable_reviewer": True, "review_mode": "auto"}

    def save_config(self, config):
        pass


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVEL_DATA_DIR", str(tmp_path))
    pm = ProjectManager()
    pm.db_path = str(tmp_path / "t.db")
    memories, styles = ChapterMemoryStore(pm.db_path), StyleStore(pm.db_path)
    rag = RAGEngine(embedder=CharEmbedder())

    async def init():
        await pm.init_db()
        await memories.init_db()
        await styles.init_db()
        pid = await pm.create_project("剑客")
        await pm.import_content(pid, NOVEL)
        for chapter, (summary, hooks) in zip(await pm.get_chapters(pid), MEMORIES):
            await memories.save(pid, ChapterMemory(chapter["id"], summary, ["张三"], [], "f", hooks=hooks))
            rag.index_chapter(pid, chapter["id"], await pm.get_chapter_content(chapter["id"]))
        await styles.save(pid, StyleProfile("短句白描。", [], "手动"))
        return pid

    pid = asyncio.run(init())
    llm = FakeLLM()
    context = ContextBuilder(rag, projects=pm, chapter_store=memories)
    pipeline = RefinePipeline(llm, AppSettings(Config()), context, styles=styles)
    return pid, pm, rag, llm, ContinuationService(pipeline, pm, rag, memories)


def test_new_chapter_prompt(env):
    pid, pm, _, llm, service = env
    request = ContinueRequest(pid, 4, "李四背叛张三。" * 3, outline="张三离开长安", target_chars=800, title="第四章 远行")
    result = asyncio.run(service.continue_text(request))
    writer = llm.prompts["writer"][0]
    assert result.text == "续写的正文。" and result.review.passed
    assert "【前情提要】\n- 第一章 入城：入城\n- 第二章 拜师：拜师\n- 第三章 反目：后文反目" in writer
    assert "【前文埋下的伏笔（可酌情呼应，已经回收的忽略）】" in writer and "王五似乎认识李四" in writer
    assert "【文风要求】\n短句白描。" in writer
    assert "【续写大纲 / 走向】\n张三离开长安" in writer and "【新章节标题】\n第四章 远行" in writer
    assert "【前文（续写从这里接着往下写）】\n李四背叛张三。" in writer and "后文（续写结束时" not in writer
    assert "请接着前文续写约 800 字" in writer


def test_paragraph_continuation_only_uses_earlier_chapters(env):
    pid, _, _, llm, service = env
    request = ContinueRequest(pid, 2, "张三拜王五为师。", following="学会了一套快剑。", target_chars=300)
    asyncio.run(service.continue_text(request))
    writer = llm.prompts["writer"][0]
    assert "【后文（续写结束时要能自然衔接到这里）】\n学会了一套快剑。" in writer
    assert "城门口的那把剑来历不明" in writer  # 第一章的伏笔
    for spoiler in ("王五似乎认识李四", "密信", "背叛", "后文反目"):
        assert spoiler not in writer.split("【前文")[0], spoiler  # 当前章及之后的信息不出现


def test_reviewer_checks_continuation_and_rejection_feeds_back(env):
    pid, _, _, llm, service = env
    llm.reviews = [json.dumps({"score": 3, "suggestion": "节奏太快", "conflicts": ["第二章已拜师，此处却说没有师父"]}),
                   json.dumps({"score": 9, "suggestion": "好"})]
    result = asyncio.run(service.continue_text(ContinueRequest(pid, 4, "前文。", outline="离开长安")))
    reviewer = llm.prompts["reviewer"][0]
    assert "【续写】\n续写的正文。" in reviewer and "【续写大纲】\n离开长安" in reviewer
    assert "衔接" in reviewer and "conflicts" in reviewer and "style_score" in reviewer
    assert result.attempts == 2
    assert "冲突：第二章已拜师，此处却说没有师父" in llm.prompts["writer"][1]


def test_adopting_a_new_chapter_appends_and_indexes(env):
    pid, pm, rag, _, service = env
    cid = asyncio.run(service.adopt_chapter(pid, "第四章 远行", "张三背起行囊，离开了长安城。"))
    chapters = asyncio.run(pm.get_chapters(pid))
    assert chapters[-1]["id"] == cid and chapters[-1]["title"] == "第四章 远行"
    assert chapters[-1]["order_index"] == chapters[-2]["order_index"] + 1
    assert rag.store.chapter_texts(pid, cid) == ["张三背起行囊，离开了长安城。"]
