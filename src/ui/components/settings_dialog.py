"""设置弹窗：各 AI 角色的连接参数与提示词、审校策略。

界面编辑的是设置的副本，点「保存配置」才生效；关闭弹窗不保存则丢弃修改。
"""
import asyncio
import copy

from nicegui import ui

from src.ai.embeddings import API_PRESETS, MIRRORS, EmbeddingError, check_embedder

from src.core.settings import DEFAULT_BLOCKS, REVIEW_MODES, AppSettings, assign, inherits_writer, resolve_role
from src.llm import LLMError
from src.llm.presets import CUSTOM, PRESET_NAMES, apply_preset, detect_preset, find_preset

ROLES = [
    ('writer', 'Writer (作家)', 'edit_note'),
    ('analyzer', 'Analyzer (军师)', 'psychology'),
    ('memory', 'Memory (章节记忆)', 'auto_stories'),
    ('graph', 'Graph (图谱)', 'hub'),
    ('reviewer', 'Reviewer (总监)', 'gavel'),
    ('chat', 'Chat (助手)', 'chat'),
]
PROVIDERS = {'openai': 'OpenAI 兼容', 'google': 'Gemini'}
EMBEDDING_SOURCES = {'local': '本地模型（首次使用时下载，约 25MB，之后离线可用）', 'api': '调用 API（/embeddings 接口）'}


class SettingsDialog:
    def __init__(self, settings: AppSettings, llm, rag=None):
        self.settings = settings
        self.llm = llm
        self.rag = rag  # 用于显示最近一次向量生成失败的原因
        self.config = settings.draft()  # 界面绑定的是副本
        self.preset_selects = {}
        self.dialog = None

    def open(self):
        if not self.dialog: return
        assign(self.config, self.settings.draft())  # 丢弃上次未保存的修改，并取到其他标签页保存的设置
        for role_key, select in self.preset_selects.items():
            select.value = detect_preset(self.config[role_key])
        self.memory_status.refresh()
        self.dialog.open()

    def create_ui(self):
        with ui.dialog() as self.dialog, ui.card().classes('w-full max-w-6xl h-[90vh] flex flex-col settings-dialog'):
            with ui.row().classes('w-full items-center justify-between border-b pb-2'):
                ui.label('AI 引擎配置').classes('text-h6')
                ui.button(icon='close', on_click=self.dialog.close).props('flat round dense')

            with ui.tabs().classes('w-full text-gray-700') as tabs:
                tab_items = {key: ui.tab(label, icon=icon) for key, label, icon in ROLES}
                memory_tab = ui.tab('记忆 (向量)', icon='memory')

            with ui.tab_panels(tabs, value=tab_items['writer']).classes('w-full flex-grow'):
                for role_key, _, _ in ROLES:
                    with ui.tab_panel(tab_items[role_key]).classes(f'role-{role_key}'):
                        if role_key == 'reviewer':
                            self._render_review_options()
                        self._render_role_panel(role_key)
                with ui.tab_panel(memory_tab).classes('memory-settings'):
                    self._render_memory_panel()

            with ui.row().classes('w-full justify-between pt-4 border-t items-center'):
                ui.switch('NSFW 模式').bind_value(self.config, 'enable_nsfw_mode').props('color=red')
                ui.button('保存配置', on_click=self.save_and_close).props('unelevated color=green')

    def _render_review_options(self):
        with ui.row().classes('w-full bg-indigo-50 p-2 rounded mb-4 items-center gap-6 review-options'):
            ui.switch('启用审校').bind_value(self.config, 'enable_reviewer').classes('font-bold')
            ui.select(REVIEW_MODES, label='未通过时').bind_value(self.config, 'review_mode').classes('w-40')
            ui.number('通过分数（0-10）', min=0, max=10, step=1, precision=0) \
                .bind_value(self.config, 'review_threshold').classes('w-36')
            ui.number('最多重试次数', min=0, max=5, step=1, precision=0) \
                .bind_value(self.config, 'max_review_retries').classes('w-32')

    def _render_memory_panel(self):
        conf = self.config['embedding']
        ui.label('向量记忆用于按语义检索前文：改写、审校、聊天时自动带上相关的设定和情节。').classes('text-sm text-gray-600')
        ui.radio(EMBEDDING_SOURCES).bind_value(conf, 'provider')
        with ui.column().classes('w-1/2 gap-2').bind_visibility_from(conf, 'provider', value='local'):
            ui.input('下载镜像', autocomplete=list(MIRRORS)).bind_value(conf, 'mirror').classes('w-full') \
                .tooltip('国内建议 https://hf-mirror.com；也可填官方 https://huggingface.co 或其他镜像')
            ui.input('模型（Hugging Face 仓库）').bind_value(conf, 'local_model').classes('w-full')
        with ui.column().classes('w-1/2 gap-2').bind_visibility_from(conf, 'provider', value='api'):
            with ui.row().classes('gap-2'):
                for name, base_url, model in API_PRESETS:
                    ui.button(name, on_click=lambda b=base_url, m=model: conf.update(base_url=b, model=m)) \
                        .props('outline dense size=sm color=indigo')
            ui.input('Base URL').bind_value(conf, 'base_url').classes('w-full')
            ui.input('API Key', password=True, password_toggle_button=True).bind_value(conf, 'api_key').classes('w-full')
            ui.input('Model').bind_value(conf, 'model').classes('w-full')
            ui.input('Proxy URL', placeholder='http://127.0.0.1:7890').bind_value(conf, 'proxy').classes('w-full')
        with ui.row().classes('items-center gap-4'):
            ui.button('测试向量', icon='science', on_click=lambda e: self._test_embedding(e.sender)) \
                .props('flat dense color=green')
            ui.label('切换后，各项目的记忆会在下次检索时用新模型重新生成').classes('text-xs text-gray-500')
        self.memory_status = ui.refreshable(self._render_memory_status)
        self.memory_status()

    def _render_memory_status(self):
        error = getattr(self.rag, 'last_error', '')
        if error:
            ui.label(f'最近一次向量生成失败：{error}').classes('text-sm text-red-600')

    async def _test_embedding(self, button):
        button.props('loading')
        try:
            dim = await asyncio.to_thread(check_embedder, copy.deepcopy(self.config['embedding']))
        except EmbeddingError as error:
            ui.notify(f'向量不可用：{error}', type='negative', multi_line=True)
        else:
            ui.notify(f'向量可用（{dim} 维）', type='positive')
        finally:
            button.props(remove='loading')

    def _render_role_panel(self, role_key):
        role_conf = self.config[role_key]
        if 'prompt_blocks' not in role_conf:
            role_conf['prompt_blocks'] = copy.deepcopy(DEFAULT_BLOCKS.get(role_key, DEFAULT_BLOCKS['writer']))
        blocks = role_conf['prompt_blocks']

        with ui.row().classes('w-full gap-6 h-full no-wrap'):
            with ui.column().classes('w-1/4 gap-2 border-r pr-4'):
                ui.label('API 参数').classes('font-bold')
                preset = ui.select(PRESET_NAMES, label='服务预设', value=detect_preset(role_conf),
                                   on_change=lambda e: self._apply_preset(role_key, e.value)).classes('w-full')
                self.preset_selects[role_key] = preset
                ui.select(PROVIDERS, label='接口类型').bind_value(role_conf, 'provider').classes('w-full')
                ui.input('API Key', password=True, password_toggle_button=True) \
                    .bind_value(role_conf, 'api_key').classes('w-full')
                if role_key != 'writer':
                    ui.label('API Key 留空时沿用 Writer 的连接').classes('text-xs text-gray-500') \
                        .bind_visibility_from(role_conf, 'api_key', backward=lambda key: not (key or '').strip())
                ui.input('Base URL').bind_value(role_conf, 'base_url').classes('w-full')
                ui.input('Proxy URL', placeholder='http://127.0.0.1:7890').bind_value(role_conf, 'proxy') \
                    .classes('w-full').tooltip('解决连接超时问题')
                model = ui.input('Model').bind_value(role_conf, 'model').classes('w-full')
                with ui.row().classes('w-full gap-2'):
                    ui.button('获取模型', icon='list', on_click=lambda: self._fetch_models(role_key, model)) \
                        .props('flat dense color=indigo')
                    ui.button('测试连接', icon='wifi_tethering', on_click=lambda e: self._test_connection(role_key, e.sender)) \
                        .props('flat dense color=green')
                ui.label('Temperature').classes('text-xs text-gray-500 mt-2')
                ui.slider(min=0, max=2, step=0.1).bind_value(role_conf, 'temperature').props('label-always')

            with ui.column().classes('w-3/4 h-full overflow-y-auto'):
                ui.label(f'{role_key} Prompt').classes('font-bold text-indigo-600')
                ui.textarea(label='Persona').bind_value(blocks, 'persona').classes('w-full').props('autogrow')
                if role_key != 'graph':
                    ui.textarea(label='Objective').bind_value(blocks, 'objective').classes('w-full').props('autogrow')
                    ui.textarea(label='Style').bind_value(blocks, 'style').classes('w-full').props('autogrow')

    def _apply_preset(self, role_key, name):
        role_conf = self.config[role_key]
        if name == CUSTOM or detect_preset(role_conf) == name:
            return  # 打开弹窗时同步选中项，或已经是这个服务：不覆盖用户改过的模型名
        apply_preset(role_conf, name)
        preset = find_preset(name)
        hint = f'，API Key 可在 {preset.key_hint} 申请' if preset.key_hint else '，本地服务无需 API Key'
        ui.notify(f'已填入 {name} 的地址和默认模型{hint}')

    async def _fetch_models(self, role_key, model_input):
        models = await self.llm.list_models(resolve_role(self.config, role_key))
        if not models:
            return ui.notify('没有获取到模型列表，请检查 API Key、Base URL 和网络', type='warning')
        model_input.set_autocomplete(models)
        ui.notify(f'找到 {len(models)} 个模型，在 Model 输入框里输入可筛选')

    async def _test_connection(self, role_key, button):
        conf = resolve_role(self.config, role_key)
        source = '（沿用 Writer 的连接）' if inherits_writer(self.config, role_key) else ''
        button.props('loading')
        try:
            reply = await self.llm.check_connection(conf)
        except LLMError as error:
            ui.notify(f'连接失败{source}：{error}', type='negative', multi_line=True)
        else:
            ui.notify(f'连接成功{source}：模型「{conf.get("model")}」回复：{reply[:30]}', type='positive')
        finally:
            button.props(remove='loading')

    def save_and_close(self):
        self.settings.apply(self.config)
        ui.notify('✅ 配置已保存', type='positive')
        self.dialog.close()
