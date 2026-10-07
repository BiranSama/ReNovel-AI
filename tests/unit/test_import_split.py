"""导入分章的特征测试：锁定 ProjectManager.import_content 的现有行为，重构时必须保持。

标记为 xfail(strict=True) 的是已知问题，修复后 xfail 会变成失败，提醒移除标记。
"""
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


@pytest.mark.xfail(strict=True, reason="已知问题：少于 3 个标题时不分章，整本书成为一个“全文”章节")
def test_two_chapters_are_split(pm):
    text = "第一章 开端\n" + BODY * 2 + "第二章 发展\n" + BODY * 2
    assert titles(pm, text) == ["第一章 开端", "第二章 发展"]


@pytest.mark.xfail(strict=True, reason="已知 bug：正文不足 10 字的章节被静默丢弃（数据丢失）")
def test_short_chapter_is_kept(pm):
    text = "第一章 开端\n短。\n第二章 发展\n" + BODY * 2 + "第三章 高潮\n" + BODY * 2
    assert titles(pm, text) == ["第一章 开端", "第二章 发展", "第三章 高潮"]


@pytest.mark.xfail(strict=True, reason="已知 bug：以“第X章”开头的正文行被当成标题")
def test_body_line_starting_with_chapter_word_is_not_a_heading(pm):
    text = ("第一章 开端\n" + BODY + "第三章里埋下的伏笔，此刻终于揭开。\n" + BODY
            + "第二章 发展\n" + BODY * 2 + "第三章 高潮\n" + BODY * 2)
    assert titles(pm, text) == ["第一章 开端", "第二章 发展", "第三章 高潮"]
