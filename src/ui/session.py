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
from src.services import segments
from src.services.refine import RefineRequest
from src.services.segments import split_text
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



class Session:
    def __init__(self, services, state: AppState | None = None):
        self.services = services
        self.state = state or AppState()
        self._renderer = None
        self.graph_view = None   # 图谱面板，由界面注册
        self.memory_view = None     # 章节记忆面板，由界面注册
        self.character_view = None  # 角色档案面板，由界面注册
        self.style_view = None      # 文风档案面板，由界面注册

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
        """分段模式下各段生效的文字（采纳了候选用候选，否则用原文）。"""
        return segments.merge(self.state.segments)

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

    async def chapter_index(self):
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
        if self.graph_view and self.graph_engine:
            self.graph_view.show(self.graph_engine)

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
    # 2b. 章节记忆
    # ==========================
    async def refresh_memory_ui(self):
        """刷新章节记忆、角色档案和文风面板（切换项目、整理记忆后）。"""
        for view in (self.memory_view, self.character_view, self.style_view):
            if not view: continue
            try: await view.refresh()
            except RuntimeError: pass  # 页面已关闭

    async def bg_update_memory(self, pid, chapter_ids=None):
        """后台整理章节记忆（只整理内容有变化的章节）。已有任务在跑时，把这些章节排到它后面。"""
        state = self.state
        pending = state.memory_pending.setdefault(pid, set())
        if chapter_ids is None: pending.add(None)  # None 表示全部章节
        else: pending.update(chapter_ids)
        if state.memory_task_running: return
        state.memory_task_running = True
        try:
            while state.memory_pending.get(pid):
                wanted = state.memory_pending.pop(pid)
                ids = None if None in wanted else wanted
                self.update_status("章节记忆整理中...", 0.0)
                updated = await self.services.chapter_memory.update(
                    pid, on_progress=self.update_status, chapter_ids=ids)
                self.update_status(f"章节记忆已更新：整理了 {updated} 章", 1.0)
        except LLMError as e:
            state.memory_pending.pop(pid, None)
            self.update_status(f"章节记忆整理失败：{e}", 1.0)
        finally:
            state.memory_task_running = False
        if pid == state.current_project_id:
            await self.refresh_memory_ui()

    async def update_memory_incrementally(self):
        if not self.state.current_project_id: return
        ui.notify('正在整理有变化的章节...')
        asyncio.create_task(self.bg_update_memory(self.state.current_project_id))

    async def bg_analyze(self, pid):
        """导入后整理全书：先整理章节记忆，再建立人物图谱。"""
        await self.bg_update_memory(pid)
        await self.bg_build_graph(pid)

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
        if c is not None:  # 空章节（内容被清空并保存）也要能选中
            self.state.current_chapter_id = cid
            self.state.segments = split_text(c)
            self.state.full_text_draft = segments.merge(self.state.segments)  # 同步全文草稿
            self.state.full_text_history = []
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
        await self.refresh_memory_ui()
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
                await self.services.rag.aindex_chapter(pid, cid, txt)
                # 已整理过记忆 / 建立了图谱的项目：后台分析这一章的新内容（内容没变时不会调用模型）。
                # 用被保存项目的图谱：向量化期间用户可能已经切换到了别的项目
                if await self.services.chapter_store.has_any(pid):
                    asyncio.create_task(self.bg_update_memory(pid, {cid}))
                engine = self.services.graphs.get(pid)
                if engine and engine.is_built():
                    asyncio.create_task(self.bg_build_graph(pid, {cid}))
            ui.notify('✅ 已保存（记忆已更新）')

    async def chapter_versions(self):
        if not self.state.current_chapter_id: return []
        return await self.services.pm.get_chapter_versions(self.state.current_chapter_id)

    def restore_version(self, content):
        """把历史版本放回编辑器（作为原文），保存后才写入；当前保存的内容会留作新的历史版本。"""
        self.state.segments = split_text(content)
        self.state.full_text_draft = segments.merge(self.state.segments)
        self.state.full_text_history = []
        self._render()
        ui.notify('已恢复到编辑器，点「保存」后生效')

    # ==========================
    # 4. 文件处理
    # ==========================
    async def handle_novel_upload(self, e, dialog):
        fname, cbytes = await self._extract_upload_info(e)
        if not cbytes: return ui.notify("文件错误", type='negative')

        try:
            # 自动识别 UTF-8 / GBK / Big5 等；大文件检测耗时，放到线程里
            content = await asyncio.to_thread(decode_text, cbytes)
        except UnsupportedEncoding as err:
            return ui.notify(str(err), type='negative')
        pm = self.services.pm
        pid = await pm.create_project(fname, "Imported")
        await pm.import_content(pid, content)

        # Flash Start: 立即向量化
        ui.notify('正在初始化向量记忆...', type='info')
        for c in await pm.get_chapters(pid):
            txt = await pm.get_chapter_content(c['id'])
            if txt: await self.services.rag.aindex_chapter(pid, c['id'], txt)

        with ui.dialog() as d, ui.card():
            ui.label('📚 整理章节记忆并建立人物图谱？').classes('font-bold')
            ui.label('会调用模型逐章分析，可稍后在右侧栏手动整理').classes('text-xs text-gray-500')
            with ui.row():
                ui.button('否', on_click=lambda: d.submit(False)).props('flat')
                ui.button('是', on_click=lambda: d.submit(True)).props('color=indigo')

        should_build = await d
        if dialog: dialog.close()

        await self.switch_project(pid, fname)
        await self.refresh_project_list()

        if should_build:
            asyncio.create_task(self.bg_analyze(pid))

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
            chapter_index=await self.chapter_index(),
            persona=self.state.active_system_prompt or "",
        )

    async def run_analyzer(self, text, instr):
        ui.notify('军师分析中...', type='info')
        return await self.services.refine.analyze(await self.refine_request(text, instr))

    async def rewrite_segment(self, seg, instr, ask=None):
        """单段精修。ask(review, text, can_retry) 在审校未通过时询问用户，返回修改意见或 None（接受）；
        为空时按审校意见自动重试。Writer 失败抛 LLMError。"""
        target = seg['original'] or ""
        if not target.strip(): return

        def show(text):
            if seg.get('ui_component'): seg['ui_component'].value = text

        result = await self.refine(await self.refine_request(target, instr), show, ask)
        segments.propose(seg, result.text)
        return result

    async def refine(self, request, on_text, ask=None):
        """走统一精修流程；结束后对审校失败或最终未通过给出提示（用户已在弹窗里看过的除外）。"""
        asked = []
        on_reject = None
        if ask:
            async def on_reject(review, text, can_retry):
                asked.append(review)
                return await ask(review, text, can_retry)

        result = await self.services.refine.refine(request, on_text=on_text, on_reject=on_reject)
        self.notify_review(result.review, asked)
        return result

    def notify_review(self, review, asked=()):
        """审校失败或最终未通过时提示；用户已在弹窗里看过这次审校意见的不再重复提示。"""
        if not review: return
        if review.error:
            ui.notify(f'审校未完成：{review.error}', type='warning')
        elif not review.passed and review not in asked:
            ui.notify(f'重试 {self.services.settings.get_max_review_retries()} 次后仍未通过审校（{review.score:g} 分），'
                      f'已保留最后一次改写：{review.feedback}', type='warning', multi_line=True)

    # ==========================
    # Batch Task
    # ==========================
    async def run_batch(self, ids, instruction="", create_backup=True):
        """批量精修指定章节；create_backup 时先复制项目，在副本上改写。"""
        state = self.state
        pid = state.current_project_id
        if create_backup:
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
            outcome = await self.services.batch.run(pid, ids, instruction or DEFAULT_INSTRUCTION,
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
        if outcome.review_rejected:
            ui.notify(f'{outcome.review_rejected} 段重试后仍未通过审校，已保留最后一次改写', type='warning')
        self.update_status(f'批量：{summary}', 1.0)
        if state.current_chapter_id and state.current_project_id == pid:
            await self.load_chapter(state.current_chapter_id)  # 刷新编辑器里的当前章
