from nicegui import ui, app
from src.interfaces.state import app_state, ViewMode
from src.di.container import container, configure_container, get_llm_config
from src.shared.types import LLMConfig, Provider, Result
from src.utils.logger import Log
from src.utils.security import mask_api_key
import asyncio
import json


def create_layout():
    from src.interfaces.controllers.editor_controller import EditorController
    from src.interfaces.controllers.project_controller import ProjectController
    
    editor_ctrl = EditorController()
    project_ctrl = ProjectController()
    
    async def on_startup():
        await project_ctrl.init_database()
        Log.system("Database initialized")
    
    app.on_startup(on_startup)
    
    ui.add_head_html('''
    <style>
        .full-height-col { display: flex; flex-direction: column; height: 100%; }
        .full-height-textarea { display: flex; flex-direction: column; flex-grow: 1; height: 100%; }
        .full-height-textarea .q-field__control,
        .full-height-textarea .q-field__native {
            height: 100% !important; min-height: 100% !important; max-height: none !important; resize: none !important;
        }
        .full-height-textarea textarea {
            overflow-y: auto !important; font-family: "Consolas", monospace; line-height: 1.8; font-size: 16px; color: #334155;
        }
        .segment-card { background: white; border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); transition: all 0.2s; }
        .segment-card:hover { transform: translateY(-1px); box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    </style>
    ''')
    
    with ui.header().classes('bg-white shadow-md h-14 items-center px-4'):
        ui.button(icon='menu', on_click=lambda: left_drawer.toggle()).props('flat dense')
        ui.label('Re:Novel AI').classes('text-xl font-bold text-indigo-600')
        
        ui.space()
        
        project_label = ui.label().classes('text-gray-500 text-sm')
        app_state.ui['project_title'] = project_label
        
        ui.space()
        
        ui.button(icon='settings', on_click=lambda: settings_dialog.open()).props('flat dense')
        ui.button(icon='history', on_click=lambda: backup_dialog.open()).props('flat dense')
    
    with ui.left_drawer() as left_drawer:
        with ui.column().classes('p-4 gap-2'):
            ui.label('项目列表').classes('text-lg font-bold')
            project_list = ui.column().classes('w-full gap-1')
            app_state.ui['project_list'] = project_list
            
            ui.separator()
            
            ui.label('章节列表').classes('text-lg font-bold mt-4')
            chapter_list = ui.column().classes('w-full gap-1')
            app_state.ui['chapter_list'] = chapter_list
    
    with ui.right_drawer() as right_drawer:
        with ui.column().classes('p-4 gap-2'):
            ui.label('知识图谱').classes('text-lg font-bold')
            graph_view = ui.element('div').classes('w-full h-64 bg-gray-100 rounded')
            
            ui.separator()
            
            ui.label('AI 助手').classes('text-lg font-bold mt-4')
            chat_input = ui.input(placeholder='输入问题...').classes('w-full')
            chat_output = ui.element('div').classes('w-full h-32 bg-gray-50 rounded overflow-auto')
    
    with ui.dialog() as settings_dialog:
        with ui.card().classes('w-96'):
            ui.label('设置').classes('text-lg font-bold')
            
            provider_select = ui.select(
                ['openai', 'google'],
                value='openai',
                label='LLM Provider'
            ).classes('w-full')
            
            model_input = ui.input(
                label='Model',
                value='gpt-4'
            ).classes('w-full')
            
            api_key_input = ui.input(
                label='API Key',
                password=True,
                password_toggle_button=True
            ).classes('w-full')
            
            base_url_input = ui.input(
                label='Base URL (Optional)'
            ).classes('w-full')
            
            temperature_slider = ui.slider(
                min=0.0,
                max=2.0,
                step=0.1,
                value=0.7,
                label='Temperature'
            ).classes('w-full')
            
            async def save_settings():
                config = LLMConfig(
                    provider=Provider(provider_select.value),
                    model=model_input.value,
                    api_key=api_key_input.value,
                    base_url=base_url_input.value or None,
                    temperature=temperature_slider.value,
                )
                configure_container(config)
                ui.notify(f'设置已保存 (API Key: {mask_api_key(config.api_key)})')
                settings_dialog.close()
            
            ui.button('保存', on_click=save_settings).props('color=primary')
            ui.button('取消', on_click=settings_dialog.close).props('flat')
    
    with ui.dialog() as backup_dialog:
        with ui.card().classes('w-96'):
            ui.label('历史备份').classes('text-lg font-bold')
            backup_list = ui.column().classes('w-full mt-2 h-48 overflow-auto')
            ui.button('关闭', on_click=backup_dialog.close).props('flat')
    
    with ui.dialog() as import_dialog:
        with ui.card():
            ui.label('导入小说').classes('text-lg font-bold')
            
            async def handle_upload(e):
                result = await project_ctrl.import_novel(e)
                if result.is_ok():
                    ui.notify(f'导入成功: {result.value}')
                    await refresh_project_list()
                    import_dialog.close()
                else:
                    ui.notify(f'导入失败: {result.error}', type='negative')
            
            ui.upload(on_upload=handle_upload, auto_upload=True).props('accept=.txt flat')
    
    @ui.refreshable
    def editor_panel():
        if app_state.view_mode == ViewMode.FULL:
            with ui.row().classes('w-full h-full gap-4 items-stretch p-4 overflow-hidden'):
                with ui.column().classes('w-1/2 h-full full-height-col bg-gray-100 rounded-lg border'):
                    ui.label('原文参考').classes('text-xs font-bold text-gray-500 p-2 border-b bg-gray-50')
                    orig_text = "\n\n".join([s.get('original', '') for s in app_state.segments])
                    ui.textarea(value=orig_text).props('readonly borderless filled').classes('full-height-textarea w-full bg-transparent p-2')
                
                with ui.column().classes('w-1/2 h-full full-height-col bg-white rounded-lg border-2 border-indigo-100 shadow-sm'):
                    with ui.row().classes('w-full justify-between items-center p-2 border-b bg-indigo-50'):
                        ui.label('改写结果').classes('text-xs font-bold text-indigo-600')
                        ui.button('同步分段', on_click=sync_to_segments).props('dense flat icon=sync color=purple size=sm')
                    
                    if not app_state.full_text_draft and app_state.segments:
                        lines = [s.get('revised') or s.get('original', '') for s in app_state.segments]
                        app_state.full_text_draft = "\n\n".join(filter(None, lines))
                    
                    ta = ui.textarea().bind_value(app_state, 'full_text_draft').props('borderless placeholder="AI改写内容将实时显示..."').classes('full-height-textarea w-full p-2')
                    app_state.ui['full_text_area'] = ta
        else:
            with ui.scroll_area().classes('w-full h-full p-6 bg-slate-50'):
                with ui.column().classes('w-full max-w-4xl mx-auto pb-32 gap-4'):
                    for i, seg in enumerate(app_state.segments):
                        with ui.row().classes('w-full segment-card p-4 gap-4 items-start'):
                            with ui.column().classes('w-[45%]'):
                                ui.label(f'#{i+1} 原文').classes('text-xs font-bold text-gray-400 mb-1')
                                ui.textarea(value=seg.get('original', '')).on(
                                    'input', 
                                    lambda e, i=i: app_state.segments[i].__setitem__('original', e.value)
                                ).props('autogrow outlined dense').classes('w-full bg-gray-50 text-sm rounded')
                            
                            with ui.column().classes('w-[10%] pt-6 gap-2 items-center'):
                                ui.button(
                                    icon='auto_fix_high',
                                    on_click=lambda i=i: rewrite_segment(i)
                                ).props('round flat dense color=indigo').tooltip('精修')
                                ui.button(
                                    icon='delete',
                                    on_click=lambda i=i: delete_segment(i)
                                ).props('round flat dense color=red size=sm')
                            
                            with ui.column().classes('w-[45%]'):
                                ui.label('AI 改写').classes('text-xs font-bold text-indigo-400 mb-1')
                                rev_ta = ui.textarea(value=seg.get('revised', '')).on(
                                    'input',
                                    lambda e, i=i: app_state.segments[i].__setitem__('revised', e.value)
                                ).props('autogrow outlined dense').classes('w-full bg-white border border-indigo-100 text-sm rounded')
                                seg['ui_component'] = rev_ta
    
    def sync_to_segments():
        if not app_state.full_text_draft:
            return
        app_state.segments = split_text(app_state.full_text_draft)
        app_state.view_mode = ViewMode.SEGMENT
        editor_panel.refresh()
        ui.notify('已同步至分段视图')
    
    def split_text(text: str) -> list[dict]:
        if not text:
            return []
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return [{'original': line, 'revised': ''} for line in lines]
    
    def merge_text() -> str:
        lines = [s.get('revised') or s.get('original', '') for s in app_state.segments]
        return "\n\n".join(filter(None, lines))
    
    async def rewrite_segment(idx: int):
        seg = app_state.segments[idx]
        original_text = seg.get('original', '')
        if not original_text:
            return ui.notify('内容为空', type='warning')
        
        instruction = prompt_input.value or "润色"
        
        ui.notify('AI 正在处理...')
        
        try:
            result = await editor_ctrl.rewrite_segment(
                project_id=app_state.current_project_id,
                chapter_id=app_state.current_chapter_id,
                chapter_index=app_state.current_chapter_index,
                original_text=original_text,
                instruction=instruction,
            )
            
            if result.is_ok():
                seg['revised'] = result.value.rewritten_text
                if seg.get('ui_component'):
                    seg['ui_component'].value = result.value.rewritten_text
                ui.notify('改写完成')
            else:
                ui.notify(f'改写失败: {result.error}', type='negative')
        except Exception as e:
            Log.error(f"Rewrite segment failed: {e}")
            ui.notify(f'错误: {e}', type='negative')
    
    def delete_segment(idx: int):
        app_state.segments.pop(idx)
        editor_panel.refresh()
    
    async def full_rewrite():
        full_text = app_state.full_text_draft if app_state.view_mode == ViewMode.FULL else merge_text()
        if not full_text.strip():
            return ui.notify('内容为空', type='warning')
        
        instruction = prompt_input.value or "精修"
        
        ui.notify('AI 正在处理全文...')
        
        try:
            app_state.full_text_draft = ""
            if app_state.ui.get('full_text_area'):
                app_state.ui['full_text_area'].value = ""
            
            async for chunk in editor_ctrl.stream_rewrite(
                project_id=app_state.current_project_id,
                chapter_id=app_state.current_chapter_id,
                chapter_index=app_state.current_chapter_index,
                original_text=full_text,
                instruction=instruction,
            ):
                app_state.full_text_draft += chunk
                if app_state.ui.get('full_text_area'):
                    app_state.ui['full_text_area'].value = app_state.full_text_draft
            
            if app_state.view_mode == ViewMode.SEGMENT:
                app_state.segments = split_text(app_state.full_text_draft)
                editor_panel.refresh()
            
            ui.notify('全文改写完成')
        except Exception as e:
            Log.error(f"Full rewrite failed: {e}")
            ui.notify(f'错误: {e}', type='negative')
    
    async def save_all():
        if not app_state.current_chapter_id:
            return ui.notify('请先选择章节', type='warning')
        
        content = merge_text()
        result = await editor_ctrl.save_chapter(
            chapter_id=app_state.current_chapter_id,
            content=content,
        )
        
        if result.is_ok():
            ui.notify('保存成功')
        else:
            ui.notify(f'保存失败: {result.error}', type='negative')
    
    async def refresh_project_list():
        project_list.clear()
        result = await project_ctrl.get_projects()
        
        if result.is_ok():
            with project_list:
                for proj in result.value:
                    ui.button(
                        proj.get('title', 'Untitled'),
                        on_click=lambda p=proj: switch_project(p)
                    ).props('flat dense align=left').classes('w-full text-left')
    
    async def switch_project(proj: dict):
        app_state.current_project_id = proj.get('id')
        app_state.current_project_title = proj.get('title', '')
        
        if app_state.ui.get('project_title'):
            app_state.ui['project_title'].text = app_state.current_project_title
        
        await refresh_chapter_list()
    
    async def refresh_chapter_list():
        if not app_state.current_project_id:
            return
        
        chapter_list.clear()
        result = await project_ctrl.get_chapters(app_state.current_project_id)
        
        if result.is_ok():
            with chapter_list:
                for chap in result.value:
                    ui.button(
                        f"第{chap.get('index', 0)}章",
                        on_click=lambda c=chap: load_chapter(c)
                    ).props('flat dense align=left').classes('w-full text-left')
    
    async def load_chapter(chap: dict):
        app_state.current_chapter_id = chap.get('id')
        app_state.current_chapter_index = chap.get('index', 0)
        
        result = await editor_ctrl.get_chapter_content(chap.get('id'))
        
        if result.is_ok():
            content = result.value
            app_state.segments = split_text(content)
            app_state.full_text_draft = content
            editor_panel.refresh()
            ui.notify(f'已加载第{app_state.current_chapter_index}章')
        else:
            ui.notify(f'加载失败: {result.error}', type='negative')
    
    with ui.column().classes('w-full h-[calc(100vh-56px)] bg-white p-0 flex-col no-wrap'):
        with ui.column().classes('w-full flex-grow overflow-hidden relative'):
            editor_panel()
        
        with ui.row().classes('w-full bg-slate-100 p-4 border-t items-center gap-4 flex-none h-20'):
            with ui.row().classes('gap-1'):
                ui.button('保存', on_click=save_all).props('unelevated color=green-6 dense icon=save')
                ui.button(
                    icon='file_download',
                    on_click=lambda: ui.download(merge_text().encode('utf-8'), 'export.txt')
                ).props('flat round dense')
            
            ui.separator().props('vertical')
            
            prompt_input = ui.input(placeholder='在此输入全局精修指令...').classes('flex-grow text-lg').props('outlined rounded bg-white')
            
            with ui.row().bind_visibility_from(app_state, 'view_mode', value=ViewMode.FULL):
                ui.button('AI 全文重写', on_click=full_rewrite).props('unelevated color=purple-6 text-white icon=auto_fix_normal size=md')
            
            ui.button('导入', on_click=import_dialog.open).props('flat dense color=indigo')
    
    ui.timer(0.5, refresh_project_list, once=True)
