"""章节历史版本：每次保存前的内容都会留下，可以恢复到编辑器（保存后生效）。"""
from nicegui import ui

PREVIEW_CHARS = 60


async def open_versions_dialog(session):
    if not session.state.current_chapter_id: return ui.notify('请先打开一个章节', type='warning')
    versions = await session.chapter_versions()
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl versions-dialog'):
        ui.label('历史版本').classes('text-lg font-bold')
        ui.label('每次保存时，被替换掉的内容会留在这里（每章保留最近 20 个）').classes('text-xs text-gray-500')
        if not versions:
            ui.label('这一章还没有历史版本').classes('text-sm text-gray-400 p-2')
        with ui.scroll_area().classes('w-full h-80'):
            for version in versions:
                content = version['content'] or ''
                with ui.row().classes('w-full items-center justify-between border-b py-1 no-wrap version-item'):
                    with ui.column().classes('gap-0 min-w-0'):
                        ui.label(version['created_at'].replace('T', ' ')).classes('text-xs text-gray-500')
                        preview = content.replace('\n', ' ')[:PREVIEW_CHARS]
                        ui.label(f'{preview}…（{len(content)} 字）').classes('text-sm truncate')

                    def restore(text=content):
                        session.restore_version(text)
                        dialog.close()

                    ui.button('恢复', on_click=restore).props('flat dense color=indigo')
        with ui.row().classes('w-full justify-end'):
            ui.button('关闭', on_click=dialog.close).props('flat')
    dialog.open()
