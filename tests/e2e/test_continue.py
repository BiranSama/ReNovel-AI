"""阶段 5 的完成标准：续写 → 审校 → 采纳 → 保存 → 记忆更新（新章节与段后续写）。"""
import json
import sqlite3
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import expect

from fake_llm import CONTINUE_MARK, CONTINUE_TEXT, VERY_SLOW

pytestmark = pytest.mark.e2e

NOVEL = Path(__file__).resolve().parents[1] / "fixtures" / "novel.txt"


def db(app):
    return sqlite3.connect(app.data_dir / "projects" / "novelforge.db")


def wait_until(predicate, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.3)
    return predicate()


def open_dialog(page):
    page.get_by_role("button", name="续写").click()
    dialog = page.locator(".continue-dialog")
    expect(dialog).to_be_visible()
    return dialog


def test_import(page):
    page.locator("header button:has(i:text-is('add'))").click()
    page.locator("input[type=file]").set_input_files(NOVEL)
    page.get_by_role("button", name="否").click()
    page.locator(".chapter-item").nth(5).wait_for()


def test_continue_new_chapter_then_adopt_updates_memory(page, app, fake_llm):
    dialog = open_dialog(page)
    dialog.get_by_label("新章节标题").fill("第六章 告别")
    dialog.get_by_label("大纲 / 走向（可选）").fill("两人告别")
    dialog.get_by_role("button", name="生成").click()
    expect(dialog.locator(".continue-draft textarea")).to_have_value(CONTINUE_MARK + CONTINUE_TEXT)
    expect(dialog.locator(".continue-review")).to_have_text("审校 9 分")
    assert db(app).execute("SELECT COUNT(*) FROM chapters").fetchone()[0] == 6  # 草稿还没保存

    calls = json.load(urllib.request.urlopen(f"{fake_llm}/calls"))
    assert any("【续写大纲 / 走向】\n两人告别" in c["last"] for c in calls)
    assert any("【续写】" in c["last"] and "请评分" in c["last"] for c in calls)  # 经过审校

    dialog.get_by_role("button", name="采纳").click()
    expect(dialog).to_be_hidden()
    expect(page.locator(".chapter-item", has_text="第六章 告别")).to_be_visible()
    expect(page.locator(".segment-card textarea").first).to_have_value(
        CONTINUE_MARK + "张三与李四在门口告别，约定明日再见。")

    row = db(app).execute("SELECT id, content FROM chapters WHERE title = '第六章 告别'").fetchone()
    assert row and row[1].startswith(CONTINUE_MARK)
    summary = wait_until(lambda: db(app).execute(
        "SELECT summary FROM chapter_memories WHERE chapter_id = ?", (row[0],)).fetchone())
    assert summary == ("第六章 告别：张三与李四在咖啡馆叙旧。",)  # 章节记忆已更新
    fragments = sqlite3.connect(app.data_dir / "memory.db").execute(
        "SELECT COUNT(*) FROM fragments WHERE chapter_id = ?", (row[0],)).fetchone()[0]
    assert fragments == 2  # 向量记忆已更新


def test_continue_after_paragraph(page, app):
    page.locator(".chapter-item", has_text="第一章").click()
    page.wait_for_function("() => document.querySelectorAll('.segment-card').length === 6")
    dialog = open_dialog(page)
    dialog.get_by_text("在当前章节某段之后续写").click()
    dialog.get_by_label("在第几段之后（共 6 段）").fill("2")
    dialog.get_by_role("button", name="生成").click()
    expect(dialog.locator(".continue-draft textarea")).to_have_value(CONTINUE_MARK + CONTINUE_TEXT)
    dialog.get_by_role("button", name="采纳").click()
    expect(dialog).to_be_hidden()

    page.wait_for_function("() => document.querySelectorAll('.segment-card').length === 8")
    expect(page.locator(".segment-card").nth(2).locator("textarea").nth(1)).to_have_value(
        CONTINUE_MARK + "张三与李四在门口告别，约定明日再见。")
    content = wait_until(lambda: (lambda r: r and CONTINUE_MARK in r[0] and r[0])(db(app).execute(
        "SELECT content FROM chapters WHERE title LIKE '第一章%'").fetchone()))
    paragraphs = content.split("\n\n")
    assert paragraphs[1].startswith("（1-2）") and paragraphs[2].startswith(CONTINUE_MARK)  # 插在第 2 段之后


def test_changing_the_target_while_generating_blocks_adoption(page, app):
    """生成过程中改了续写方式：生成完的草稿是按原来的位置写的，不能采纳到新的位置。"""
    chapters = db(app).execute("SELECT COUNT(*) FROM chapters").fetchone()[0]
    dialog = open_dialog(page)
    dialog.get_by_label("大纲 / 走向（可选）").fill(f"两人告别{VERY_SLOW}")  # 生成要等几秒
    dialog.get_by_role("button", name="生成").click()
    dialog.get_by_text("在当前章节某段之后续写").click()
    expect(dialog.locator(".continue-review")).to_have_text("生成期间改动了续写位置，请重新生成", timeout=30000)
    expect(dialog.locator(".continue-draft textarea")).to_have_value(CONTINUE_MARK + CONTINUE_TEXT)
    expect(dialog.get_by_role("button", name="采纳")).to_be_disabled()
    dialog.get_by_role("button", name="关闭").click()
    assert db(app).execute("SELECT COUNT(*) FROM chapters").fetchone()[0] == chapters
