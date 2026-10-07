"""顶栏：视图切换（分段精修 / 全文工作台）、副本、图谱与助手、设置、导入。"""
from nicegui import ui


def create_header(session, on_switch_mode, on_toggle_assistant, on_open_settings, on_open_import):
    state = session.state
    with ui.header().classes('bg-white text-slate-800 h-14 flex items-center shadow-sm px-4 border-b'):
        ui.label('NovelForge').classes('text-xl font-black text-indigo-600')
        ui.label('Studio').classes('text-xs text-gray-400 mt-1 ml-1')

        ui.space()
        with ui.button_group().props('rounded unelevated'):
            ui.button('分段精修', on_click=lambda: on_switch_mode('segment')) \
                .props('dense color=indigo-1 text-color=indigo').bind_visibility_from(state, 'view_mode', value='full')
            ui.button('全文工作台', on_click=lambda: on_switch_mode('full')) \
                .props('dense color=purple-1 text-color=purple').bind_visibility_from(state, 'view_mode', value='segment')
        ui.space()

        ui.label().bind_text_from(state, 'active_card_name', backward=lambda name: f'🎭 {name}') \
            .classes('text-xs bg-slate-100 px-3 py-1 rounded-full mr-2')

        with ui.row().classes('gap-1'):
            ui.button(icon='history', on_click=session.open_backup_dialog).props('flat round dense color=slate-600').tooltip('副本')
            ui.button(icon='hub', on_click=on_toggle_assistant).props('flat round dense color=slate-600').tooltip('图谱')
            ui.button(icon='settings', on_click=on_open_settings).props('flat round dense color=slate-600')
            ui.button(icon='add', on_click=on_open_import).props('flat round dense color=indigo')
