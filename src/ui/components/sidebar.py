"""左侧栏（章节目录、书架）以及与项目相关的弹窗（导入、历史副本）。"""
from nicegui import ui


def create_sidebar(session):
    refs = session.state.ui
    with ui.left_drawer(value=True).classes('bg-slate-50 border-r w-64 flex flex-col') as drawer:
        with ui.row().classes('w-full p-3 border-b bg-white items-center'):
            ui.icon('book', size='xs').classes('text-indigo-500')
            refs['project_title'] = ui.label('未加载').classes('text-sm font-bold text-slate-700 truncate flex-grow')
            ui.button(icon='refresh', on_click=session.refresh_project_list).props('flat round dense size=sm color=grey')

        with ui.tabs().classes('w-full text-xs') as tabs:
            chapters_tab = ui.tab('章节', icon='list')
            books_tab = ui.tab('书架', icon='library_books')

        with ui.tab_panels(tabs, value=chapters_tab).classes('flex-grow w-full bg-transparent'):
            with ui.tab_panel(chapters_tab).classes('p-0 w-full h-full'):
                with ui.scroll_area().classes('h-full w-full'):
                    refs['chapter_list'] = ui.column().classes('w-full gap-0')
            with ui.tab_panel(books_tab).classes('p-0 w-full h-full'):
                with ui.scroll_area().classes('h-full w-full'):
                    refs['project_list'] = ui.column().classes('w-full gap-1 p-2')
    return drawer


def create_import_dialog(session):
    with ui.dialog() as dialog, ui.card():
        ui.label('导入').classes('text-lg font-bold')
        ui.upload(on_upload=lambda e: session.handle_novel_upload(e, dialog), auto_upload=True).props('accept=.txt flat')
    return dialog


def create_backup_dialog(session):
    refs = session.state.ui
    with ui.dialog() as dialog, ui.card().classes('w-96'):
        ui.label('历史副本').classes('font-bold')
        ui.button('+ 创建副本', on_click=session.create_backup).props('unelevated color=green w-full')
        refs['backup_list'] = ui.column().classes('w-full mt-2 h-48 scroll-y border rounded')
    refs['backup_dialog'] = dialog
    return dialog
