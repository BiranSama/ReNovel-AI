"""导入非 UTF-8 文件：GBK 正常导入；无法识别的编码给出提示，不创建项目。"""
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

NOVEL = Path(__file__).resolve().parents[1] / "fixtures" / "novel.txt"


def upload(page, name: str, data: bytes) -> None:
    page.locator("header button:has(i:text-is('add'))").click()
    page.locator("input[type=file]").set_input_files({"name": name, "mimeType": "text/plain", "buffer": data})


def project_titles(app) -> list[str]:
    con = sqlite3.connect(app.data_dir / "projects" / "novelforge.db")
    return [row[0] for row in con.execute("SELECT title FROM projects")]


def test_gbk_novel_imports_correctly(page, app):
    upload(page, "gbk.txt", NOVEL.read_text(encoding="utf-8").encode("gbk"))
    page.get_by_role("button", name="否").click()

    items = page.locator(".chapter-item")
    items.nth(5).wait_for()
    assert items.all_inner_texts()[1] == "第一章 测试章节1"
    page.locator(".chapter-item", has_text="第一章").click()
    page.wait_for_function("() => document.querySelectorAll('.segment-card').length === 6")
    assert page.locator(".segment-card textarea").first.input_value().startswith("（1-1）张三走进咖啡馆")


def test_unrecognized_encoding_is_rejected(page, app):
    before = project_titles(app)
    upload(page, "binary.txt", bytes(range(256)) * 4)
    page.get_by_text("无法识别文件编码").wait_for()
    assert project_titles(app) == before
