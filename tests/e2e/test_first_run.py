"""首次启动引导：没有可用的模型服务时弹出，测试连接后保存，之后不再弹出。"""
import json

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def customize_config(config, fake_llm):
    """模拟第一次启动：没有任何角色填写 API Key。"""
    for role in ("writer", "reviewer", "analyzer", "chat", "graph"):
        config[role] = {"api_key": "", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"}
    return config


def test_welcome_dialog_guides_setup(page, app, fake_llm):
    dialog = page.locator(".welcome-dialog")
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text("API Key 可在 platform.openai.com 申请")

    dialog.get_by_label("Base URL").fill(f"{fake_llm}/v1")
    dialog.get_by_label("API Key").fill("sk-new")
    dialog.get_by_label("Model").fill("fake-model")
    dialog.get_by_role("button", name="测试连接").click()
    expect(page.locator(".q-notification", has_text="连接成功")).to_be_visible()

    dialog.get_by_role("button", name="保存并开始").click()
    expect(dialog).to_be_hidden()
    writer = json.loads((app.data_dir / "config.json").read_text(encoding="utf-8"))["writer"]
    assert (writer["api_key"], writer["base_url"], writer["model"]) == ("sk-new", f"{fake_llm}/v1", "fake-model")

    page.reload()
    page.wait_for_timeout(1500)
    expect(page.locator(".welcome-dialog")).to_be_hidden()  # 已经设置过，不再弹出
