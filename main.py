from nicegui import ui
from src.interfaces.web.app import create_layout

ui.page_title('Re:Novel AI')

create_layout()

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="Re:Novel AI",
        port=8080,
        reload=True,
        dark=False
    )
