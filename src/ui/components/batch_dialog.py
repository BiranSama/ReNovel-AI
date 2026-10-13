"""批量精修弹窗：选择范围（本章 / 全书 / 继续上次进度）与是否在副本上改写。"""
from nicegui import ui

SCOPES = {'current': '本章', 'all': '全书', 'resume': '继续上次进度'}


async def open_batch_dialog(session):
    state, services = session.state, session.services
    if not state.current_project_id: return ui.notify('请先导入', type='warning')
    if state.is_batch_running or services.batch.is_running(state.current_project_id):
        return ui.notify('这个项目已有批量任务在运行（可能在另一个标签页）', type='warning')
    chapters = await services.pm.get_chapters(state.current_project_id)
    remaining = await services.batch.remaining_chapters(state.current_project_id)
    conf = {'scope': 'current', 'create_backup': True}

    def targets():
        if conf['scope'] == 'current':
            return [c for c in chapters if c['id'] == state.current_chapter_id]
        return chapters if conf['scope'] == 'all' else remaining

    @ui.refreshable
    def chapter_list():
        for c in targets(): ui.label(c['title']).classes('text-sm border-b')

    async def start():
        ids = [c['id'] for c in targets()]
        if not ids: return ui.notify('无章节')
        dialog.close()
        await session.run_batch(ids, state.instruction, create_backup=conf['create_backup'] and conf['scope'] != 'resume')

    labels = dict(SCOPES, resume=f"{SCOPES['resume']}（剩 {len(remaining)} 章）")
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-3xl'):
        ui.label('批量任务').classes('text-lg font-bold')
        with ui.row().classes('w-full gap-4'):
            with ui.column().classes('w-1/3'):
                ui.radio(labels, on_change=chapter_list.refresh).bind_value(conf, 'scope')
                ui.checkbox('创建副本（在副本上改写，原项目不动）').bind_value(conf, 'create_backup') \
                    .bind_visibility_from(conf, 'scope', backward=lambda s: s != 'resume')
            with ui.column().classes('w-2/3'):
                with ui.scroll_area().classes('h-48 border rounded p-2 w-full'):
                    chapter_list()
        with ui.row().classes('w-full justify-end'):
            ui.button('启动', on_click=start).props('color=indigo')
    dialog.open()
