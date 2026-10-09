"""分层约束：业务层不依赖界面，才能脱离浏览器单独测试。"""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
UI_FREE = sorted([*ROOT.glob("src/services/*.py"), *ROOT.glob("src/llm/*.py"),
                  ROOT / "src/core/settings.py", ROOT / "src/paths.py"])


def imported_modules(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("path", UI_FREE, ids=lambda p: str(p.relative_to(ROOT)))
def test_business_layer_does_not_import_ui(path):
    forbidden = {m for m in imported_modules(path) if m.split(".")[0] == "nicegui" or m.startswith("src.ui")}
    assert not forbidden, f"{path.name} 不应依赖界面：{forbidden}"
