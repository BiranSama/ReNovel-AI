"""小说助手：本章模式只用前文信息回答，全书模式用全部设定（作者视角）。"""
from nicegui import ui

from src.llm import LLMError

CHAT_MODES = {'chapter': '本章', 'book': '全书'}


class ChatPanel:
    def __init__(self, session):
        self.session = session
        with ui.scroll_area().classes('flex-grow p-4 bg-slate-50 w-full'):
            self.messages = ui.column().classes('w-full gap-3')
        with ui.column().classes('p-3 border-t w-full'):
            self.mode = ui.select(CHAT_MODES, value='chapter').props('dense filled').classes('w-full')
            self.input = ui.textarea(placeholder="输入问题...").classes('w-full').props('outlined dense rows=2') \
                .on('keydown.enter.prevent', self.send)
            ui.button('发送', on_click=self.send).props('full-width unelevated color=indigo icon=send')

    async def send(self):
        question = (self.input.value or '').strip()
        self.input.value = ''
        if not question: return

        session = self.session
        with self.messages:
            ui.label(question).classes('chat-bubble chat-user')
            bubble = ui.label('Thinking...').classes('chat-bubble chat-ai')
        answer = ''
        try:
            async for token in session.services.chat.answer(
                    question, session.state.current_project_id, await session.chapter_index(),
                    session.current_text(), self.mode.value):
                answer += token
                bubble.text = answer
        except LLMError as e:
            bubble.text = f'出错：{e}'
