"""多个标签页各自独立：打开的章节、编辑模式、改写与保存互不干扰。"""
import sqlite3
from pathlib import Path

import pytest
from playwright.sync_api import expect

from fake_llm import REWRITE_MARK

pytestmark = pytest.mark.e2e

NOVEL = Path(__file__).resolve().parents[1] / "fixtures" / "novel.txt"


def open_tab(browser, app):
    page = browser.new_page(viewport={"width": 1500, "height": 950})
    page.set_default_timeout(30_000)
    page.goto(app.url)
    return page


def open_chapter(page, title: str, first_paragraph: str):
    page.locator(".chapter-item", has_text=title).click()
    expect(page.locator(".segment-card textarea").first).to_have_value(first_paragraph_prefix(first_paragraph))


def first_paragraph_prefix(prefix: str):
    import re
    return re.compile("^" + re.escape(prefix))


def chapter_content(app, title_prefix: str) -> str:
    con = sqlite3.connect(app.data_dir / "projects" / "novelforge.db")
    row = con.execute("SELECT content FROM chapters WHERE title LIKE ?", (f"{title_prefix}%",)).fetchone()
    return row[0]


def test_two_tabs_do_not_interfere(browser, app):
    tab_a = open_tab(browser, app)
    tab_a.locator("header button:has(i:text-is('add'))").click()
    tab_a.locator("input[type=file]").set_input_files(NOVEL)
    tab_a.get_by_role("button", name="否").click()
    tab_a.locator(".chapter-item").nth(5).wait_for()

    tab_b = open_tab(browser, app)  # 新标签页会自动打开最近的项目
    tab_b.locator(".chapter-item").nth(5).wait_for()

    open_chapter(tab_a, "第一章", "（1-1）")
    open_chapter(tab_b, "第二章", "（2-1）")
    expect(tab_a.locator(".segment-card textarea").first).to_have_value(first_paragraph_prefix("（1-1）"))

    # B 切到全文模式，A 仍是分段模式
    tab_b.get_by_role("button", name="全文工作台").click()
    expect(tab_b.locator(".segment-card")).to_have_count(0)
    expect(tab_a.locator(".segment-card")).to_have_count(6)

    # A 改写并保存第一章，不影响 B 正在编辑的第二章
    tab_a.locator(".segment-card button:has(i:text-is('auto_fix_high'))").first.click()
    tab_a.wait_for_function("() => !document.querySelector('.segment-card .q-btn .q-spinner')")
    expect(tab_a.locator(".segment-card textarea").nth(1)).to_have_value(first_paragraph_prefix(REWRITE_MARK))
    tab_a.get_by_role("button", name="保存").click()
    tab_a.get_by_text("已保存").wait_for()

    assert chapter_content(app, "第一章").startswith(REWRITE_MARK)
    assert REWRITE_MARK not in chapter_content(app, "第二章")
    assert tab_b.locator(".full-height-textarea textarea").nth(1).input_value().startswith("（2-1）")

    tab_a.close()
    tab_b.close()
