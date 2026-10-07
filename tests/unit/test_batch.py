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

    def index_chapter(self, project_id, chapter_id, text):
        self.indexed.append((project_id, chapter_id, text))

    def clone_project_memory(self, old, new):
        self.cloned.append((old, new))


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


def test_backup_maps_chapters_and_leaves_original_untouched(setup):
    pm, pid = setup
    memory = FakeMemory()
    service = BatchService(pm, FakeRefine(), memory)
    backup, mapping = asyncio.run(service.make_backup(pid))

    original_ids = chapter_ids(pm, pid)
    assert list(mapping) == original_ids and list(mapping.values()) == chapter_ids(pm, backup)
    assert memory.cloned == [(pid, backup)]

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
