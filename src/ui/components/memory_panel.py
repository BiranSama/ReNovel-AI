"""章节记忆面板：逐章查看摘要、出场角色与关键事件，可手动整理有变化的章节。"""
from nicegui import ui


class MemoryPanel:
    def __init__(self, session):
        self.session = session
        with ui.row().classes('w-full p-2 border-b bg-gray-50 justify-between items-center'):
            ui.label('章节记忆').classes('text-xs font-bold text-gray-500')
            ui.button('整理记忆', on_click=session.update_memory_incrementally).props('flat dense icon=auto_stories color=indigo')
        with ui.scroll_area().classes('flex-grow w-full'):
            self.container = ui.column().classes('w-full gap-1 p-2 memory-list')
        session.memory_view = self

    async def refresh(self):
        pid = self.session.state.current_project_id
        rows = await self.session.services.chapter_memory.chapter_memories(pid) if pid else []
        self.container.clear()
        with self.container:
            if not any(memory for _, memory in rows):
                ui.label('还没有整理过章节记忆。点击「整理记忆」，或保存章节后自动整理。').classes('text-xs text-gray-400 p-2')
            for chapter, memory in rows:
                if memory is None:
                    caption = '未整理'
                elif memory.is_empty:
                    caption = '内容太短，无需整理'
                else:
                    caption = memory.summary
                with ui.expansion(chapter['title'], caption=caption).classes('w-full border-b memory-item'):
                    if memory and not memory.is_empty:
                        ui.label(memory.summary).classes('text-sm')
                        if memory.characters:
                            with ui.row().classes('gap-1'):
                                for name in memory.characters:
                                    ui.chip(name).props('dense outline color=indigo')
                        for event in memory.events:
                            ui.label(f'• {event}').classes('text-xs text-gray-600')
                        for hook in memory.hooks:
                            ui.label(f'🔖 伏笔：{hook}').classes('text-xs text-purple-600')
