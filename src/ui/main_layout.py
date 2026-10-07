from nicegui import ui, app
from src.core.managers import mgr
from src.ui.state import app_state
from src.ui.components.settings_dialog import SettingsDialog
from src.ui.layouts.panels import create_header, create_left_drawer, create_right_drawer
import src.logic.handlers as h
from src.llm import LLMError
import asyncio

app.on_startup(mgr.init_db)

# ==========================
# CSS 样式补丁
# ==========================
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
    .insert-zone { height: 10px; width: 100%; display: flex; justify-content: center; align-items: center; opacity: 0; cursor: pointer; margin: 4px 0; transition: opacity 0.2s; }
    .insert-zone:hover { opacity: 1; }
    .insert-btn { background-color: #a78bfa; color: white; border-radius: 50%; width: 20px; height: 20px; display: flex; justify-content: center; align-items: center; font-size: 12px; }
</style>
''')

def create_layout():
    # 重置 UI 引用
    for key in list(app_state.ui.keys()):
        app_state.ui[key] = None

    settings = SettingsDialog(mgr.settings)
    settings.create_ui() 
    app_state.settings = mgr.settings
    
    # 注册渲染器
    def safe_refresh():
        try: editor_panel.refresh()
        except: pass
    h.register_renderer(safe_refresh)

    # ==========================
    # 警告弹窗
    # ==========================
    warning_future = None
    def resolve_warn(action, fb=None):
        nonlocal warning_future
        if warning_future and not warning_future.done(): warning_future.set_result({'action': action, 'feedback': fb})
        warn_dlg.close()

    with ui.dialog() as warn_dlg, ui.card().classes('w-full max-w-6xl h-[90vh] flex flex-col border-t-4 border-red-500'):
        with ui.row().classes('justify-between w-full'):
            ui.label('⚠️ 总监意见：质量未达标').classes('text-lg font-bold text-red-600')
            warn_score = ui.label().classes('text-xl font-bold bg-red-100 px-2 rounded')
        with ui.row().classes('flex-grow w-full gap-4 py-2 overflow-hidden'):
            with ui.column().classes('w-1/2 h-full full-height-col'):
                ui.label('📄 原文').classes('font-bold text-gray-500')
                warn_orig = ui.textarea().props('readonly borderless filled').classes('full-height-textarea bg-gray-100 rounded')
            with ui.column().classes('w-1/2 h-full full-height-col'):
                ui.label('📝 当前改写').classes('font-bold text-gray-500')
                warn_rev = ui.textarea().props('readonly borderless filled').classes('full-height-textarea bg-yellow-50 rounded')
        ui.label('💡 修改建议:').classes('font-bold text-indigo-500')
        warn_input = ui.textarea().classes('w-full bg-white border p-1 rounded').props('outlined dense rows=2')
        with ui.row().classes('w-full justify-end items-center'):
            warn_limit = ui.label('已达到最多重试次数，可接受当前结果后手动修改').classes('text-sm text-gray-500')
            warn_retry = ui.button('AI 重写', on_click=lambda: resolve_warn('retry', warn_input.value)).props('outline color=indigo')
            ui.button('强制通过', on_click=lambda: resolve_warn('accept')).props('unelevated color=grey')

    async def show_warning_dialog(seg, r_data, rev_text, original_text=None, can_retry=True):
        nonlocal warning_future
        warn_retry.set_visibility(can_retry); warn_limit.set_visibility(not can_retry)
        warn_score.text = f"{r_data.get('score', 0)}分"
        orig = original_text if original_text is not None else seg.get('original', '') if seg else ''
        warn_orig.value = orig; warn_rev.value = rev_text; warn_input.value = r_data.get('suggestion', '')
        warn_score.update(); warn_orig.update(); warn_rev.update(); warn_input.update()
        warning_future = asyncio.get_running_loop().create_future()
        warn_dlg.open()
        return await warning_future

    # ==========================
    # AI 逻辑
    # ==========================
    async def run_full_rewrite():
        full_text = h.current_text()
        if not full_text.strip(): return ui.notify('内容为空', type='warning')

        request = await h.refine_request(full_text, prompt_input.value or "精修")
        try:
            report = await h.run_analyzer(full_text, request.instruction)
        except LLMError as e:
            return ui.notify(f'军师分析失败：{e}', type='negative')

        with ui.dialog() as d, ui.card().classes('w-full max-w-4xl'):
            ui.label('军师报告').classes('text-lg font-bold text-purple')
            ui.markdown(report).classes('w-full bg-gray-50 p-4 h-64 overflow-auto')
            with ui.row().classes('w-full justify-end'):
                ui.button('取消', on_click=d.close).props('flat')
                ui.button('执行', on_click=lambda: d.submit(True)).props('color=purple')
        if not await d: return
        request.guidance = report

        def show(text):
            if app_state.view_mode == 'full' and app_state.ui.get('full_text_area'):
                app_state.ui['full_text_area'].value = text

        asked = []

        async def ask_user(review, text, can_retry):
            asked.append(review)
            action = await show_warning_dialog(
                None, {'score': review.score, 'suggestion': review.suggestion}, text,
                original_text=full_text, can_retry=can_retry)
            if action['action'] != 'retry': return None
            return action.get('feedback') or review.suggestion

        try:
            result = await mgr.refine.refine(request, on_text=show, on_reject=ask_user)
        except LLMError as e:
            return ui.notify(f'改写失败：{e}', type='negative')

        if app_state.view_mode == 'segment':
            app_state.segments = h.split_text(result.text); editor_panel.refresh()
        else:
            app_state.full_text_draft = result.text
        h.notify_review(result.review, asked)
        ui.notify('全文重写完成')

    async def run_seg_rewrite_ui(idx, button=None):
        seg = app_state.segments[idx]
        if seg.get('busy'): return  # 这一段正在改写，忽略重复点击
        # 段落自己的局部指令优先；为空时用底部的全局指令
        local = (getattr(seg.get('prompt_input'), 'value', '') or '').strip()
        instr = local or prompt_input.value or "润色"
        seg['busy'] = True
        if button: button.props('loading')
        try:
            await h._atomic_rewrite_segment(seg, instr, show_warning_dialog)
        except LLMError as e:
            ui.notify(f'改写失败：{e}', type='negative')
        finally:
            seg['busy'] = False
            if button: button.props(remove='loading')
        if seg.get('ui_component'): seg['ui_component'].value = seg.get('revised', '')

    # ==========================
    # 核心编辑器 (Renderers)
    # ==========================
    def ensure_segments_safe():
        for seg in app_state.segments:
            seg.setdefault('original', '')
            seg.setdefault('revised', '')
            seg.setdefault('prompt_input', None)

    def sync_local():
        if not app_state.full_text_draft: return
        app_state.segments = h.split_text(app_state.full_text_draft)
        ensure_segments_safe()
        app_state.view_mode = 'segment' # 切回分段
        editor_panel.refresh()
        ui.notify('已同步至分段视图')

    @ui.refreshable
    def editor_panel():
        ensure_segments_safe()

        # --- 全文模式 ---
        if app_state.view_mode == 'full':
            # 使用 flex-grow 占据剩余空间 (但不是 h-screen，而是父容器的剩余)
            with ui.row().classes('w-full h-full gap-4 items-stretch p-4 overflow-hidden'):
                # 左侧原文
                with ui.column().classes('w-1/2 h-full full-height-col bg-gray-100 rounded-lg border'):
                    ui.label('📄 原文参考').classes('text-xs font-bold text-gray-500 p-2 border-b bg-gray-50')
                    orig_text = "\n\n".join([s.get('original', '') for s in app_state.segments])
                    ui.textarea(value=orig_text).props('readonly borderless filled').classes('full-height-textarea w-full bg-transparent p-2')

                # 右侧改写
                with ui.column().classes('w-1/2 h-full full-height-col bg-white rounded-lg border-2 border-indigo-100 shadow-sm'):
                    with ui.row().classes('w-full justify-between items-center p-2 border-b bg-indigo-50'):
                        ui.label('📝 改写结果').classes('text-xs font-bold text-indigo-600')
                        ui.button('同步分段', on_click=sync_local).props('dense flat icon=sync color=purple size=sm')

                    # 初始化全文草稿
                    if not app_state.full_text_draft and app_state.segments:
                        lines = [s.get('revised') or s.get('original', '') for s in app_state.segments]
                        app_state.full_text_draft = "\n\n".join(filter(None, lines))

                    ta = ui.textarea().bind_value(app_state, 'full_text_draft').props('borderless placeholder="AI改写内容将实时显示..."').classes('full-height-textarea w-full p-2')
                    app_state.ui['full_text_area'] = ta

        # --- 分段模式 ---
        else:
            with ui.scroll_area().classes('w-full h-full p-6 bg-slate-50'):
                with ui.column().classes('w-full max-w-4xl mx-auto pb-32 gap-4'):
                    for i, seg in enumerate(app_state.segments):
                        with ui.row().classes('w-full segment-card p-4 gap-4 items-start'):
                            # 原文
                            with ui.column().classes('w-[45%]'):
                                ui.label(f'#{i+1} 原文').classes('text-xs font-bold text-gray-400 mb-1')
                                ui.textarea(value=seg.get('original', '')).on('input', lambda e, i=i: app_state.segments[i].__setitem__('original', e.value)).props('autogrow outlined dense').classes('w-full bg-gray-50 text-sm rounded')

                            # 操作区
                            with ui.column().classes('w-[10%] pt-6 gap-2 items-center'):
                                ui.button(icon='auto_fix_high', on_click=lambda e, i=i: run_seg_rewrite_ui(i, e.sender)).props('round flat dense color=indigo').tooltip('精修')
                                ui.button(icon='delete', on_click=lambda i=i: (app_state.segments.pop(i), editor_panel.refresh())).props('round flat dense color=red size=sm')
                                with ui.expansion('', icon='edit_note').props('dense flat'):
                                    seg['prompt_input'] = ui.input(placeholder='局部指令').props('dense outlined').classes('w-32 text-xs')

                            # 改写区
                            with ui.column().classes('w-[45%]'):
                                ui.label('AI 改写').classes('text-xs font-bold text-indigo-400 mb-1')
                                rev_ta = ui.textarea(value=seg.get('revised', '')).on('input', lambda e, i=i: app_state.segments[i].__setitem__('revised', e.value)).props('autogrow outlined dense').classes('w-full bg-white border border-indigo-100 text-sm rounded')
                                seg['ui_component'] = rev_ta

                        # 插入区
                        with ui.element('div').classes('insert-zone').on('click', lambda i=i: (app_state.segments.insert(i+1, {'original':'','revised':''}), editor_panel.refresh())):
                            ui.label('+').classes('insert-btn')

    # ==========================
    # 布局组装 (Layout Assembly)
    # ==========================
    with ui.dialog() as import_dlg, ui.card():
        ui.label('导入').classes('text-lg font-bold')
        ui.upload(on_upload=lambda e: h.handle_novel_upload(e, import_dlg), auto_upload=True).props('accept=.txt flat')

    with ui.dialog() as backup_dlg, ui.card().classes('w-96'):
        ui.label('历史副本').classes('font-bold')
        ui.button('+ 创建副本', on_click=h.create_backup).props('unelevated color=green w-full')
        app_state.ui['backup_list'] = ui.column().classes('w-full mt-2 h-48 scroll-y border rounded')
        app_state.ui['backup_dialog'] = backup_dlg

    left_drawer = create_left_drawer()
    right_drawer = create_right_drawer(h.refresh_graph_ui, h.send_chat_msg, h.update_graph_incrementally)

    create_header(
        left_drawer.toggle,
        right_drawer.toggle,
        settings.open,
        import_dlg.open,
        # 切换模式时强制刷新组件
        lambda m: (setattr(app_state, 'view_mode', m), editor_panel.refresh(), ui.notify(f'切换到{m}模式'))
    )

    # 主容器 (使用 flex-col)
    with ui.column().classes('w-full h-[calc(100vh-56px)] bg-white p-0 flex-col no-wrap') as main_container:
        
        # 1. 编辑器区域 (Flex-Grow 占据所有空间)
        # 这里创建一个 wrapper，并在 wrapper 内部调用 refreshable 组件
        with ui.column().classes('w-full flex-grow overflow-hidden relative'):
            editor_panel() # 【修复】直接在此处调用，它会自动挂载到当前上下文 (main_container -> column)

        # 2. 底部工具栏 (固定高度)
        with ui.row().classes('w-full bg-slate-100 p-4 border-t items-center gap-4 flex-none h-20 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.1)]'):
            with ui.row().classes('gap-1'):
                ui.button('保存', on_click=h.save_all).props('unelevated color=green-6 dense icon=save')
                ui.button(icon='file_download', on_click=lambda: ui.download(h.current_text().encode('utf-8'), 'export.txt')).props('flat round dense')
            
            ui.separator().props('vertical')
            
            prompt_input = ui.input(placeholder='在此输入全局精修指令...').classes('flex-grow text-lg').props('outlined rounded bg-white')

            with ui.row().bind_visibility_from(app_state, 'view_mode', value='full'):
                ui.button('AI 全文重写', on_click=run_full_rewrite).props('unelevated color=purple-6 text-white icon=auto_fix_normal size=md')

            ui.button('批量', on_click=lambda: h.open_batch_console(prompt_input.value)).props('flat dense color=indigo')
            ui.button('停止', on_click=h.stop_workflow).props('outline color=red dense') \
                .bind_visibility_from(app_state, 'is_batch_running')
            with ui.column().classes('gap-0 w-56'):
                app_state.ui['status_label'] = ui.label('').classes('text-xs text-gray-500 truncate w-full')
                app_state.ui['status_progress'] = ui.linear_progress(value=0, show_value=False).classes('hidden w-full')

    # 强制首次渲染与数据加载
    ui.timer(0.1, lambda: (ensure_segments_safe(), editor_panel.refresh()), once=True)
    ui.timer(0.5, h.auto_load_latest_project, once=True)