"""以测试配置启动应用：指定端口、关闭热重载、不打开浏览器。

用法: python run_app.py <port>，数据目录由环境变量 RENOVEL_DATA_DIR 指定。
"""
import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

os.environ.update(RENOVEL_PORT=sys.argv[1], RENOVEL_RELOAD="0", RENOVEL_SHOW="0")
sys.path.insert(0, str(ROOT))
sys.argv = [str(ROOT / "main.py")]
runpy.run_path(str(ROOT / "main.py"), run_name="__main__")
