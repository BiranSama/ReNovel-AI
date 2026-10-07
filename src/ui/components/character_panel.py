"""角色档案面板：自动汇总的别名、性格、状态变化与人物关系，可手动修订。"""
from nicegui import ui

from src.core.chapter_memory_store import CharacterOverride


def _split_names(text: str) -> list[str]:
    return [n.strip() for n in text.replace("，", ",").replace("、", ",").split(",") if n.strip()]


class CharacterPanel:
    def __init__(self, session):
        self.session = session
        with ui.row().classes('w-full p-2 border-b bg-gray-50 justify-between items-center'):
            ui.label('角色档案').classes('text-xs font-bold text-gray-500')
            ui.label('来自章节记忆，点击查看与修订').classes('text-xs text-gray-400')
        with ui.scroll_area().classes('flex-grow w-full'):
            self.container = ui.column().classes('w-full gap-1 p-2 character-list')
        session.character_view = self

    async def refresh(self):
        session = self.session
        profiles = await session.services.characters.profiles(session.state.current_project_id)
        self.container.clear()
        with self.container:
            if not profiles:
                ui.label('还没有角色档案。整理章节记忆后会自动生成。').classes('text-xs text-gray-400 p-2')
            for profile in profiles:
                with ui.card().classes('w-full p-2 cursor-pointer hover:bg-indigo-50 character-item') \
                        .on('click', lambda _, p=profile: self.open_profile(p)):
                    with ui.row().classes('items-center gap-2'):
                        ui.label(profile.name).classes('font-bold text-sm')
                        if profile.aliases:
                            ui.label('又名 ' + '、'.join(profile.aliases)).classes('text-xs text-gray-500')
                        if profile.edited:
                            ui.icon('edit', size='xs').classes('text-indigo-400').tooltip('已手动修订')
                    ui.label(f'出场 {len(profile.chapters)} 章').classes('text-xs text-gray-400')

    def open_profile(self, profile):
        session = self.session
        pid = session.state.current_project_id
        relations = session.services.characters.relations(pid, profile)
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl character-dialog'):
            ui.label(profile.name).classes('text-lg font-bold')
            aliases = ui.input('别名（逗号分隔；填入其他角色名可合并为同一人）', value='、'.join(profile.aliases)).classes('w-full')
            traits = ui.textarea('性格', value=profile.manual_traits,
                                 placeholder=profile.traits_text() or '还没有整理出性格描述').classes('w-full').props('autogrow')
            if profile.traits and not profile.manual_traits:
                ui.label(f'自动汇总：{profile.traits_text()}').classes('text-xs text-gray-500')
            notes = ui.textarea('备注（改写和审校时会参考）', value=profile.notes).classes('w-full').props('autogrow')
            hidden = ui.checkbox('不是角色（误识别），隐藏')

            ui.label('状态变化').classes('font-bold text-sm mt-2')
            if not profile.statuses:
                ui.label('暂无').classes('text-xs text-gray-400')
            for change in profile.statuses:
                ui.label(f'{change.chapter_title}：{change.status}').classes('text-sm')
            ui.label('人物关系').classes('font-bold text-sm mt-2')
            for line in relations or ['暂无（建立人物图谱后显示）']:
                ui.label(line).classes('text-sm text-gray-600')

            async def save():
                await session.services.characters.save_override(pid, CharacterOverride(
                    profile.name, _split_names(aliases.value or ''), (traits.value or '').strip(),
                    (notes.value or '').strip(), bool(hidden.value)))
                dialog.close()
                ui.notify('角色档案已保存')
                await self.refresh()

            with ui.row().classes('w-full justify-end'):
                ui.button('取消', on_click=dialog.close).props('flat')
                ui.button('保存', on_click=save).props('color=indigo')
        dialog.open()
