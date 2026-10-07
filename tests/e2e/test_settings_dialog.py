"""设置弹窗：测试连接、服务预设、关闭不保存则不生效、审校选项保存到配置文件。"""
import json

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def open_settings(page):
    page.locator("header button:has(i:text-is('settings'))").click()
    dialog = page.locator(".settings-dialog")
    expect(dialog).to_be_visible()
    return dialog


def saved_config(app) -> dict:
    return json.loads((app.data_dir / "config.json").read_text(encoding="utf-8"))


def test_test_connection_uses_current_settings(page):
    dialog = open_settings(page)
    dialog.locator(".role-writer").get_by_role("button", name="测试连接").click()
    expect(page.locator(".q-notification", has_text="连接成功")).to_be_visible()


def test_preset_fills_fields_but_closing_discards_changes(page, app, fake_llm):
    writer = page.locator(".settings-dialog .role-writer")
    base_url = writer.get_by_label("Base URL")
    expect(base_url).to_have_value(f"{fake_llm}/v1")
    expect(writer.get_by_label("服务预设")).to_have_value("自定义")

    writer.get_by_label("服务预设").click()
    page.get_by_role("option", name="DeepSeek").click()
    expect(base_url).to_have_value("https://api.deepseek.com/v1")
    expect(writer.get_by_label("Model")).to_have_value("deepseek-chat")

    page.locator(".settings-dialog button:has(i:text-is('close'))").click()
    open_settings(page)
    expect(base_url).to_have_value(f"{fake_llm}/v1")  # 没保存：恢复原设置
    expect(writer.get_by_label("服务预设")).to_have_value("自定义")
    assert saved_config(app)["writer"]["base_url"] == f"{fake_llm}/v1"


def test_review_options_are_saved(page, app):
    dialog = page.locator(".settings-dialog")
    dialog.get_by_role("tab", name="Reviewer (总监)").click()
    options = dialog.locator(".review-options")
    options.get_by_label("未通过时").click()
    page.get_by_role("option", name="自动按意见重试").click()
    options.get_by_label("最多重试次数").fill("1")
    dialog.get_by_role("button", name="保存配置").click()
    expect(dialog).to_be_hidden()

    config = saved_config(app)
    assert (config["review_mode"], config["max_review_retries"], config["review_threshold"]) == ("auto", 1, 8)
