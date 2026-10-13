"""批量精修：按章保存与记录进度、停止 / 出错时不保存半章、副本映射、断点续跑。"""
import asyncio

import pytest

from src.core.project_manager import ProjectManager
from src.llm import LLMError
from src.services.batch import BatchService, join_paragraphs, split_paragraphs
from src.services.refine import RefineResult, Review

NOVEL = "第一章 开端\n甲一。\n甲二。\n第二章 发展\n乙一。\n乙二。\n第三章 高潮\n丙一。\n"


class FakeRefine:
    def __init__(self, fail_on: str = "", output=lambda text: f"改：{text}", review_error: str = ""):
        self.fail_on, self.output, self.review_error = fail_on, output, review_error
        self.requests = []

    async def refine(self, request, on_text=None, on_reject=None):
        self.requests.append(request)
        if self.fail_on and request.text == self.fail_on:
            raise LLMError("额度不足")
        review = Review(None, "", True, error=self.review_error) if self.review_error else None
        return RefineResult(self.output(request.text), review, 1)


class FakeMemory:
    def __init__(self):
        self.indexed, self.cloned = [], []

    async def aindex_chapter(self, project_id, chapter_id, text):
        self.indexed.append((project_id, chapter_id, text))

    async def aclone_project_memory(self, old, new, chapter_map=None):
        self.cloned.append((old, new, chapter_map))


@pytest.fixture
def setup(tmp_path):
    pm = ProjectManager()
    pm.db_path = str(tmp_path / "t.db")

    async def init():
        await pm.init_db()
        pid = await pm.create_project("书")
        await pm.import_content(pid, NOVEL)
        return pid

    return pm, asyncio.run(init())


def chapters(pm, pid):
    async def load():
        return [(c["title"], await pm.get_chapter_content(c["id"])) for c in await pm.get_chapters(pid)]
    return asyncio.run(load())


def chapter_ids(pm, pid):
    return [c["id"] for c in asyncio.run(pm.get_chapters(pid))]


def test_paragraph_helpers():
    assert split_paragraphs(" 甲 \n\n乙\n  \n") == ["甲", "乙"]
    assert join_paragraphs(["甲", "", "乙"]) == "甲\n\n乙"


def test_rewrites_selected_chapters_and_records_progress(setup):
    pm, pid = setup
    ids = chapter_ids(pm, pid)
    refine, memory = FakeRefine(), FakeMemory()
    progress = []
    outcome = asyncio.run(BatchService(pm, refine, memory).run(pid, ids[:2], "润色", on_progress=progress.append))

    assert (outcome.chapters_done, outcome.chapters_total, outcome.stopped) == (2, 2, False)
    assert chapters(pm, pid) == [
        ("第一章 开端", "改：甲一。\n\n改：甲二。"),
        ("第二章 发展", "改：乙一。\n\n改：乙二。"),
        ("第三章 高潮", "丙一。"),
    ]
    assert asyncio.run(pm.get_progress(pid)) == ids[1]
    assert [r.instruction for r in refine.requests] == ["润色"] * 4
    assert [r.chapter_index for r in refine.requests] == [1, 1, 2, 2]  # 章节位置用于图谱视角
    assert [i[1] for i in memory.indexed] == ids[:2]  # 改写后的章节重新写入记忆
    assert progress[0].fraction == 0 and progress[-1].fraction == 1


def test_stop_discards_unfinished_chapter(setup):
    pm, pid = setup
    ids = chapter_ids(pm, pid)
    refine = FakeRefine()
    outcome = asyncio.run(BatchService(pm, refine).run(pid, ids, should_stop=lambda: len(refine.requests) >= 3))

    assert (outcome.chapters_done, outcome.stopped) == (1, True)
    assert chapters(pm, pid)[1] == ("第二章 发展", "乙一。\n乙二。")  # 只改了一段的第二章不保存
    assert asyncio.run(pm.get_progress(pid)) == ids[0]


def test_llm_error_stops_and_reports(setup):
    pm, pid = setup
    ids = chapter_ids(pm, pid)
    outcome = asyncio.run(BatchService(pm, FakeRefine(fail_on="乙二。")).run(pid, ids))
    assert (outcome.chapters_done, outcome.stopped, outcome.error) == (1, True, "额度不足")
    assert chapters(pm, pid)[1][1] == "乙一。\n乙二。"


def test_empty_output_keeps_original_and_review_errors_are_counted(setup):
    pm, pid = setup
    ids = chapter_ids(pm, pid)
    refine = FakeRefine(output=lambda text: "" if text == "甲一。" else f"改：{text}", review_error="超时")
    outcome = asyncio.run(BatchService(pm, refine).run(pid, ids[:1]))
    assert chapters(pm, pid)[0][1] == "甲一。\n\n改：甲二。"
    assert outcome.review_errors == 2


def test_backup_maps_chapters_and_leaves_original_untouched(setup, tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVEL_DATA_DIR", str(tmp_path))  # 副本会复制图谱文件（此处没有图谱）
    pm, pid = setup
    asyncio.run(pm.save_progress(pid, chapter_ids(pm, pid)[0]))
    memory = FakeMemory()
    service = BatchService(pm, FakeRefine(), memory)
    backup, mapping = asyncio.run(service.make_backup(pid))

    original_ids = chapter_ids(pm, pid)
    assert list(mapping) == original_ids and list(mapping.values()) == chapter_ids(pm, backup)
    assert memory.cloned == [(pid, backup, mapping)]  # 记忆里的章节 id 也换成副本的

    assert [p["id"] for p in asyncio.run(pm.get_backups(pid))] == [backup]
    assert asyncio.run(pm.get_backups(backup)) == []

    assert asyncio.run(pm.get_progress(backup)) is None  # 副本的批量进度从头开始
    asyncio.run(service.run(backup, [mapping[original_ids[0]]]))
    assert chapters(pm, backup)[0][1].startswith("改：")
    assert chapters(pm, pid)[0][1] == "甲一。\n甲二。"


def test_remaining_chapters_resume_after_progress(setup):
    pm, pid = setup
    ids = chapter_ids(pm, pid)
    service = BatchService(pm, FakeRefine())
    assert [c["id"] for c in asyncio.run(service.remaining_chapters(pid))] == ids  # 没有进度：全部

    asyncio.run(service.run(pid, ids[:1]))
    assert [c["id"] for c in asyncio.run(service.remaining_chapters(pid))] == ids[1:]


def test_resume_does_not_skip_chapters_before_a_single_chapter_run(setup):
    pm, pid = setup
    ids = chapter_ids(pm, pid)
    service = BatchService(pm, FakeRefine())
    asyncio.run(service.run(pid, ids[1:2]))  # 只精修了第二章（“当前章”范围）
    assert [c["id"] for c in asyncio.run(service.remaining_chapters(pid))] == [ids[0], ids[2]]


def test_rejected_reviews_are_counted(setup):
    pm, pid = setup

    class Rejecting(FakeRefine):
        async def refine(self, request, on_text=None, on_reject=None):
            return RefineResult(f"改：{request.text}", Review(4, "太平淡", False), 3)

    outcome = asyncio.run(BatchService(pm, Rejecting()).run(pid, chapter_ids(pm, pid)[:1]))
    assert (outcome.review_rejected, outcome.review_errors) == (2, 0)
    assert chapters(pm, pid)[0][1] == "改：甲一。\n\n改：甲二。"  # 保留最后一次改写


def test_empty_chapter_is_skipped_without_error(setup):
    pm, pid = setup
    ids = chapter_ids(pm, pid)
    asyncio.run(pm.update_chapter_content(ids[0], ""))
    assert asyncio.run(pm.get_chapter_content(ids[0])) == ""
    assert asyncio.run(pm.get_chapter_content("missing")) is None
    outcome = asyncio.run(BatchService(pm, FakeRefine()).run(pid, ids[:1]))
    assert outcome.chapters_done == 1 and not outcome.error


def test_same_project_cannot_run_two_batches_at_once(setup):
    """两个标签页同时对同一项目跑批量：第二个直接返回错误，不会互相覆盖。"""
    pm, pid = setup
    ids = chapter_ids(pm, pid)

    class Slow(FakeRefine):
        async def refine(self, request, on_text=None, on_reject=None):
            await asyncio.sleep(0.05)
            return await super().refine(request)

    service = BatchService(pm, Slow())

    async def both():
        return await asyncio.gather(service.run(pid, ids[:1]), service.run(pid, ids[:1]))

    first, second = asyncio.run(both())
    assert first.chapters_done == 1 and not first.error
    assert second.error and second.chapters_done == 0
    assert not service.is_running(pid)  # 结束后可以再跑


def test_chapter_saved_during_rewrite_keeps_the_manual_edit(setup):
    """不建副本的批量改写期间，用户（可能在另一个标签页）保存了正在改写的章节：保留手动修改，不被改写结果覆盖。"""
    pm, pid = setup
    ids = chapter_ids(pm, pid)

    class SaveMidway(FakeRefine):
        async def refine(self, request, on_text=None, on_reject=None):
            if request.text == "乙一。":
                await pm.update_chapter_content(ids[1], "手动改过的第二章。")
            return await super().refine(request)

    outcome = asyncio.run(BatchService(pm, SaveMidway()).run(pid, ids))
    assert outcome.conflicts == ["第二章 发展"] and outcome.chapters_done == 2 and not outcome.stopped
    assert chapters(pm, pid)[1] == ("第二章 发展", "手动改过的第二章。")
    assert chapters(pm, pid)[2] == ("第三章 高潮", "改：丙一。")  # 其余章节照常改写
    remaining = asyncio.run(BatchService(pm, FakeRefine()).remaining_chapters(pid))
    assert [c["id"] for c in remaining] == [ids[1]]  # 续跑时重新精修这一章


def test_conditional_update_only_writes_unchanged_content(setup):
    pm, pid = setup
    first = chapter_ids(pm, pid)[0]
    assert not asyncio.run(pm.update_chapter_content(first, "新", expected="不是当前内容"))
    assert asyncio.run(pm.get_chapter_content(first)) == "甲一。\n甲二。"
    assert asyncio.run(pm.update_chapter_content(first, "新", expected="甲一。\n甲二。"))
    assert asyncio.run(pm.get_chapter_content(first)) == "新"


def test_chapter_memory_is_updated_before_the_next_chapter(setup):
    """整理过记忆的项目：每章改写保存后先更新它的章节记忆，再改下一章，后面章节的参考资料跟上前面的改动。"""
    pm, pid = setup
    ids = chapter_ids(pm, pid)
    log = []

    class Refine(FakeRefine):
        async def refine(self, request, on_text=None, on_reject=None):
            log.append(("改写", request.text))
            return await super().refine(request)

    class Store:
        async def has_any(self, project_id):
            return True

    class ChapterMemory:
        async def update(self, project_id, chapter_ids=None):
            log.append(("记忆", chapter_ids))
            if ids[0] in chapter_ids:
                raise LLMError("额度不足")  # 整理失败不中断批量
            return 1

    outcome = asyncio.run(BatchService(pm, Refine(), chapter_store=Store(), chapter_memory=ChapterMemory())
                          .run(pid, ids[:2]))
    assert outcome.chapters_done == 2 and not outcome.error
    assert log == [("改写", "甲一。"), ("改写", "甲二。"), ("记忆", {ids[0]}),
                   ("改写", "乙一。"), ("改写", "乙二。"), ("记忆", {ids[1]})]


def test_backup_drops_a_graph_cached_before_the_copy_finished(setup, tmp_path, monkeypatch):
    """副本先建项目、后复制图谱：期间另一个标签页打开副本会缓存空图谱，复制完要让它重新读取。"""
    from src.core.managers import GraphStore

    monkeypatch.setenv("RENOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("src.core.managers.GraphEngine", lambda project_id: object())
    pm, pid = setup
    graphs = GraphStore()
    service = BatchService(pm, FakeRefine(), graphs=graphs)
    original = pm.duplicate_project

    async def duplicate_and_open(project_id, suffix):
        backup = await original(project_id, suffix)
        graphs.get(backup)  # 另一个标签页此时打开了副本
        duplicate_and_open.backup = backup
        return backup

    monkeypatch.setattr(pm, "duplicate_project", duplicate_and_open)
    backup, _ = asyncio.run(service.make_backup(pid))
    assert backup == duplicate_and_open.backup and backup not in graphs._engines
