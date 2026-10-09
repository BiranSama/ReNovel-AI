"""编辑器：分段精修（原文 / 改写逐段对照）与全文工作台两种视图，以及单段、全文的 AI 改写。"""
from nicegui import ui

from src.llm import LLMError
from src.ui.components.review_dialog import ReviewDialog
from src.ui.session import split_text

DEFAULT_SEGMENT_INSTRUCTION = "润色"
DEFAULT_FULL_INSTRUCTION = "精修"


class Editor:
    def __init__(self, session, review: ReviewDialog):
        self.session = session
        self.state = session.state
        self.review = review
        self.full_text_area = None
        self.panel = ui.refreshable(self._render)
        session.register_renderer(self.refresh)

    def refresh(self):
        try: self.panel.refresh()
        except RuntimeError: pass  # 页面已关闭

    def switch_mode(self, mode):
        self.state.view_mode = mode
        self.refresh()
        ui.notify(f'切换到{mode}模式')

    def sync_to_segments(self):
        """把全文草稿拆回分段视图。"""
        if not self.state.full_text_draft: return
        self.state.segments = split_text(self.state.full_text_draft)
        self.state.view_mode = 'segment'
        self.refresh()
        ui.notify('已同步至分段视图')

    # ==========================
    # AI 改写
    # ==========================
    async def rewrite_segment(self, idx, button=None):
        seg = self.state.segments[idx]
        if seg.get('busy'): return  # 这一段正在改写，忽略重复点击
        # 段落自己的局部指令优先；为空时用底部的全局指令
        local = (getattr(seg.get('prompt_input'), 'value', '') or '').strip()
        instruction = local or self.state.instruction or DEFAULT_SEGMENT_INSTRUCTION

        async def ask(review, text, can_retry):
            return await self.review.ask(review, seg.get('original', ''), text, can_retry)

        seg['busy'] = True
        if button: button.props('loading')
        try:
            await self.session.rewrite_segment(seg, instruction, ask)
        except LLMError as e:
            ui.notify(f'改写失败：{e}', type='negative')
        finally:
            seg['busy'] = False
            if button: button.props(remove='loading')
        if seg.get('ui_component'): seg['ui_component'].value = seg.get('revised', '')

    async def rewrite_full(self):
        """全文重写：先由军师分析并给出报告，用户确认后按报告改写。"""
        session, state = self.session, self.state
        full_text = session.current_text()
        if not full_text.strip(): return ui.notify('内容为空', type='warning')

        request = await session.refine_request(full_text, state.instruction or DEFAULT_FULL_INSTRUCTION)
        try:
            report = await session.run_analyzer(full_text, request.instruction)
        except LLMError as e:
            return ui.notify(f'军师分析失败：{e}', type='negative')
        if not await self._confirm_report(report): return
        request.guidance = report

        def show(text):
            if state.view_mode == 'full' and self.full_text_area:
                self.full_text_area.value = text

        async def ask(review, text, can_retry):
            return await self.review.ask(review, full_text, text, can_retry)

        try:
            result = await session.refine(request, show, ask)
        except LLMError as e:
            return ui.notify(f'改写失败：{e}', type='negative')

        if state.view_mode == 'segment':
            state.segments = split_text(result.text)
            self.refresh()
        else:
            state.full_text_draft = result.text
        ui.notify('全文重写完成')

    @staticmethod
    async def _confirm_report(report: str) -> bool:
        with ui.dialog() as d, ui.card().classes('w-full max-w-4xl'):
            ui.label('军师报告').classes('text-lg font-bold text-purple')
            ui.markdown(report).classes('w-full bg-gray-50 p-4 h-64 overflow-auto')
            with ui.row().classes('w-full justify-end'):
                ui.button('取消', on_click=d.close).props('flat')
                ui.button('执行', on_click=lambda: d.submit(True)).props('color=purple')
        return bool(await d)

    # ==========================
    # 视图
    # ==========================
    def _render(self):
        for seg in self.state.segments:
            seg.setdefault('original', '')
            seg.setdefault('revised', '')
            seg.setdefault('prompt_input', None)
        if self.state.view_mode == 'full':
            self._render_full()
        else:
            self._render_segments()

    def _render_full(self):
        state = self.state
        with ui.row().classes('w-full h-full gap-4 items-stretch p-4 overflow-hidden'):
            with ui.column().classes('w-1/2 h-full full-height-col bg-gray-100 rounded-lg border'):
                ui.label('📄 原文参考').classes('text-xs font-bold text-gray-500 p-2 border-b bg-gray-50')
                original = "\n\n".join(s.get('original', '') for s in state.segments)
                ui.textarea(value=original).props('readonly borderless filled') \
                    .classes('full-height-textarea w-full bg-transparent p-2')

            with ui.column().classes('w-1/2 h-full full-height-col bg-white rounded-lg border-2 border-indigo-100 shadow-sm'):
                with ui.row().classes('w-full justify-between items-center p-2 border-b bg-indigo-50'):
                    ui.label('📝 改写结果').classes('text-xs font-bold text-indigo-600')
                    ui.button('同步分段', on_click=self.sync_to_segments).props('dense flat icon=sync color=purple size=sm')

                if not state.full_text_draft and state.segments:  # 初始化全文草稿
                    lines = [s.get('revised') or s.get('original', '') for s in state.segments]
                    state.full_text_draft = "\n\n".join(filter(None, lines))
                self.full_text_area = ui.textarea().bind_value(state, 'full_text_draft') \
                    .props('borderless placeholder="AI改写内容将实时显示..."').classes('full-height-textarea w-full p-2')

    def _render_segments(self):
        state = self.state
        with ui.scroll_area().classes('w-full h-full p-6 bg-slate-50'):
            with ui.column().classes('w-full max-w-4xl mx-auto pb-32 gap-4'):
                for i, seg in enumerate(state.segments):
                    with ui.row().classes('w-full segment-card p-4 gap-4 items-start'):
                        with ui.column().classes('w-[45%]'):
                            ui.label(f'#{i+1} 原文').classes('text-xs font-bold text-gray-400 mb-1')
                            ui.textarea(value=seg.get('original', '')) \
                                .on('input', lambda e, i=i: state.segments[i].__setitem__('original', e.value)) \
                                .props('autogrow outlined dense').classes('w-full bg-gray-50 text-sm rounded')

                        with ui.column().classes('w-[10%] pt-6 gap-2 items-center'):
                            ui.button(icon='auto_fix_high', on_click=lambda e, i=i: self.rewrite_segment(i, e.sender)) \
                                .props('round flat dense color=indigo').tooltip('精修')
                            ui.button(icon='delete', on_click=lambda i=i: (state.segments.pop(i), self.refresh())) \
                                .props('round flat dense color=red size=sm')
                            with ui.expansion('', icon='edit_note').props('dense flat'):
                                seg['prompt_input'] = ui.input(placeholder='局部指令').props('dense outlined').classes('w-32 text-xs')

                        with ui.column().classes('w-[45%]'):
                            ui.label('AI 改写').classes('text-xs font-bold text-indigo-400 mb-1')
                            seg['ui_component'] = ui.textarea(value=seg.get('revised', '')) \
                                .on('input', lambda e, i=i: state.segments[i].__setitem__('revised', e.value)) \
                                .props('autogrow outlined dense').classes('w-full bg-white border border-indigo-100 text-sm rounded')

                    with ui.element('div').classes('insert-zone') \
                            .on('click', lambda i=i: (state.segments.insert(i + 1, {'original': '', 'revised': ''}), self.refresh())):
                        ui.label('+').classes('insert-btn')
