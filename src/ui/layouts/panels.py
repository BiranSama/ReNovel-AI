from nicegui import ui
from src.ui.state import app_state
import src.logic.handlers as h

def create_header(on_toggle_left, on_toggle_right, on_open_settings, on_open_import, on_switch_mode):
    with ui.header().classes('bg-white text-slate-800 h-14 flex items-center shadow-sm px-4 border-b'):
        ui.label('NovelForge').classes('text-xl font-black text-indigo-600')
        ui.label('Studio').classes('text-xs text-gray-400 mt-1 ml-1')
        
        ui.space()
        with ui.button_group().props('rounded unelevated'):
            ui.button('分段精修', on_click=lambda: on_switch_mode('segment')).props('dense color=indigo-1 text-color=indigo').bind_visibility_from(app_state, 'view_mode', lambda m: m=='full')
            ui.button('全文工作台', on_click=lambda: on_switch_mode('full')).props('dense color=purple-1 text-color=purple').bind_visibility_from(app_state, 'view_mode', lambda m: m=='segment')
        ui.space()
        
        app_state.ui['persona_label'] = ui.label('🎭 默认').classes('text-xs bg-slate-100 px-3 py-1 rounded-full mr-2')
        
        with ui.row().classes('gap-1'):
            ui.button(icon='history').props('flat round dense color=slate-600').tooltip('副本').on('click', lambda: (app_state.ui['backup_dialog'].open(), h.refresh_backup_list(app_state.ui['backup_list'])))
            ui.button(icon='hub', on_click=on_toggle_right).props('flat round dense color=slate-600').tooltip('图谱')
            ui.button(icon='settings', on_click=on_open_settings).props('flat round dense color=slate-600')
            ui.button(icon='add', on_click=on_open_import).props('flat round dense color=indigo')

def create_left_drawer():
    with ui.left_drawer(value=True).classes('bg-slate-50 border-r w-64 flex flex-col') as drawer:
        with ui.row().classes('w-full p-3 border-b bg-white items-center'):
            ui.icon('book', size='xs').classes('text-indigo-500')
            app_state.ui['project_title'] = ui.label('未加载').classes('text-sm font-bold text-slate-700 truncate flex-grow')
            ui.button(icon='refresh', on_click=h.refresh_project_list).props('flat round dense size=sm color=grey')

        with ui.tabs().classes('w-full text-xs') as tabs:
            t_chapter = ui.tab('章节', icon='list')
            t_books = ui.tab('书架', icon='library_books')
        
        with ui.tab_panels(tabs, value=t_chapter).classes('flex-grow w-full bg-transparent'):
            with ui.tab_panel(t_chapter).classes('p-0 w-full h-full'):
                with ui.scroll_area().classes('h-full w-full'):
                    app_state.ui['chapter_list'] = ui.column().classes('w-full gap-0')
            
            with ui.tab_panel(t_books).classes('p-0 w-full h-full'):
                with ui.scroll_area().classes('h-full w-full'):
                    app_state.ui['project_list'] = ui.column().classes('w-full gap-1 p-2')
    return drawer

def create_right_drawer(on_refresh_graph, on_send_chat, on_update_graph):
    with ui.right_drawer(value=False).classes('bg-white border-l w-[600px]') as drawer:
        with ui.tabs().classes('w-full text-gray-600') as r_tabs: 
            rt1=ui.tab('助手', icon='chat'); rt2=ui.tab('图谱', icon='hub')
        
        with ui.tab_panels(r_tabs, value=rt1).classes('flex-grow h-full'):
            with ui.tab_panel(rt1).classes('p-0 flex flex-col w-full h-full'):
                with ui.scroll_area().classes('flex-grow p-4 bg-slate-50 w-full'): 
                    app_state.ui['chat_container'] = ui.column().classes('w-full gap-3')
                
                with ui.column().classes('p-3 border-t w-full'): 
                    app_state.ui['chat_mode'] = ui.select({'chapter':'本章','book':'全书'}, value='chapter').props('dense filled').classes('w-full')
                    chat_input = ui.textarea(placeholder="输入问题...").classes('w-full').props('outlined dense rows=2').on('keydown.enter.prevent', on_send_chat)
                    app_state.ui['chat_input'] = chat_input
                    ui.button('发送', on_click=on_send_chat).props('full-width unelevated color=indigo icon=send')
            
            with ui.tab_panel(rt2).classes('p-0 w-full h-full flex flex-col relative'):
                with ui.row().classes('w-full p-2 border-b bg-gray-50 justify-between items-center'):
                    ui.label('关系网').classes('text-xs font-bold text-gray-500')
                    with ui.row().classes('gap-1'):
                        ui.button('增量更新', on_click=on_update_graph).props('flat dense icon=update color=indigo')
                        ui.button('刷新', on_click=on_refresh_graph).props('flat dense icon=refresh')

                app_state.ui['graph_chart'] = ui.echart({'series':[{'type':'graph','layout':'force','data':[],'links':[]}]}).classes('w-full flex-grow')
    return drawer