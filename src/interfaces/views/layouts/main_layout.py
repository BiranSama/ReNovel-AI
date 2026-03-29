from nicegui import ui
from src.interfaces import app_state


def create_layout():
    with ui.column().classes('w-full h-screen'):
        create_header()
        
        with ui.row().classes('w-full flex-1 overflow-hidden'):
            create_left_drawer()
            create_main_content()
            create_right_drawer()
        
        create_footer()


def create_header():
    with ui.header().classes('bg-white text-slate-800 h-14 flex items-center shadow-sm px-4 border-b'):
        ui.label('NovelForge').classes('text-xl font-black text-indigo-600')
        ui.label('Studio').classes('text-xs text-gray-400 mt-1 ml-1')
        
        ui.space()
        
        ui.button(icon='settings').props('flat round dense color=slate-600')
        ui.button(icon='add').props('flat round dense color=indigo')


def create_left_drawer():
    with ui.left_drawer(value=True).classes('bg-slate-50 border-r w-64 flex flex-col'):
        with ui.row().classes('w-full p-3 border-b bg-white items-center'):
            ui.icon('book', size='xs').classes('text-indigo-500')
            ui.label('未加载').classes('text-sm font-bold text-slate-700 truncate flex-grow')
        
        ui.label('章节列表').classes('text-xs text-gray-400 p-2')
        
        with ui.scroll_area().classes('flex-grow w-full'):
            app_state.ui_refs['chapter_list'] = ui.column().classes('w-full gap-0')


def create_main_content():
    with ui.column().classes('flex-1 h-full bg-white p-4 overflow-hidden'):
        ui.label('编辑器区域').classes('text-gray-400')
        ui.label('(待实现)').classes('text-xs text-gray-300')


def create_right_drawer():
    with ui.right_drawer(value=False).classes('bg-white border-l w-96'):
        ui.label('图谱 / 聊天').classes('text-gray-400 p-4')


def create_footer():
    with ui.row().classes('w-full bg-slate-100 p-4 border-t items-center gap-4'):
        ui.button('保存', icon='save').props('unelevated color=green-6 dense')
        ui.input(placeholder='输入精修指令...').classes('flex-grow').props('outlined dense')
        ui.button('AI 重写', icon='auto_fix_high').props('unelevated color=purple-6')
