"""会话的后台任务：章节记忆的待办按项目排队且都会被处理；批量改写后刷新记忆与图谱。用假服务，不启动界面。"""
import asyncio
from types import SimpleNamespace

import pytest

from src.services.batch import BatchOutcome
from src.ui.session import Session


class FakeChapterMemory:
    def __init__(self):
        self.calls = []
        self.session = None

    async def update(self, project_id, on_progress=None, chapter_ids=None):
        self.calls.append((project_id, chapter_ids))
        if project_id == "A" and len(self.calls) == 1:
            # 整理 A 的过程中，用户切到 B 并保存
            await self.session.bg_update_memory("B", {"b1"})
        await asyncio.sleep(0)
        return 1


def test_pending_memory_work_for_other_projects_is_drained():
    memory = FakeChapterMemory()
    session = Session(SimpleNamespace(chapter_memory=memory))
    memory.session = session

    asyncio.run(session.bg_update_memory("A"))
    assert memory.calls == [("A", None), ("B", {"b1"})]
    assert not session.state.memory_task_running and session.state.memory_pending == {}


def test_batch_refreshes_memories_and_graph_of_rewritten_chapters(monkeypatch):
    async def run(pid, ids, instruction, on_progress=None, should_stop=None):
        return BatchOutcome(pid, 1, 1)

    async def has_any(pid):
        return True

    built = SimpleNamespace(is_built=lambda: True)
    services = SimpleNamespace(batch=SimpleNamespace(run=run), chapter_store=SimpleNamespace(has_any=has_any),
                               graphs=SimpleNamespace(get=lambda pid: built))
    session = Session(services)
    session.state.current_project_id = "P"
    started = []

    async def record(name, pid, ids):
        started.append((name, pid, ids))

    monkeypatch.setattr(session, "bg_update_memory", lambda pid, ids: record("memory", pid, ids))
    monkeypatch.setattr(session, "bg_build_graph", lambda pid, ids: record("graph", pid, ids))
    monkeypatch.setattr("src.ui.session.ui.notify", lambda *a, **k: None)

    async def go():
        await session.run_batch(["c1"], create_backup=False)
        await asyncio.sleep(0)

    asyncio.run(go())
    assert sorted(started) == [("graph", "P", {"c1"}), ("memory", "P", {"c1"})]


class FakeStore:
    async def has_any(self, pid):
        return False


class FakeProjects:
    def __init__(self):
        self.saved = {}

    async def update_chapter_content(self, cid, text, expected=None):
        self.saved[cid] = text
        return True


class FakeRag:
    async def aindex_chapter(self, pid, cid, text):
        pass


def continuation_session(monkeypatch):
    services = SimpleNamespace(pm=FakeProjects(), rag=FakeRag(), chapter_store=FakeStore(),
                               graphs=SimpleNamespace(get=lambda pid: None))
    session = Session(services)
    session.state.current_project_id, session.state.current_chapter_id = "P", "c1"
    monkeypatch.setattr("src.ui.session.ui.notify", lambda *a, **k: None)

    async def no_memory(pid, ids):
        pass

    monkeypatch.setattr(session, "bg_update_memory", no_memory)
    return session


def test_adopting_paragraphs_in_full_text_mode_keeps_them(monkeypatch):
    from src.services.continuation import ContinueRequest

    session = continuation_session(monkeypatch)
    state = session.state
    state.view_mode, state.full_text_draft = "full", "甲。\n\n乙。"
    request = ContinueRequest("P", 1, "甲。", "乙。", mode="paragraph", chapter_id="c1", after=1)

    async def go():
        await session.adopt_continuation(request, "续一。\n续二。")
        await asyncio.sleep(0)

    asyncio.run(go())
    assert session.services.pm.saved["c1"] == "甲。\n\n续一。\n\n续二。\n\n乙。"


def test_preparing_a_continuation_does_not_touch_paragraph_history(monkeypatch):
    """全文工作台里打开续写、生成草稿：续写位置按全文草稿计算，但不改动各段的原文、候选与撤销历史。"""
    from src.services import segments as segment_ops
    from src.services.segments import split_text

    session = continuation_session(monkeypatch)
    state = session.state
    state.segments = split_text("原文甲。\n原文乙。")
    segment_ops.propose(state.segments[0], "改写甲。")
    kept = [dict(seg) for seg in state.segments]
    state.view_mode, state.full_text_draft = "full", "改写甲。\n\n原文乙。\n\n全文里新加的一段。"

    async def chapter_index():
        return 1

    monkeypatch.setattr(session, "chapter_index", chapter_index)
    assert len(session.working_segments()) == 3
    request = asyncio.run(session.continue_request("paragraph", after=3))
    assert request.preceding == "改写甲。\n\n原文乙。\n\n全文里新加的一段。" and request.after == 3
    assert [dict(seg) for seg in state.segments] == kept


def test_adopting_refuses_when_target_changed(monkeypatch):
    from src.services.continuation import ContinueRequest
    from src.services.segments import split_text

    session = continuation_session(monkeypatch)
    session.state.segments = split_text("甲。\n乙。")
    stale = ContinueRequest("P", 1, "别的前文。", "乙。", mode="paragraph", chapter_id="c1", after=1)
    other_chapter = ContinueRequest("P", 1, "甲。", "乙。", mode="paragraph", chapter_id="c2", after=1)
    for request in (stale, other_chapter):
        with pytest.raises(ValueError):
            asyncio.run(session.adopt_continuation(request, "续。"))
    assert session.services.pm.saved == {}


def test_graph_updates_are_queued_across_projects():
    calls = []
    session = None

    async def update(engine, project, on_progress=None, chapter_ids=None):
        calls.append((project, chapter_ids))
        if len(calls) == 1:
            await session.bg_build_graph("B", {"b1"})  # 更新 A 时又保存了 B
        return 0

    services = SimpleNamespace(graphs=SimpleNamespace(get=lambda pid: object()), graph=SimpleNamespace(update=update))
    session = Session(services)
    asyncio.run(session.bg_build_graph("A"))
    assert calls == [("A", None), ("B", {"b1"})] and session.state.graph_pending == {}


def test_memory_update_does_not_redraw_the_style_panel():
    """整理完当前项目的记忆只刷新记忆和角色面板：文风面板里正在编辑、还没保存的内容不能被重绘掉。"""
    class Memory:
        async def update(self, project_id, on_progress=None, chapter_ids=None):
            return 1

    session = Session(SimpleNamespace(chapter_memory=Memory()))
    session.state.current_project_id = "P"
    refreshed = []

    def view(name):
        async def refresh():
            refreshed.append(name)
        return SimpleNamespace(refresh=refresh)

    session.memory_view, session.character_view, session.style_view = view("记忆"), view("角色"), view("文风")
    asyncio.run(session.bg_update_memory("P"))
    assert refreshed == ["记忆", "角色"]

    asyncio.run(session.refresh_memory_ui(include_style=True))  # 切换项目时
    assert refreshed[2:] == ["记忆", "角色", "文风"]
