"""文风档案面板：风格描述与代表段落，可从原文提炼、套用预设或手动编辑；改写时立即生效。"""
from nicegui import ui

from src.core.style_store import StyleProfile
from src.llm import LLMError
from src.services.style import PRESET_NAMES, StyleExtractError


class StylePanel:
    def __init__(self, session):
        self.session = session
        self.profile = StyleProfile()
        with ui.row().classes('w-full p-2 border-b bg-gray-50 justify-between items-center'):
            ui.label('文风档案').classes('text-xs font-bold text-gray-500')
            with ui.row().classes('gap-1 items-center'):
                self.extract_button = ui.button('从原文提炼', on_click=self.extract) \
                    .props('flat dense icon=auto_awesome color=indigo')
                ui.select(PRESET_NAMES, label='套用预设', on_change=lambda e: self.apply_preset(e)) \
                    .props('dense outlined').classes('w-28 style-preset')
        with ui.scroll_area().classes('flex-grow w-full'):
            self.container = ui.column().classes('w-full gap-2 p-2 style-panel')
        session.style_view = self

    async def refresh(self):
        pid = self.session.state.current_project_id
        self.profile = await self.session.services.style.get(pid) if pid else StyleProfile()
        self._render()

    def _render(self):
        profile = self.profile
        self.container.clear()
        with self.container:
            if profile.source:
                ui.label(f'来源：{profile.source}').classes('text-xs text-gray-400')
            ui.textarea('风格描述（改写时遵循，审校时打「文风贴合度」）', value=profile.description,
                        on_change=lambda e: setattr(profile, 'description', e.value or '')) \
                .props('autogrow outlined').classes('w-full style-description')
            ui.label('代表段落（改写时作为示例）').classes('text-xs text-gray-500')
            for i, sample in enumerate(profile.samples):
                with ui.row().classes('w-full no-wrap items-start'):
                    ui.textarea(value=sample, on_change=lambda e, i=i: profile.samples.__setitem__(i, e.value or '')) \
                        .props('autogrow outlined dense').classes('flex-grow style-sample')
                    ui.button(icon='close', on_click=lambda i=i: (profile.samples.pop(i), self._render())) \
                        .props('flat round dense size=sm color=grey')
            with ui.row().classes('w-full justify-between'):
                ui.button('添加段落', icon='add', on_click=lambda: (profile.samples.append(''), self._render())) \
                    .props('flat dense size=sm')
                ui.button('保存文风', icon='save', on_click=self.save).props('unelevated dense color=indigo')

    async def save(self):
        pid = self.session.state.current_project_id
        if not pid: return ui.notify('请先打开项目', type='warning')
        if not self.profile.source:
            self.profile.source = '手动填写'
        await self.session.services.style.save(pid, self.profile)
        ui.notify('文风档案已保存，下一次改写即按新档案执行')
        await self.refresh()

    async def apply_preset(self, event):
        pid = self.session.state.current_project_id
        if not event.value: return
        if not pid:
            event.sender.value = None
            return ui.notify('请先打开项目', type='warning')
        self.profile = await self.session.services.style.apply_preset(pid, event.value)
        event.sender.value = None
        self._render()
        ui.notify(f'已套用「{self.profile.source.removeprefix("预设：")}」文风')

    async def extract(self):
        pid = self.session.state.current_project_id
        if not pid: return ui.notify('请先打开项目', type='warning')
        self.extract_button.props('loading')
        try:
            self.profile = await self.session.services.style.extract(pid)
        except (LLMError, StyleExtractError) as e:
            return ui.notify(f'提炼文风失败：{e}', type='negative')
        finally:
            self.extract_button.props(remove='loading')
        self._render()
        ui.notify('已从原文提炼文风档案')
