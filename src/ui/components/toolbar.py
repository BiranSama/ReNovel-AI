"""底部工具栏：保存 / 导出、全局精修指令、全文重写、批量与停止、状态栏。"""
from nicegui import ui

from src.ui.components.batch_dialog import open_batch_dialog
from src.ui.components.continue_dialog import open_continue_dialog
from src.ui.components.versions_dialog import open_versions_dialog


def create_toolbar(session, editor):
    state = session.state
    with ui.row().classes('w-full bg-slate-100 p-4 border-t items-center gap-4 flex-none h-20 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.1)]'):
        with ui.row().classes('gap-1'):
            ui.button('保存', on_click=session.save_all).props('unelevated color=green-6 dense icon=save')
            ui.button(icon='file_download', on_click=lambda: ui.download(session.current_text().encode('utf-8'), 'export.txt')) \
                .props('flat round dense')
            ui.button(icon='restore', on_click=lambda: open_versions_dialog(session)) \
                .props('flat round dense').tooltip('历史版本')

        ui.separator().props('vertical')
        ui.input(placeholder='在此输入全局精修指令...').bind_value(state, 'instruction') \
            .classes('flex-grow text-lg').props('outlined rounded bg-white')

        with ui.row().bind_visibility_from(state, 'view_mode', value='full'):
            ui.button('AI 全文重写', on_click=editor.rewrite_full) \
                .props('unelevated color=purple-6 text-white icon=auto_fix_normal size=md')

        ui.button('续写', icon='post_add', on_click=lambda: open_continue_dialog(session, editor)) \
            .props('flat dense color=teal')
        ui.button('批量', on_click=lambda: open_batch_dialog(session)).props('flat dense color=indigo')
        ui.button('停止', on_click=session.stop_workflow).props('outline color=red dense') \
            .bind_visibility_from(state, 'is_batch_running')
        with ui.column().classes('gap-0 w-56'):
            state.ui['status_label'] = ui.label('').classes('text-xs text-gray-500 truncate w-full')
            state.ui['status_progress'] = ui.linear_progress(value=0, show_value=False).classes('hidden w-full')
