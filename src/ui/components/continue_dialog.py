"""续写弹窗：在全书末尾续写新章节，或在当前章节某段之后续写；生成草稿、审校，采纳后才保存并进入记忆。"""
from nicegui import ui

from src.llm import LLMError
from src.services.continuation import LENGTHS, tail

MODES = {'chapter': '在全书末尾续写新章节', 'paragraph': '在当前章节某段之后续写'}


async def open_continue_dialog(session, editor):
    state = session.state
    if not state.current_project_id: return ui.notify('请先导入或打开一本书', type='warning')
    session.sync_segments_from_draft()  # 全文工作台：段落数按当前草稿计算
    chapters = await session.services.pm.get_chapters(state.current_project_id)
    has_chapter = bool(state.current_chapter_id and state.segments)
    conf = {'mode': 'chapter', 'after': len(state.segments), 'outline': '', 'length': 800,
            'title': f'第{len(chapters) + 1}章'}
    draft = {'text': '', 'request': None}

    with ui.dialog() as dialog, ui.card().classes('w-full max-w-4xl continue-dialog'):
        ui.label('续写').classes('text-lg font-bold')
        ui.radio(MODES if has_chapter else {'chapter': MODES['chapter']}, on_change=lambda: invalidate()) \
            .bind_value(conf, 'mode').props('inline')
        with ui.row().classes('w-full items-center gap-4'):
            ui.input('新章节标题').bind_value(conf, 'title').bind_visibility_from(conf, 'mode', value='chapter')
            ui.number(f'在第几段之后（共 {len(state.segments)} 段）', min=0, max=len(state.segments), step=1, precision=0,
                      on_change=lambda: invalidate()) \
                .bind_value(conf, 'after').bind_visibility_from(conf, 'mode', value='paragraph').classes('w-48')
            ui.select(LENGTHS, label='篇幅').bind_value(conf, 'length').classes('w-48')
        ui.textarea('大纲 / 走向（可选）', placeholder='如：李四终于说出当年的真相，两人不欢而散') \
            .bind_value(conf, 'outline').props('autogrow outlined').classes('w-full')
        area = ui.textarea('续写草稿（可修改；采纳后才保存）').props('autogrow outlined') \
            .classes('w-full continue-draft').bind_value(draft, 'text')
        result_label = ui.label().classes('text-sm text-gray-500 continue-review')

        def invalidate():
            """生成后改了续写位置：草稿是按原来的位置写、审的，不能采纳到新位置。"""
            if draft['request']:
                draft['request'] = None
                adopt_button.disable()
                result_label.text = '续写位置已改动，请重新生成'

        async def generate():
            generate_button.props('loading'); adopt_button.disable()
            draft['request'] = None
            request = await session.continue_request(conf['mode'], conf['after'], conf['outline'],
                                                     conf['length'], conf['title'])

            def show(text):
                area.value = text

            async def ask(review, text, can_retry):
                return await editor.review.ask(review, tail(request.preceding, 1500), text, can_retry)

            try:
                result = await session.continue_text(request, show, ask)
            except LLMError as e:
                return ui.notify(f'续写失败：{e}', type='negative')
            finally:
                generate_button.props(remove='loading')
            draft['text'], draft['request'] = result.text, request
            review = result.review
            if review and review.score is not None:
                result_label.text = f'审校 {review.score:g} 分' + \
                    (f' · 文风 {review.style_score:g}' if review.style_score is not None else '')
            adopt_button.enable()

        async def adopt():
            text, request = (draft['text'] or '').strip(), draft['request']
            if not text or not request: return ui.notify('请先生成草稿', type='warning')
            adopt_button.props('loading')
            try:
                await session.adopt_continuation(request, text, conf['title'])
            except ValueError as e:
                return ui.notify(str(e), type='warning')
            finally:
                adopt_button.props(remove='loading')
            dialog.close()
            if request.mode == 'chapter':
                await session.refresh_chapter_list()
            ui.notify('已采纳续写，正在更新记忆')

        with ui.row().classes('w-full justify-end'):
            ui.button('关闭', on_click=dialog.close).props('flat')
            generate_button = ui.button('生成', icon='auto_awesome', on_click=generate).props('outline color=indigo')
            adopt_button = ui.button('采纳', icon='check', on_click=adopt).props('unelevated color=green')
            adopt_button.disable()
    dialog.open()
