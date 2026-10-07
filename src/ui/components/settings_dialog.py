from nicegui import ui, events
from src.core.settings import AppSettings, DEFAULT_BLOCKS
from src.core.st_converter import STConverter
import copy

class SettingsDialog:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.converter = STConverter()
        self.config = settings.config  # 界面直接绑定共享的设置
        self.dialog = None

    def open(self):
        if self.dialog: self.dialog.open()

    def create_ui(self):
        with ui.dialog() as self.dialog, ui.card().classes('w-full max-w-6xl h-[90vh] flex flex-col'):
            with ui.row().classes('w-full items-center justify-between border-b pb-2'):
                ui.label('AI 引擎配置').classes('text-h6')
                ui.button(icon='close', on_click=self.dialog.close).props('flat round dense')

            with ui.tabs().classes('w-full text-gray-700') as tabs:
                tab_writer = ui.tab('Writer (作家)', icon='edit_note')
                tab_analyzer = ui.tab('Analyzer (军师)', icon='psychology')
                tab_graph = ui.tab('Graph (图谱)', icon='hub')
                tab_reviewer = ui.tab('Reviewer (总监)', icon='gavel')
                tab_chat = ui.tab('Chat (助手)', icon='chat')

            with ui.tab_panels(tabs, value=tab_writer).classes('w-full flex-grow'):
                with ui.tab_panel(tab_writer): self._render_role_panel('writer')
                with ui.tab_panel(tab_analyzer): self._render_role_panel('analyzer')
                with ui.tab_panel(tab_graph): self._render_role_panel('graph')
                with ui.tab_panel(tab_chat): self._render_role_panel('chat')
                with ui.tab_panel(tab_reviewer):
                    with ui.row().classes('w-full bg-indigo-50 p-2 rounded mb-4 items-center'):
                        ui.label('启用校验').classes('font-bold mr-4')
                        ui.switch('Enable').bind_value(self.config, 'enable_reviewer')
                    self._render_role_panel('reviewer')

            with ui.row().classes('w-full justify-between pt-4 border-t items-center'):
                ui.switch('NSFW 模式').bind_value(self.config, 'enable_nsfw_mode').props('color=red')
                ui.button('保存配置', on_click=self.save_and_close).props('unelevated color=green')

    def _render_role_panel(self, role_key):
        role_conf = self.config[role_key]
        if 'prompt_blocks' not in role_conf:
            role_conf['prompt_blocks'] = copy.deepcopy(DEFAULT_BLOCKS.get(role_key, DEFAULT_BLOCKS['writer']))
        blocks = role_conf['prompt_blocks']

        with ui.row().classes('w-full gap-6 h-full no-wrap'):
            with ui.column().classes('w-1/4 gap-4 border-r pr-4'):
                ui.label('API 参数').classes('font-bold')
                ui.select(['openai', 'google'], label='Provider').bind_value(role_conf, 'provider').classes('w-full')
                ui.input('API Key', password=True).bind_value(role_conf, 'api_key').classes('w-full')
                ui.input('Base URL').bind_value(role_conf, 'base_url').classes('w-full')
                
                # 【新增】代理设置
                ui.input('Proxy URL', placeholder='http://127.0.0.1:7890').bind_value(role_conf, 'proxy').classes('w-full').tooltip('解决连接超时问题')
                
                ui.input('Model').bind_value(role_conf, 'model').classes('w-full')
                # 【修复】使用 props('label-always') 而不是 label=True
                ui.slider(min=0, max=2, step=0.1).bind_value(role_conf, 'temperature').props('label-always')

            with ui.column().classes('w-3/4 h-full overflow-y-auto'):
                ui.label(f'{role_key} Prompt').classes('font-bold text-indigo-600')
                ui.textarea(label='Persona').bind_value(blocks, 'persona').classes('w-full').props('autogrow')
                if role_key != 'graph':
                    ui.textarea(label='Objective').bind_value(blocks, 'objective').classes('w-full').props('autogrow')
                    ui.textarea(label='Style').bind_value(blocks, 'style').classes('w-full').props('autogrow')

    def save_and_close(self):
        self.settings.save()
        ui.notify('✅ 配置已保存', type='positive')
        self.dialog.close()

