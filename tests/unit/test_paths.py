"""数据目录解析：开发 / exe / 环境变量覆盖。"""
import sys

from src import paths


def test_dev_mode_uses_project_root(monkeypatch):
    monkeypatch.delenv("RENOVEL_DATA_DIR", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert paths.data_dir() == paths.PROJECT_ROOT / "data"


def test_frozen_exe_keeps_data_next_to_executable(monkeypatch, tmp_path):
    monkeypatch.delenv("RENOVEL_DATA_DIR", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "ReNovel.exe"))
    assert paths.data_dir() == tmp_path / "data"


def test_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("RENOVEL_DATA_DIR", str(tmp_path / "custom"))
    assert paths.data_dir() == tmp_path / "custom"
    assert paths.db_file() == tmp_path / "custom" / "projects" / "novelforge.db"
    assert paths.config_file() == tmp_path / "custom" / "config.json"
    assert paths.graph_file("p1") == tmp_path / "custom" / "projects" / "p1_graph.json"
    assert paths.memory_db() == tmp_path / "custom" / "memory.db"


def test_ensure_dirs_creates_layout(monkeypatch, tmp_path):
    monkeypatch.setenv("RENOVEL_DATA_DIR", str(tmp_path / "d"))
    assert paths.ensure_dirs() == tmp_path / "d"
    for sub in ("projects", "models", "presets"):
        assert (tmp_path / "d" / sub).is_dir()
