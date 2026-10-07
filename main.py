import os
import sys

# 控制台编码不支持中文 / emoji 时（如英文 Windows 的 cp1252）替换成问号，而不是让打印日志的地方抛异常
for _stream in (sys.stdout, sys.stderr):
    if _stream and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

if "--self-check" in sys.argv:  # 打包产物的自检：检查依赖与数据目录后退出，不启动界面
    from src.selfcheck import run
    sys.exit(run())

from nicegui import app, ui  # noqa: E402

from src.core.managers import Services  # noqa: E402
from src.ui.main_layout import create_layout  # noqa: E402

# 应用级服务只创建一次，所有浏览器标签页共享
services = Services()
app.on_startup(services.init_db)


@ui.page('/')
def index():
    """每个浏览器标签页单独调用，拥有自己的会话状态。"""
    ui.page_title('Re:Novel AI')
    create_layout(services)


# 启动应用（环境变量：RENOVEL_PORT 端口，RENOVEL_RELOAD=1 修改代码后自动重启，RENOVEL_SHOW=0 不自动打开浏览器）
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="Re:Novel AI",
        port=int(os.environ.get("RENOVEL_PORT", "8080")),
        reload=os.environ.get("RENOVEL_RELOAD") == "1",
        show=os.environ.get("RENOVEL_SHOW", "1") == "1",
        dark=False,  # 默认亮色主题
    )
