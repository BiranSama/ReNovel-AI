"""一个浏览器标签页的会话：持有该页的界面状态，处理界面事件并调用应用级服务。

每次打开页面都会创建新的 Session，因此多个标签页的项目、章节、编辑内容互不影响；
项目数据、设置、模型客户端等则由所有会话共享的 Services 提供。
"""
import asyncio
import functools

from nicegui import ui

from src.llm import LLMError
from src.services.batch import BACKUP_SUFFIX, DEFAULT_INSTRUCTION
from src.services.importer import UnsupportedEncoding, decode_text
from src.services.refine import RefineRequest
from src.ui.state import AppState


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

def split_text(text):
    if not text: return []
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return [{'original': line, 'revised': ''} for line in lines]


class Session:
    def __init__(self, services, state: AppState | None = None):
        self.services = services
        self.state = state or AppState()
        self._renderer = None

    @property
    def graph_engine(self):
        """当前项目的图谱（同一项目在各标签页共享）。"""
        return self.services.graphs.get(self.state.current_project_id)

    @safe_sync
    def update_status(self, msg, p=None):
        label, progress = self.state.ui['status_label'], self.state.ui['status_progress']
        if label: label.text = msg
        if progress:
            if p is not None:
                progress.classes(remove='hidden')
                progress.value = p
                if p >= 1.0:  # 3 秒后隐藏进度条；后台任务里没有界面上下文，不能用 ui.timer
                    asyncio.get_running_loop().call_later(3.0, lambda: progress.classes(add='hidden'))
            else:
                progress.classes(add='hidden')

    def stop_workflow(self):
        self.state.stop_signal = True
        ui.notify('已发送停止信号', type='warning')

    def current_text(self):
        """编辑器里当前显示的正文（全文模式取草稿，分段模式取合并结果）。"""
        return self.state.full_text_draft if self.state.view_mode == 'full' else self.merge_text()

    def merge_text(self):
        lines = []
        for seg in self.state.segments:
            content = seg['revised'] if seg['revised'] else seg['original']
            if content.strip(): lines.append(content)
        return "\n\n".join(lines)

    async def _extract_upload_info(self, e):
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

    async def _get_current_chapter_index(self):
        if not self.state.current_project_id or not self.state.current_chapter_id: return 0
        chs = await self.services.pm.get_chapters(self.state.current_project_id)
        for i, c in enumerate(chs):
            if c['id'] == self.state.current_chapter_id: return i + 1
        return 0

    # ==========================
    # 2. 图谱逻辑
    # ==========================
    @safe_sync
    def refresh_graph_ui(self):
        engine, chart = self.graph_engine, self.state.ui['graph_chart']
        if not engine or not chart: return
        data = engine.get_visualization_data()
        if data['nodes']:
            chart.options['series'][0]['data'] = data['nodes']
            chart.options['series'][0]['links'] = data['links']
            chart.update()

    async def bg_build_graph(self, pid, chapter_ids=None):
        """后台更新图谱：只分析内容有变化的章节（可限定章节）。在后台任务中运行，进度显示在状态栏。"""
        engine = self.services.graphs.get(pid)
        if not engine or self.state.graph_task_running: return
        self.state.graph_task_running = True
        self.update_status("图谱更新中...", 0.0)
        try:
            added = await self.services.graph.update(
                engine, pid, on_progress=lambda m, p: (self.update_status(m, p), self.refresh_graph_ui()),
                chapter_ids=chapter_ids)
            self.update_status(f"图谱已更新：新增 {added} 条关系", 1.0)
        except LLMError as e:
            self.update_status(f"图谱更新失败：{e}", 1.0)
        finally:
            self.state.graph_task_running = False
        self.refresh_graph_ui()

    async def update_graph_incrementally(self):
        if not self.state.current_project_id: return
        ui.notify('正在分析有变化的章节...')
        asyncio.create_task(self.bg_build_graph(self.state.current_project_id))

    # ==========================
    # 3. 项目与 IO
    # ==========================
    def register_renderer(self, func):
        self._renderer = func

    def _render(self):
        if self._renderer:
            try: self._renderer()
            except RuntimeError: pass

    @safe_async
    async def refresh_chapter_list(self):
        container = self.state.ui['chapter_list']
        if not container: return
        container.clear()
        if not self.state.current_project_id: return

        chs = await self.services.pm.get_chapters(self.state.current_project_id)
        with container:
            for c in chs:
                act = ' active-chapter' if self.state.current_chapter_id == c['id'] else ''
                ui.label(c['title']).classes(f'w-full px-4 py-2 text-sm cursor-pointer border-b chapter-item{act}') \
                    .on('click', lambda _, cid=c['id']: self.load_chapter(cid))

    async def load_chapter(self, cid):
        c = await self.services.pm.get_chapter_content(cid)
        if c:
            self.state.current_chapter_id = cid
            self.state.segments = split_text(c)
            # 同步全文草稿
            lines = [s['revised'] if s['revised'] else s['original'] for s in self.state.segments]
            self.state.full_text_draft = "\n\n".join(lines)
            self._render()
            await self.refresh_chapter_list()

    @safe_async
    async def switch_project(self, pid, title):
        self.state.current_project_id = pid
        self.state.current_project_title = title

        if self.state.ui['project_title']:
            try: self.state.ui['project_title'].text = title
            except RuntimeError: pass

        self.refresh_graph_ui()
        chs = await self.services.pm.get_chapters(pid)
        if chs: await self.load_chapter(chs[0]['id'])
        else: await self.refresh_chapter_list()

    @safe_async
    async def refresh_project_list(self):
        container = self.state.ui['project_list']
        if not container: return
        container.clear()
        projs = await self.services.pm.get_projects()
        with container:
            for p in projs:
                with ui.card().classes('w-full p-2 mb-1 cursor-pointer hover:bg-indigo-50 border-l-4 border-transparent hover:border-indigo-500') \
                        .on('click', lambda _, pid=p['id'], t=p['title']: self.switch_project(pid, t)):
                    ui.label(p['title']).classes('font-bold text-sm text-slate-700')
                    ui.label(p['created_at'][:10]).classes('text-xs text-gray-400')

    async def auto_load_latest_project(self):
        projs = await self.services.pm.get_projects()
        if projs: await self.switch_project(projs[0]['id'], projs[0]['title'])
        await self.refresh_project_list()

    async def save_all(self):
        # 全文模式先同步回 segments；内容被清空时也要同步，才能保存空章节
        if self.state.view_mode == 'full':
            self.state.segments = split_text(self.state.full_text_draft or "")
            self._render()

        txt = self.merge_text()
        pid, cid = self.state.current_project_id, self.state.current_chapter_id
        if cid:
            await self.services.pm.update_chapter_content(cid, txt)
            if pid:
                self.services.rag.index_chapter(pid, cid, txt)
                # 已建立图谱的项目：后台分析这一章的新内容（内容没变时不会调用模型）
                if self.graph_engine and self.graph_engine.is_built():
                    asyncio.create_task(self.bg_build_graph(pid, {cid}))
            ui.notify('✅ 已保存（记忆已更新）')

    # ==========================
    # 4. 文件处理
    # ==========================
    async def handle_novel_upload(self, e, dialog):
        fname, cbytes = await self._extract_upload_info(e)
        if not cbytes: return ui.notify("文件错误", type='negative')

        try:
            content = decode_text(cbytes)  # 自动识别 UTF-8 / GBK / Big5 等，不再静默丢字
        except UnsupportedEncoding as err:
            return ui.notify(str(err), type='negative')
        pm = self.services.pm
        pid = await pm.create_project(fname, "Imported")
        await pm.import_content(pid, content)

        # Flash Start: 立即向量化
        ui.notify('正在初始化向量记忆...', type='info')
        for c in await pm.get_chapters(pid):
            txt = await pm.get_chapter_content(c['id'])
            if txt: self.services.rag.index_chapter(pid, c['id'], txt)

        with ui.dialog() as d, ui.card():
            ui.label('📚 建立图谱?').classes('font-bold')
            with ui.row():
                ui.button('否', on_click=lambda: d.submit(False)).props('flat')
                ui.button('是', on_click=lambda: d.submit(True)).props('color=indigo')

        should_build = await d
        if dialog: dialog.close()

        await self.switch_project(pid, fname)
        await self.refresh_project_list()

        if should_build:
            asyncio.create_task(self.bg_build_graph(pid))

    async def create_backup(self):
        if not self.state.current_project_id: return
        ui.notify('备份中...')
        await self.services.batch.make_backup(self.state.current_project_id, "(副本)")
        ui.notify('副本创建成功')
        await self.refresh_project_list()
        await self.refresh_backup_list()

    async def refresh_backup_list(self):
        container = self.state.ui.get('backup_list')
        if not container or not self.state.current_project_id: return
        backups = await self.services.pm.get_backups(self.state.current_project_id)
        container.clear()
        with container:
            if not backups: ui.label('当前项目还没有副本').classes('text-xs text-gray-400 p-2')
            for p in backups:
                with ui.row().classes('w-full items-center justify-between px-2 py-1 border-b no-wrap'):
                    with ui.column().classes('gap-0 min-w-0'):
                        ui.label(p['title']).classes('text-sm truncate')
                        ui.label(p['created_at'][:16].replace('T', ' ')).classes('text-xs text-gray-400')
                    ui.button('打开', on_click=lambda _, pid=p['id'], t=p['title']: self.open_backup(pid, t)) \
                        .props('flat dense size=sm')

    async def open_backup_dialog(self):
        self.state.ui['backup_dialog'].open()
        await self.refresh_backup_list()

    async def open_backup(self, pid, title):
        self.state.ui['backup_dialog'].close()
        await self.switch_project(pid, title)

    # ==========================
    # 5. AI Workflow (核心)
    # ==========================
    async def refine_request(self, text, instr):
        return RefineRequest(
            text=text,
            instruction=instr,
            project_id=self.state.current_project_id,
            chapter_index=await self._get_current_chapter_index(),
            persona=self.state.active_system_prompt or "",
        )

    async def run_analyzer(self, text, instr):
        ui.notify('军师分析中...', type='info')
        return await self.services.refine.analyze(await self.refine_request(text, instr))

    async def rewrite_segment(self, seg, instr, dialog_callback=None):
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

        result = await self.services.refine.refine(await self.refine_request(target, instr), on_text=show, on_reject=on_reject)
        seg['revised'] = result.text
        if result.review and result.review.error:
            ui.notify(f'审校未完成：{result.review.error}', type='warning')
        return result

    # ==========================
    # Batch Task
    # ==========================
    async def open_batch_console(self, instruction=""):
        state = self.state
        if not state.current_project_id: return ui.notify('请先导入', type='warning')
        if state.is_batch_running: return ui.notify('已有批量任务在运行', type='warning')
        all_chs = await self.services.pm.get_chapters(state.current_project_id)
        remaining = await self.services.batch.remaining_chapters(state.current_project_id)
        task_conf = {'scope': 'current', 'create_backup': True, 'selected': [], 'instruction': instruction}

        def render_ch_list(container):
            container.clear()
            with container:
                scope = task_conf['scope']; targets = []
                if scope == 'current' and state.current_chapter_id:
                    targets = [c for c in all_chs if c['id'] == state.current_chapter_id]
                elif scope == 'all': targets = all_chs
                elif scope == 'resume': targets = remaining
                task_conf['selected'] = [c['id'] for c in targets]
                for c in targets: ui.label(c['title']).classes('text-sm border-b')

        with ui.dialog() as d, ui.card().classes('w-full max-w-3xl'):
            ui.label('批量任务').classes('text-lg font-bold')
            with ui.row().classes('w-full gap-4'):
                with ui.column().classes('w-1/3'):
                    ui.radio({'current': '本章', 'all': '全书', 'resume': f'继续上次进度（剩 {len(remaining)} 章）'},
                             value='current', on_change=lambda: render_ch_list(ch_area)).bind_value(task_conf, 'scope')
                    ui.checkbox('创建副本（在副本上改写，原项目不动）', value=True).bind_value(task_conf, 'create_backup') \
                        .bind_visibility_from(task_conf, 'scope', backward=lambda s: s != 'resume')
                with ui.column().classes('w-2/3'):
                    ch_area = ui.scroll_area().classes('h-48 border rounded p-2 w-full')
                    render_ch_list(ch_area)
            with ui.row().classes('w-full justify-end'):
                ui.button('启动', on_click=lambda: self.start_batch_execution(task_conf, d)).props('color=indigo')
        d.open()

    async def start_batch_execution(self, conf, dlg):
        state = self.state
        ids = list(conf['selected'])
        if not ids: return ui.notify('无章节')
        dlg.close()

        pid = state.current_project_id
        if conf['create_backup'] and conf['scope'] != 'resume':
            ui.notify('备份中...')
            pid, mapping = await self.services.batch.make_backup(pid)
            ids = [mapping[i] for i in ids]
            await self.switch_project(pid, f"{state.current_project_title} {BACKUP_SUFFIX}")
            await self.refresh_project_list()

        def progress(p):
            if p.chapters_done < p.chapters_total:
                self.update_status(f'批量：{p.chapter_title}（第 {p.chapters_done + 1}/{p.chapters_total} 章，'
                                   f'第 {p.paragraphs_done + 1}/{p.paragraphs_total} 段）', p.fraction)

        state.is_batch_running = True; state.stop_signal = False
        self.update_status("批量任务启动...", 0.0)
        try:
            outcome = await self.services.batch.run(pid, ids, conf.get('instruction') or DEFAULT_INSTRUCTION,
                                                    on_progress=progress, should_stop=lambda: state.stop_signal)
        finally:
            state.is_batch_running = False

        summary = f'完成 {outcome.chapters_done}/{outcome.chapters_total} 章'
        if outcome.error:
            ui.notify(f'批量任务出错已停止（{summary}）：{outcome.error}', type='negative')
        elif outcome.stopped:
            ui.notify(f'批量任务已停止（{summary}）。当前章未完成的部分未保存，可用“继续上次进度”接着跑', type='warning')
        else:
            ui.notify(f'批量任务完成（{summary}）', type='positive')
        if outcome.review_errors:
            ui.notify(f'{outcome.review_errors} 段审校未完成，已保留改写结果', type='warning')
        self.update_status(f'批量：{summary}', 1.0)
        if state.current_chapter_id and state.current_project_id == pid:
            await self.load_chapter(state.current_chapter_id)  # 刷新编辑器里的当前章

    # ==========================
    # Chat Logic
    # ==========================
    async def send_chat_msg(self):
        ui_refs = self.state.ui
        chat_input = ui_refs.get('chat_input')
        if not chat_input: return ui.notify("输入框未就绪", type='warning')
        msg = chat_input.value; chat_input.value = ""
        if not msg: return

        with ui_refs['chat_container']: ui.label(msg).classes('chat-bubble chat-user')
        mode = ui_refs['chat_mode'].value if ui_refs['chat_mode'] else 'chapter'
        with ui_refs['chat_container']: bubble = ui.label('Thinking...').classes('chat-bubble chat-ai')
        res = ""
        try:
            async for t in self.services.chat.answer(msg, self.state.current_project_id,
                                                     await self._get_current_chapter_index(), self.current_text(), mode):
                res += t; bubble.text = res
        except LLMError as e:
            bubble.text = f"出错：{e}"
