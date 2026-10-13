"""文风：套用预设、手动修改后立即用于改写，从原文提炼。"""
import json
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

NOVEL = Path(__file__).resolve().parents[1] / "fixtures" / "novel.txt"


def writer_prompts(fake_llm):
    calls = json.load(urllib.request.urlopen(f"{fake_llm}/calls"))
    return [c["last"] for c in calls if c["last"].endswith("请直接输出改写后的正文。")]  # 审校提示词里也会引用改写结果


def rewrite_first_segment(page, fake_llm):
    """点精修并等这一次改写完成：先等假服务收到新的 Writer 请求，再等加载动画消失（含审校）。

    这一段可能已经是「已采纳」状态，只看状态或加载动画会在新请求发出前就判定完成。
    """
    before = len(writer_prompts(fake_llm))
    card = page.locator(".segment-card").first
    card.locator("button:has(i:text-is('auto_fix_high'))").click()
    deadline = time.time() + 30
    while len(writer_prompts(fake_llm)) == before and time.time() < deadline:
        time.sleep(0.2)
    assert len(writer_prompts(fake_llm)) > before, "没有发出新的改写请求"
    page.wait_for_function("() => !document.querySelector('.segment-card .q-btn .q-spinner')")
    expect(card.locator(".segment-status")).to_have_text("已采纳")


def test_open_style_panel(page):
    page.locator("header button:has(i:text-is('add'))").click()
    page.locator("input[type=file]").set_input_files(NOVEL)
    page.get_by_role("button", name="否").click()
    page.locator(".chapter-item", has_text="第一章").click()
    page.wait_for_function("() => document.querySelectorAll('.segment-card').length === 6")
    page.locator("header button:has(i:text-is('hub'))").click()
    page.get_by_role("tab", name="文风").click()


def test_preset_is_used_by_next_rewrite(page, fake_llm):
    page.locator(".style-preset").click()
    page.get_by_role("option", name="白描").click()
    expect(page.locator(".style-description textarea")).to_have_value(
        "零度叙述，克制冷静。多用短句和动作、对白推进情节，不直接写人物心理和情绪，少用形容词与比喻，情绪通过细节和动作侧面流露。")
    rewrite_first_segment(page, fake_llm)
    assert "【文风要求】\n零度叙述" in writer_prompts(fake_llm)[-1]


def test_edited_description_takes_effect_immediately(page, fake_llm):
    page.locator(".style-description textarea").fill("测试：全部用短句。")
    page.get_by_role("button", name="保存文风").click()
    expect(page.locator(".style-panel")).to_contain_text("来源：预设：白描")
    rewrite_first_segment(page, fake_llm)
    assert "【文风要求】\n测试：全部用短句。" in writer_prompts(fake_llm)[-1]


def test_extract_from_book(page):
    page.get_by_role("button", name="从原文提炼").click()
    expect(page.locator(".style-description textarea")).to_have_value("测试文风：短句白描。")
    expect(page.locator(".style-panel")).to_contain_text("来源：提炼自原文")
    expect(page.locator(".style-sample")).to_have_count(2)
