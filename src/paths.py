"""应用数据目录的唯一来源。

- 开发运行：项目根目录下的 data/
- 打包成 exe：exe 所在目录下的 data/（绿色版，拷走即带走数据）
- 环境变量 RENOVEL_DATA_DIR 可覆盖以上两者（测试也用它隔离数据）

每次调用时读取环境变量，所以测试可以在运行时切换目录。
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    override = os.environ.get("RENOVEL_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return PROJECT_ROOT / "data"


def projects_dir() -> Path:
    return data_dir() / "projects"


def vectordb_dir() -> Path:
    return data_dir() / "vectordb"


def presets_dir() -> Path:
    return data_dir() / "presets"


def config_file() -> Path:
    return data_dir() / "config.json"


def db_file() -> Path:
    return projects_dir() / "novelforge.db"


def graph_file(project_id: str) -> Path:
    return projects_dir() / f"{project_id}_graph.json"


def ensure_dirs() -> Path:
    """创建所有数据子目录，返回数据根目录。"""
    for directory in (projects_dir(), vectordb_dir(), presets_dir()):
        directory.mkdir(parents=True, exist_ok=True)
    return data_dir()
