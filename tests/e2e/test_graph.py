"""导入时选择整理全书：后台先整理章节记忆，再抽取人物关系，结果落盘并能在右侧栏查看。

单独成模块，以便使用一个全新的应用实例。
"""
import json
import sqlite3
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

NOVEL = Path(__file__).resolve().parents[1] / "fixtures" / "novel.txt"


def test_build_graph_on_import(page, app):
    page.locator("header button:has(i:text-is('add'))").click()
    page.locator("input[type=file]").set_input_files(NOVEL)
    page.get_by_role("button", name="是").click()

    deadline = time.time() + 90
    graph = None
    while time.time() < deadline:
        files = list((app.data_dir / "projects").glob("*_graph.json"))
        if files:
            graph = json.loads(files[0].read_text(encoding="utf-8"))
            if len(graph["graph"].get("extracted", {})) == 6:  # 6 章都处理完（序章太短，记录指纹但不调用模型）
                break
        time.sleep(1)

    assert graph and graph["links"], app.log_tail()
    assert {n["id"] for n in graph["nodes"]} == {"张三", "李四"}
    assert len(graph["links"]) == 1  # 每章都抽到同一条关系，只保留一条


def test_chapter_memories_are_built_and_shown(page, app):
    con = sqlite3.connect(app.data_dir / "projects" / "novelforge.db")
    rows = con.execute("SELECT c.title, m.summary, m.characters FROM chapter_memories m "
                       "JOIN chapters c ON c.id = m.chapter_id ORDER BY c.order_index").fetchall()
    assert len(rows) == 6  # 记忆先于图谱整理，图谱完成时记忆已全部写入
    preface, first = rows[0], rows[1]
    assert preface[1] == ""  # 序章太短，不调用模型
    assert first[1] == "第一章 测试章节1：张三与李四在咖啡馆叙旧。" and json.loads(first[2]) == ["张三", "李四"]

    page.locator("header button:has(i:text-is('hub'))").click()
    page.get_by_role("tab", name="记忆").click()
    item = page.locator(".memory-item", has_text="第一章 测试章节1")
    expect(item).to_contain_text("张三与李四在咖啡馆叙旧")
    item.click()
    expect(item.get_by_text("• 两人聊起往事")).to_be_visible()


def test_character_profiles_can_be_viewed_and_edited(page, app):
    page.get_by_role("tab", name="角色").click()
    zhang = page.locator(".character-item", has_text="张三")
    expect(zhang).to_contain_text("又名 三哥")
    zhang.click()

    dialog = page.locator(".character-dialog")
    expect(dialog).to_contain_text("第一章 测试章节1：第一章 测试章节1末与李四和好")
    expect(dialog).to_contain_text("张三 朋友 李四")  # 人物关系来自图谱
    dialog.get_by_label("备注（改写和审校时会参考）").fill("左撇子")
    dialog.get_by_role("button", name="保存").click()
    expect(dialog).to_be_hidden()

    con = sqlite3.connect(app.data_dir / "projects" / "novelforge.db")
    assert con.execute("SELECT notes FROM character_overrides WHERE name = '张三'").fetchone() == ("左撇子",)
    expect(page.locator(".character-item", has_text="张三").locator("i", has_text="edit")).to_be_visible()
