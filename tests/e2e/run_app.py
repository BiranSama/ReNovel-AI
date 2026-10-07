"""在指定端口、关闭热重载的情况下启动应用（不改动 main.py）。

用法: python run_app.py <port>，数据目录由环境变量 RENOVEL_DATA_DIR 指定。

NiceGUI 3 的脚本模式会为每个客户端重新执行 sys.argv[0]，所以这里把它指向
main.py：首次以非 __main__ 名执行以搭建界面（不触发其中的 ui.run），之后的
重新执行里 main.py 自己的 ui.run 会因应用已启动而直接返回。
"""
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "main.py"

port = int(sys.argv[1])
sys.path.insert(0, str(ROOT))
sys.argv = [str(MAIN)]
runpy.run_path(str(MAIN), run_name="renovel_main")

from nicegui import ui  # noqa: E402

ui.run(title="Re:Novel AI", port=port, reload=False, show=False)
