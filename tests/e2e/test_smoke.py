"""核心流程冒烟测试：导入 → 打开章节 → 单段改写 → 保存 → 全文改写 → 批量 → 聊天。

用例按顺序共享同一个应用和页面（模块级夹具），后一步依赖前一步的状态。
"""
import json
import sqlite3
import time
import urllib.request
from pathlib import Path

import pytest

from fake_llm import REJECT_ONCE, REWRITE_MARK

pytestmark = pytest.mark.e2e

NOVEL = Path(__file__).resolve().parents[1] / "fixtures" / "novel.txt"


def db(app) -> sqlite3.Connection:
    return sqlite3.connect(app.data_dir / "projects" / "novelforge.db")


def chapter_content(app, project_title: str, chapter_prefix: str) -> str:
    row = db(app).execute(
        "SELECT ch.content FROM chapters ch JOIN projects p ON p.id = ch.project_id "
        "WHERE p.title = ? AND ch.title LIKE ?",
        (project_title, f"{chapter_prefix}%"),
    ).fetchone()
    return row[0] if row else ""


def wait_until(predicate, timeout: float = 60, interval: float = 0.5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(interval)
    return predicate()


def test_import_splits_chapters(page, app):
    page.locator("header button:has(i:text-is('add'))").click()
    page.locator("input[type=file]").set_input_files(NOVEL)
    page.get_by_role("button", name="否").click()

    items = page.locator(".chapter-item")
    items.nth(5).wait_for()
    assert items.all_inner_texts() == [
        "【序章】", "第一章 测试章节1", "第二章 测试章节2",
        "第三章 测试章节3", "第四章 测试章节4", "第五章 测试章节5",
    ]


def test_open_chapter_shows_segment_cards(page):
    page.locator(".chapter-item", has_text="第一章").click()
    page.wait_for_function(
        "() => document.querySelectorAll('.segment-card').length === 6"
    )
    first = page.locator(".segment-card textarea").first.input_value()
    assert first.startswith("（1-1）")


def test_rewrite_segment(page):
    page.locator(".segment-card button:has(i:text-is('auto_fix_high'))").first.click()
    page.wait_for_function(
        f"() => [...document.querySelectorAll('.segment-card textarea')]"
        f".some(t => t.value.includes('{REWRITE_MARK}'))"
    )
    revised = page.locator(".segment-card textarea").nth(1).input_value()
    assert revised.startswith(REWRITE_MARK)


def test_reviewer_rejection_retries_with_user_feedback(page, fake_llm):
    page.get_by_placeholder("在此输入全局精修指令...").fill(f"润色{REJECT_ONCE}")
    page.locator(".segment-card button:has(i:text-is('auto_fix_high'))").nth(1).click()

    dialog = page.locator(".q-dialog").filter(has_text="总监意见：质量未达标")
    dialog.wait_for()
    assert dialog.locator("textarea").last.input_value() == "形容词太多"  # 预填审校建议
    dialog.locator("textarea").last.fill("加一点幽默感")
    dialog.get_by_role("button", name="AI 重写").click()

    page.wait_for_function(
        f"() => document.querySelectorAll('.segment-card textarea')[3].value.startsWith('{REWRITE_MARK}')"
    )
    calls = json.load(urllib.request.urlopen(f"{fake_llm}/calls"))
    assert any("【审校意见（必须执行）】\n加一点幽默感" in c["last"] for c in calls)
    page.get_by_placeholder("在此输入全局精修指令...").fill("")


def test_save_persists_to_sqlite(page, app):
    page.get_by_role("button", name="保存").click()
    content = wait_until(lambda: REWRITE_MARK in chapter_content(app, "novel.txt", "第一章"), timeout=10)
    assert content, app.log_tail()


def test_full_text_rewrite(page):
    page.get_by_role("button", name="全文工作台").click()
    page.get_by_placeholder("在此输入全局精修指令...").fill("更生动")
    page.get_by_role("button", name="AI 全文重写").click()
    page.get_by_role("button", name="执行").click()  # 军师报告确认
    page.wait_for_function(
        f"() => [...document.querySelectorAll('.full-height-textarea textarea')]"
        f".some(t => t.value.startsWith('{REWRITE_MARK}'))"
    )


def test_batch_creates_backup_project(page, app):
    page.get_by_role("button", name="分段精修").click()
    page.get_by_role("button", name="批量").click()
    page.get_by_role("button", name="启动").click()

    def batch_done():
        row = db(app).execute(
            "SELECT world_settings FROM projects WHERE title = 'novel.txt (批量副本)'"
        ).fetchone()
        return row and '"last_polished_chapter_id": null' not in row[0]

    assert wait_until(batch_done), app.log_tail()


@pytest.mark.xfail(strict=True, reason="已知 bug：批量把改写写回了原项目，副本保持原样")
def test_batch_rewrites_the_backup_not_the_original(app):
    backup = chapter_content(app, "novel.txt (批量副本)", "第一章")
    assert backup.count(REWRITE_MARK) == 6


def test_chat_answers(page):
    page.locator("header button:has(i:text-is('hub'))").click()
    page.get_by_placeholder("输入问题...").fill("这一章讲了什么")
    page.get_by_role("button", name="发送").click()
    page.wait_for_function(
        f"() => [...document.querySelectorAll('.chat-ai')]"
        f".some(b => b.innerText.includes('{REWRITE_MARK}'))"
    )
