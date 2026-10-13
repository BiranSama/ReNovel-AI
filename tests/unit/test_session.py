"""会话的后台任务：章节记忆的待办按项目排队且都会被处理；批量改写后刷新记忆与图谱。用假服务，不启动界面。"""
import asyncio
from types import SimpleNamespace

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
