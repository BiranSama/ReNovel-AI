"""段落版本：候选默认采纳、撤销先退回上一个候选再退回原文、重新采纳；章节保存留下历史版本。"""
import asyncio

from src.core.project_manager import MAX_VERSIONS, ProjectManager
from src.services import segments


def test_split_and_merge_use_adopted_candidates():
    segs = segments.split_text("甲。\n\n乙。\n")
    assert [s["original"] for s in segs] == ["甲。", "乙。"]
    segments.propose(segs[0], "甲改。")
    assert segments.merge(segs) == "甲改。\n\n乙。"


def test_undo_steps_back_through_candidates_then_original():
    seg = segments.new_segment("原文。")
    segments.propose(seg, "候选一。")
    segments.propose(seg, "候选二。")
    assert segments.current(seg) == "候选二。" and segments.can_undo(seg)

    assert segments.undo(seg) and segments.current(seg) == "候选一。"
    assert segments.undo(seg) and segments.current(seg) == "原文。"
    assert seg["revised"] == "候选一。" and segments.can_adopt(seg)  # 候选保留，可重新采纳
    assert not segments.can_undo(seg) and not segments.undo(seg)

    segments.adopt(seg)
    assert segments.current(seg) == "候选一。"


def test_manual_edit_counts_as_adopted_and_empty_candidate_falls_back():
    seg = segments.new_segment("原文。")
    segments.edit(seg, "手改。")
    assert segments.current(seg) == "手改。"
    segments.edit(seg, "  ")
    assert segments.current(seg) == "原文。" and not segments.can_adopt(seg)


def test_same_candidate_twice_is_not_stacked():
    seg = segments.new_segment("原文。")
    segments.propose(seg, "候选。")
    segments.propose(seg, "候选。")
    assert seg["history"] == []


def test_old_segments_without_fields_still_merge():
    assert segments.merge([{"original": "甲。", "revised": "甲改。"}, {"original": "乙。", "revised": ""}]) == "甲改。\n\n乙。"


def test_saving_keeps_previous_versions(tmp_path):
    pm = ProjectManager()
    pm.db_path = str(tmp_path / "t.db")

    async def run():
        await pm.init_db()
        pid = await pm.create_project("书")
        await pm.import_content(pid, "第一章 开端\n原文。\n")
        cid = (await pm.get_chapters(pid))[0]["id"]
        await pm.update_chapter_content(cid, "原文。")  # 内容没变：不留版本
        await pm.update_chapter_content(cid, "第二版。")
        await pm.update_chapter_content(cid, "第三版。")
        first = await pm.get_chapter_versions(cid)
        for i in range(MAX_VERSIONS + 5):
            await pm.update_chapter_content(cid, f"第{i + 4}版。")
        return first, await pm.get_chapter_versions(cid)

    first, later = asyncio.run(run())
    assert [v["content"] for v in first] == ["第二版。", "原文。"]  # 最新的在前
    assert len(later) == MAX_VERSIONS and later[0]["content"] == f"第{MAX_VERSIONS + 7}版。"
