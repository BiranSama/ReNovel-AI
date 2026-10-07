from nicegui import ui
from src.core.managers import mgr, GraphEngine
from src.ui.state import app_state
from src.llm import LLMError
from src.llm.prompts import assemble_system_prompt
from src.services.refine import RefineRequest
import asyncio
import functools

# ==========================
# 0. 基础工具 (防御性)
# ==========================
def safe_sync(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try: return func(*args, **kwargs)
        except RuntimeError: pass
    return wrapper

def safe_async(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try: return await func(*args, **kwargs)
        except RuntimeError: pass
    return wrapper

@safe_sync
def update_status(msg, p=None):
    if app_state.ui['status_label']: app_state.ui['status_label'].text = msg
    if app_state.ui['status_progress']:
        if p is not None:
            app_state.ui['status_progress'].classes(remove='hidden')
            app_state.ui['status_progress'].value = p
            if p >= 1.0: ui.timer(3.0, lambda: app_state.ui['status_progress'].classes(add='hidden'), once=True)
        else:
            app_state.ui['status_progress'].classes(add='hidden')

def stop_workflow(): 
    app_state.stop_signal = True
    ui.notify('已发送停止信号', type='warning')

def split_text(text):
    if not text: return []
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return [{'original': line, 'revised': ''} for line in lines]

def merge_text():
    lines = []
    for seg in app_state.segments:
        content = seg['revised'] if seg['revised'] else seg['original']
        if content.strip(): lines.append(content)
    return "\n\n".join(lines)

def assemble_prompt(role_key):
    return assemble_system_prompt(mgr.settings.get_role_config(role_key), mgr.settings.is_nsfw_enabled())

async def _extract_upload_info(e):
    filename = "unknown_file"
    if hasattr(e, 'name'): filename = e.name
    elif hasattr(e, 'file') and hasattr(e.file, 'name'): filename = e.file.name
    content = b""
    file_obj = None
    if hasattr(e, 'content'): file_obj = e.content
    elif hasattr(e, 'file'): file_obj = e.file
    if file_obj:
        if hasattr(file_obj, 'read'):
            try: content = await file_obj.read()
            except: content = file_obj.read()
        elif hasattr(file_obj, '_data'):
            content = file_obj._data
    return filename, content

async def _get_current_chapter_index():
    if not app_state.current_project_id or not app_state.current_chapter_id: return 0
    chs = await mgr.pm.get_chapters(app_state.current_project_id)
    for i, c in enumerate(chs):
        if c['id'] == app_state.current_chapter_id: return i + 1
    return 0

# ==========================
# 2. 图谱逻辑
# ==========================
@safe_sync
def refresh_graph_ui():
    if not mgr.current_graph_engine or not app_state.ui['graph_chart']: return
    data = mgr.current_graph_engine.get_visualization_data()
    if data['nodes']:
        app_state.ui['graph_chart'].options['series'][0]['data'] = data['nodes']
        app_state.ui['graph_chart'].options['series'][0]['links'] = data['links']
        app_state.ui['graph_chart'].update()

async def bg_build_graph(pid, content, incremental=False):
    if not GraphEngine: return
    
    g_conf = app_state.settings.get_role_config('graph')
    if not g_conf.get('api_key'):
        w_conf = app_state.settings.get_role_config('writer')
        if w_conf.get('api_key'):
            g_conf = w_conf.copy()
            g_conf['prompt_blocks'] = app_state.settings.get_role_config('graph').get('prompt_blocks', {})
        else:
            ui.notify('错误：未配置 API Key', type='negative')
            return

    update_status("后台图谱构建中...", 0.1)
    app_state.graph_task_running = True
    mgr.load_graph(pid)
    
    chapters = []
    if '第' in content[:1000]: 
        chapters = [{'title': f'Ch{i}', 'content': c} for i, c in enumerate(content.split('第')) if len(c) > 100]
    if len(chapters) < 1:
        chunk_size = 3000
        for i in range(0, len(content), chunk_size):
            chapters.append({'title': f'Part {i//chunk_size + 1}', 'content': content[i:i+chunk_size]})

    update_status(f"正在分析 {len(chapters)} 个切片...", 0.1)

    await mgr.current_graph_engine.build_graph_from_chapters(
        chapters, 
        lambda m, p: (update_status(m,p), refresh_graph_ui()), 
        config=g_conf
    )
    
    app_state.graph_task_running = False
    update_status("✅ 图谱构建完成", 1.0)
    refresh_graph_ui()

async def update_graph_incrementally():
    if not app_state.current_project_id: return
    ui.notify('全书扫描中...')
    chs = await mgr.pm.get_chapters(app_state.current_project_id)
    full_content = ""
    for c in chs:
        txt = await mgr.pm.get_chapter_content(c['id'])
        full_content += f"第{c['title']}\n{txt}\n"
    
    asyncio.create_task(bg_build_graph(app_state.current_project_id, full_content, incremental=True))

# ==========================
# 3. 项目与 IO
# ==========================
_renderer = None
def register_renderer(func): global _renderer; _renderer = func

@safe_async
async def refresh_chapter_list():
    if not app_state.ui['chapter_list']: return
    app_state.ui['chapter_list'].clear()
    if not app_state.current_project_id: return
    
    chs = await mgr.pm.get_chapters(app_state.current_project_id)
    with app_state.ui['chapter_list']:
        for c in chs:
            act = ' active-chapter' if app_state.current_chapter_id == c['id'] else ''
            ui.label(c['title']).classes(f'w-full px-4 py-2 text-sm cursor-pointer border-b chapter-item{act}').on('click', lambda _,cid=c['id']: load_chapter(cid))

async def load_chapter(cid):
    c = await mgr.pm.get_chapter_content(cid)
    if c:
        app_state.current_chapter_id = cid
        app_state.segments = split_text(c)
        
        # 【核心修复】同步全文草稿
        lines = [s['revised'] if s['revised'] else s['original'] for s in app_state.segments]
        app_state.full_text_draft = "\n\n".join(lines)
        
        if _renderer: 
            try: _renderer()
            except RuntimeError: pass
        await refresh_chapter_list()

@safe_async
async def switch_project(pid, title):
    app_state.current_project_id = pid
    app_state.current_project_title = title
    
    if app_state.ui['project_title']: 
        try: app_state.ui['project_title'].text = title
        except RuntimeError: pass
        
    mgr.load_graph(pid)
    chs = await mgr.pm.get_chapters(pid)
    if chs: await load_chapter(chs[0]['id'])
    else: await refresh_chapter_list()

@safe_async
async def refresh_project_list():
    if not app_state.ui['project_list']: return
    app_state.ui['project_list'].clear()
    projs = await mgr.pm.get_projects()
    with app_state.ui['project_list']:
        for p in projs:
            with ui.card().classes('w-full p-2 mb-1 cursor-pointer hover:bg-indigo-50 border-l-4 border-transparent hover:border-indigo-500').on('click', lambda _, pid=p['id'], t=p['title']: switch_project(pid, t)):
                ui.label(p['title']).classes('font-bold text-sm text-slate-700')
                ui.label(p['created_at'][:10]).classes('text-xs text-gray-400')

async def auto_load_latest_project():
    projs = await mgr.pm.get_projects()
    if projs: await switch_project(projs[0]['id'], projs[0]['title'])
    await refresh_project_list()

async def save_all():
    # 如果是全文模式，先同步回 segments
    if app_state.view_mode == 'full':
        if app_state.full_text_draft:
            app_state.segments = split_text(app_state.full_text_draft)
            if _renderer:
                try: _renderer()
                except RuntimeError: pass
    
    txt = merge_text()
    if app_state.current_chapter_id:
        await mgr.pm.update_chapter_content(app_state.current_chapter_id, txt)
        # 实时 RAG 索引
        if app_state.current_project_id: mgr.rag.index_chapter(app_state.current_project_id, app_state.current_chapter_id, txt)
        ui.notify('✅ 已保存 (含RAG更新)')

# ==========================
# 4. 文件处理
# ==========================
async def handle_novel_upload(e, dialog):
    fname, cbytes = await _extract_upload_info(e)
    if not cbytes: return ui.notify("文件错误", type='negative')
    
    content = cbytes.decode('utf-8', 'ignore')
    pid = await mgr.pm.create_project(fname, "Imported")
    await mgr.pm.import_content(pid, content)
    
    # Flash Start: 立即向量化
    ui.notify('正在初始化向量记忆...', type='info')
    chs = await mgr.pm.get_chapters(pid)
    for c in chs:
        txt = await mgr.pm.get_chapter_content(c['id'])
        if txt: mgr.rag.index_chapter(pid, c['id'], txt)
    
    with ui.dialog() as d, ui.card():
        ui.label('📚 建立图谱?').classes('font-bold')
        with ui.row(): 
            ui.button('否', on_click=lambda: d.submit(False)).props('flat')
            ui.button('是', on_click=lambda: d.submit(True)).props('color=indigo')
    
    should_build = await d
    if dialog: dialog.close()
    
    await switch_project(pid, fname)
    await refresh_project_list()
    
    if should_build and GraphEngine:
        await asyncio.sleep(1)
        asyncio.create_task(bg_build_graph(pid, content))

async def create_backup():
    if not app_state.current_project_id: return
    ui.notify('备份中...')
    nid = await mgr.pm.duplicate_project(app_state.current_project_id, "(副本)")
    if nid:
        if mgr.rag: mgr.rag.clone_project_memory(app_state.current_project_id, nid)
        ui.notify('副本创建成功')
        await refresh_project_list()

async def refresh_backup_list(container): pass # 兼容

# ==========================
# 5. AI Workflow (核心)
# ==========================
async def generate_smart_query(target_text, context_prev):
    prompt = f"Context: {context_prev[-300:]}\nTarget: {target_text}\nExtract 3 keywords."
    kw = ""
    try:
        conf = app_state.settings.get_role_config('writer').copy()
        conf['system_prompt'] = "Keyword Extractor" 
        async for token in mgr.llm.stream_rewrite(target_text, prompt, conf): kw += token
    except: return target_text
    return kw.strip()

async def refine_request(text, instr):
    return RefineRequest(
        text=text,
        instruction=instr,
        project_id=app_state.current_project_id,
        chapter_index=await _get_current_chapter_index(),
        persona=app_state.active_system_prompt or "",
    )

async def run_analyzer(text, instr):
    ui.notify('军师分析中...', type='info')
    return await mgr.refine.analyze(await refine_request(text, instr))

async def _atomic_rewrite_segment(seg, instr, dialog_callback=None):
    """单段精修。dialog_callback 为空（批量）时审校不通过自动重试。Writer 失败抛 LLMError。"""
    target = seg['original'] or ""
    if not target.strip(): return

    def show(text):
        if seg.get('ui_component'): seg['ui_component'].value = text

    on_reject = None
    if dialog_callback:
        async def on_reject(review, text):
            action = await dialog_callback(seg, {'score': review.score, 'suggestion': review.suggestion}, text)
            if action['action'] != 'retry': return None
            return action.get('feedback') or review.suggestion

    result = await mgr.refine.refine(await refine_request(target, instr), on_text=show, on_reject=on_reject)
    seg['revised'] = result.text
    if result.review and result.review.error:
        ui.notify(f'审校未完成：{result.review.error}', type='warning')
    return result

async def run_seg_logic(idx, instr, dialog_cb):
    seg = app_state.segments[idx]
    await _atomic_rewrite_segment(seg, instr, dialog_cb)

# ==========================
# Batch Task
# ==========================
async def open_batch_console():
    if not app_state.current_project_id: return ui.notify('请先导入', type='warning')
    all_chs = await mgr.pm.get_chapters(app_state.current_project_id)
    task_conf = {'scope': 'current', 'create_backup': True, 'selected': set()}
    
    def render_ch_list(container):
        container.clear()
        with container:
            scope = task_conf['scope']; targets = []
            if scope == 'current' and app_state.current_chapter_id: 
                targets = [c for c in all_chs if c['id'] == app_state.current_chapter_id]
            elif scope == 'all': targets = all_chs
            task_conf['selected'] = set(c['id'] for c in targets)
            for c in targets: ui.label(c['title']).classes('text-sm border-b')

    with ui.dialog() as d, ui.card().classes('w-full max-w-3xl'):
        ui.label('批量任务').classes('text-lg font-bold')
        with ui.row().classes('w-full gap-4'):
            with ui.column().classes('w-1/3'):
                ui.radio({'current':'本章','all':'全书'}, value='current', on_change=lambda: render_ch_list(ch_area)).bind_value(task_conf, 'scope')
                ui.checkbox('创建副本', value=True).bind_value(task_conf, 'create_backup')
            with ui.column().classes('w-2/3'):
                ch_area = ui.scroll_area().classes('h-48 border rounded p-2 w-full')
                render_ch_list(ch_area)
        with ui.row().classes('w-full justify-end'):
            ui.button('启动', on_click=lambda: start_batch_execution(task_conf, d, all_chs)).props('color=indigo')
    d.open()

async def start_batch_execution(conf, dlg, all_chs):
    ids = conf['selected']
    if not ids: return ui.notify('无章节')
    dlg.close()
    
    pid = app_state.current_project_id
    if conf['create_backup']:
        ui.notify('备份中...')
        pid = await mgr.pm.duplicate_project(pid, "(批量副本)")
        if mgr.rag: mgr.rag.clone_project_memory(app_state.current_project_id, pid)
        await switch_project(pid, app_state.current_project_title+"(批量副本)")
    
    app_state.is_batch_running = True; app_state.stop_signal = False
    update_status("批量任务启动...", 0.1)
    
    targets = [c for c in all_chs if c['id'] in ids]
    global_instr = "精修文本，保持原意，提升文笔。"
    
    for i, ch in enumerate(targets):
        if app_state.stop_signal: break
        update_status(f'处理: {ch["title"]} ({i+1}/{len(targets)})', (i+1)/len(targets))
        
        await load_chapter(ch['id'])
        
        # 核心循环
        for seg in app_state.segments:
            if app_state.stop_signal: break
            if not seg['original'].strip(): continue
            
            # 不传 dialog_callback：审校不通过时自动重试
            try:
                await _atomic_rewrite_segment(seg, global_instr, dialog_callback=None)
            except LLMError as e:
                ui.notify(f'批量任务已停止：{e}', type='negative')
                app_state.stop_signal = True
                break
            
            # 稍微暂停，避免 API 速率限制
            await asyncio.sleep(0.2)
        
        await save_all()
        await mgr.pm.save_progress(pid, ch['id'])
        
    app_state.is_batch_running = False
    update_status("批量任务完成", 1.0)

# ==========================
# Chat Logic
# ==========================
async def send_chat_msg():
    chat_input = app_state.ui.get('chat_input')
    if not chat_input: return ui.notify("输入框未就绪", type='warning')
    msg = chat_input.value; chat_input.value = "" 
    if not msg: return
    
    with app_state.ui['chat_container']: ui.label(msg).classes('chat-bubble chat-user')
    mode = app_state.ui['chat_mode'].value if app_state.ui['chat_mode'] else 'chapter'
    
    ctx = ""
    if mode == 'chapter':
        txt = merge_text()
        k = await generate_smart_query(msg, txt[-500:])
        rag_res = mgr.rag.search_context(k, app_state.current_project_id)
        graph_res = mgr.current_graph_engine.query_context(k, 999, 'reader') if mgr.current_graph_engine else ""
        ctx = f"【本章】\n{txt[:2000]}\n{rag_res}\n{graph_res}"
    else:
        k = await generate_smart_query(msg, "")
        rag_res = mgr.rag.search_context(k, app_state.current_project_id)
        graph_res = mgr.current_graph_engine.query_context(k, 999, 'reader') if mgr.current_graph_engine else ""
        ctx = f"{rag_res}\n{graph_res}"
        
    sys = assemble_prompt('chat')
    conf = app_state.settings.get_role_config('chat').copy(); conf['system_prompt'] = sys
    
    with app_state.ui['chat_container']: bubble = ui.label('Thinking...').classes('chat-bubble chat-ai')
    res = ""; 
    try:
        async for t in mgr.llm.stream_rewrite(f"{ctx}\n问：{msg}", "", conf):
            res += t; bubble.text = res
    except: bubble.text = "Error"