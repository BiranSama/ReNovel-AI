"""段落版本与章节历史：AI 候选默认采纳、撤销退回原文、重新采纳、手动修改、恢复历史版本。"""
import sqlite3
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

from fake_llm import REWRITE_MARK

pytestmark = pytest.mark.e2e

NOVEL = Path(__file__).resolve().parents[1] / "fixtures" / "novel.txt"


def chapter_one(app) -> str:
    con = sqlite3.connect(app.data_dir / "projects" / "novelforge.db")
    return con.execute("SELECT content FROM chapters WHERE title LIKE '第一章%'").fetchone()[0]


def save_and_wait(page, app, predicate):
    page.get_by_role("button", name="保存").click()
    deadline = time.time() + 10
    while time.time() < deadline and not predicate(chapter_one(app)):
        time.sleep(0.2)
    assert predicate(chapter_one(app)), chapter_one(app)[:200]


def card(page, index):
    return page.locator(".segment-card").nth(index)


def test_open_chapter(page):
    page.locator("header button:has(i:text-is('add'))").click()
    page.locator("input[type=file]").set_input_files(NOVEL)
    page.get_by_role("button", name="否").click()
    page.locator(".chapter-item", has_text="第一章").click()
    page.wait_for_function("() => document.querySelectorAll('.segment-card').length === 6")


def test_rewrite_is_adopted_and_can_be_undone(page, app):
    first = card(page, 0)
    first.locator("button:has(i:text-is('auto_fix_high'))").click()
    expect(first.locator(".segment-status")).to_have_text("已采纳")
    assert first.locator("textarea").nth(1).input_value().startswith(REWRITE_MARK)

    first.locator("button:has(i:text-is('undo'))").click()  # 只有一个候选：退回原文
    expect(first.locator(".segment-status")).to_have_text("未采纳（保存原文）")
    expect(first.locator("button:has(i:text-is('undo'))")).to_be_disabled()
    save_and_wait(page, app, lambda content: content.startswith("（1-1）"))
    assert REWRITE_MARK not in chapter_one(app)

    first.get_by_role("button", name="采纳").click()
    expect(first.locator(".segment-status")).to_have_text("已采纳")
    save_and_wait(page, app, lambda content: content.startswith(REWRITE_MARK))


def test_manual_edit_of_candidate_is_saved(page, app):
    second = card(page, 1).locator("textarea").nth(1)
    second.fill("手动改写的第二段。")
    expect(card(page, 1).locator(".segment-status")).to_have_text("已采纳")
    save_and_wait(page, app, lambda content: "手动改写的第二段。" in content)


def test_restore_previous_version(page, app):
    page.locator("button:has(i:text-is('restore'))").click()
    items = page.locator(".versions-dialog .version-item")
    expect(items).to_have_count(3)  # 三次有变化的保存（第一次统一了段落格式）各留下一个旧版本
    items.last.get_by_role("button", name="恢复").click()  # 最早的版本：导入时的原文
    expect(card(page, 0).locator("textarea").first).to_have_value(
        "（1-1）张三走进咖啡馆，看见李四坐在窗边，两人聊起了往事，气氛渐渐变得微妙。")
    save_and_wait(page, app, lambda content: REWRITE_MARK not in content and "手动改写" not in content)

    page.locator("button:has(i:text-is('restore'))").click()
    expect(items).to_have_count(4)  # 恢复前的内容也留作历史版本，可以再撤回
