"""导入分章：ProjectManager.import_content 端到端写库后的章节结果。"""
import asyncio

import pytest

from src.core.project_manager import ProjectManager

BODY = "　　张三推开门，屋里一片漆黑，只有窗外透进来的月光。\n"


@pytest.fixture
def pm(tmp_path):
    pm = ProjectManager()
    pm.db_path = str(tmp_path / "test.db")
    asyncio.run(pm.init_db())
    return pm


def split(pm, text: str) -> list[tuple[str, int, str]]:
    async def run():
        pid = await pm.create_project("t")
        await pm.import_content(pid, text)
        chapters = await pm.get_chapters(pid)
        return [(c["title"], c["order_index"], await pm.get_chapter_content(c["id"])) for c in chapters]

    return asyncio.run(run())


def titles(pm, text: str) -> list[str]:
    return [title for title, _, _ in split(pm, text)]


def test_chinese_headings_with_preface(pm):
    text = "　　前言：本书纯属虚构。\n第一章 开端\n" + BODY * 2 + "第二章 发展\n" + BODY * 2 + "第三章 高潮\n" + BODY * 2
    chapters = split(pm, text)
    assert [(t, i) for t, i, _ in chapters] == [
        ("【序章】", -1), ("第一章 开端", 0), ("第二章 发展", 1), ("第三章 高潮", 2),
    ]
    assert chapters[0][2] == "前言：本书纯属虚构。"
    assert chapters[1][2].startswith("张三推开门")
    assert "第二章" not in chapters[1][2]


@pytest.mark.parametrize("headings", [
    ["Chapter 1 Start", "Chapter 2 Next", "Chapter 3 End"],
    ["1. 开始", "2. 继续", "3. 结束"],
    ["【楔子】", "【第一回】", "【第二回】"],
    ["第一卷 风起", "第二卷 云涌", "第三卷 雷动"],
])
def test_other_heading_styles(pm, headings):
    text = "".join(f"{h}\n" + BODY * 2 for h in headings)
    assert titles(pm, text) == headings


def test_crlf_and_special_spaces_are_normalized(pm):
    text = "第一章 开端\r\n" + BODY.replace("\n", "\r\n") * 2 + "第二章 发展\r\n" + BODY * 2 + "第三章 高潮\r\n" + BODY * 2
    chapters = split(pm, text)
    assert [t for t, _, _ in chapters] == ["第一章 开端", "第二章 发展", "第三章 高潮"]
    assert "\r" not in chapters[0][2] and "　" not in chapters[0][2]


def test_text_without_headings_becomes_single_chapter(pm):
    assert split(pm, BODY * 3) == [("全文", 0, (BODY * 3).replace("　", " "))]


def test_two_chapters_are_split(pm):
    text = "第一章 开端\n" + BODY * 2 + "第二章 发展\n" + BODY * 2
    assert titles(pm, text) == ["第一章 开端", "第二章 发展"]


def test_short_chapter_is_kept(pm):
    text = "第一章 开端\n短。\n第二章 发展\n" + BODY * 2 + "第三章 高潮\n" + BODY * 2
    chapters = split(pm, text)
    assert [t for t, _, _ in chapters] == ["第一章 开端", "第二章 发展", "第三章 高潮"]
    assert chapters[0][2] == "短。"


def test_single_chapter_heading_still_splits_preface(pm):
    assert titles(pm, "\u3000\u3000楔子内容。\n第一章 开端\n" + BODY) == ["【序章】", "第一章 开端"]


def test_volume_heading_without_body_is_skipped(pm):
    text = "第一卷 风起\n第一章 开端\n" + BODY + "第二章 发展\n" + BODY
    chapters = split(pm, text)
    assert [(t, i) for t, i, _ in chapters] == [("第一章 开端", 0), ("第二章 发展", 1)]


def test_heading_may_end_with_question_mark(pm):
    assert titles(pm, "第一章 他是谁？\n" + BODY + "第二章 真相！\n" + BODY) == ["第一章 他是谁？", "第二章 真相！"]


def test_body_line_starting_with_chapter_word_is_not_a_heading(pm):
    text = ("第一章 开端\n" + BODY + "第三章里埋下的伏笔，此刻终于揭开。\n" + BODY
            + "第二章 发展\n" + BODY * 2 + "第三章 高潮\n" + BODY * 2)
    assert titles(pm, text) == ["第一章 开端", "第二章 发展", "第三章 高潮"]


def test_volume_heading_with_numbered_chapters(pm):
    text = "第一卷 风起\n1. 开始\n" + BODY + "2. 继续\n" + BODY + "3. 结束\n" + BODY
    assert titles(pm, text) == ["1. 开始", "2. 继续", "3. 结束"]


def test_volumes_without_chapter_headings_split_by_volume(pm):
    text = "第一卷 风起\n" + BODY * 2 + "第二卷 云涌\n" + BODY * 2
    assert titles(pm, text) == ["第一卷 风起", "第二卷 云涌"]
