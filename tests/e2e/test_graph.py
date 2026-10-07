"""知识图谱冒烟测试：导入时选择建立图谱，后台抽取关系并落盘。

单独成模块，以便使用一个全新的应用实例。
"""
import json
import time
from pathlib import Path

import pytest

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
            if graph["links"]:
                break
        time.sleep(1)

    assert graph and graph["links"], app.log_tail()
    assert {n["id"] for n in graph["nodes"]} == {"张三", "李四"}
