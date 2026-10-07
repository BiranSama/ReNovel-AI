"""页面组装：每个浏览器标签页调用一次 create_layout，各部分的界面与交互在 src/ui/components 里。"""
from nicegui import ui

from src.ui.components.chat_panel import ChatPanel
from src.ui.components.editor import Editor
from src.ui.components.graph_panel import GraphPanel
from src.ui.components.header import create_header
from src.ui.components.memory_panel import MemoryPanel
from src.ui.components.review_dialog import ReviewDialog
from src.ui.components.settings_dialog import SettingsDialog
from src.ui.components.sidebar import create_backup_dialog, create_import_dialog, create_sidebar
from src.ui.components.toolbar import create_toolbar
from src.ui.session import Session

# ==========================
# CSS 样式补丁
# ==========================
PAGE_CSS = '''
<style>
    .full-height-col { display: flex; flex-direction: column; height: 100%; }
    .full-height-textarea { display: flex; flex-direction: column; flex-grow: 1; height: 100%; }
    .full-height-textarea .q-field__control,
    .full-height-textarea .q-field__native {
        height: 100% !important; min-height: 100% !important; max-height: none !important; resize: none !important;
    }
    .full-height-textarea textarea {
        overflow-y: auto !important; font-family: "Consolas", monospace; line-height: 1.8; font-size: 16px; color: #334155;
    }
    .segment-card { background: white; border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); transition: all 0.2s; }
    .segment-card:hover { transform: translateY(-1px); box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .insert-zone { height: 10px; width: 100%; display: flex; justify-content: center; align-items: center; opacity: 0; cursor: pointer; margin: 4px 0; transition: opacity 0.2s; }
    .insert-zone:hover { opacity: 1; }
    .insert-btn { background-color: #a78bfa; color: white; border-radius: 50%; width: 20px; height: 20px; display: flex; justify-content: center; align-items: center; font-size: 12px; }
</style>
'''

def create_layout(services):
    """搭建一个页面。每个浏览器标签页调用一次，拥有自己的 Session 和界面状态。"""
    session = Session(services)
    ui.add_head_html(PAGE_CSS)

    settings = SettingsDialog(services.settings, services.llm, services.rag)
    settings.create_ui()
    editor = Editor(session, ReviewDialog())
    import_dialog = create_import_dialog(session)
    create_backup_dialog(session)

    create_sidebar(session)
    with ui.right_drawer(value=False).classes('bg-white border-l w-[600px]') as assistant:
        with ui.tabs().classes('w-full text-gray-600') as tabs:
            chat_tab = ui.tab('助手', icon='chat')
            memory_tab = ui.tab('记忆', icon='auto_stories')
            graph_tab = ui.tab('图谱', icon='hub')
        with ui.tab_panels(tabs, value=chat_tab).classes('flex-grow h-full'):
            with ui.tab_panel(chat_tab).classes('p-0 flex flex-col w-full h-full'):
                ChatPanel(session)
            with ui.tab_panel(memory_tab).classes('p-0 w-full h-full flex flex-col'):
                MemoryPanel(session)
            with ui.tab_panel(graph_tab).classes('p-0 w-full h-full flex flex-col relative'):
                GraphPanel(session)

    create_header(session, editor.switch_mode, assistant.toggle, settings.open, import_dialog.open)

    with ui.column().classes('w-full h-[calc(100vh-56px)] bg-white p-0 flex-col no-wrap'):
        with ui.column().classes('w-full flex-grow overflow-hidden relative'):
            editor.panel()  # 编辑器占据剩余空间
        create_toolbar(session, editor)

    # 首次渲染与数据加载
    ui.timer(0.1, editor.refresh, once=True)
    ui.timer(0.5, session.auto_load_latest_project, once=True)
