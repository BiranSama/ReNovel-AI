import os

from nicegui import app, ui

from src.core.managers import Services
from src.ui.main_layout import create_layout

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
