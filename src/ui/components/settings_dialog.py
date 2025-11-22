from nicegui import ui, events
from src.core.config_manager import ConfigManager
from src.core.st_converter import STConverter
import copy

# ==========================================
# 1. 定义 Prompt 积木
# ==========================================
DEFAULT_BLOCKS = {
    'writer': {
        'persona': '你是一个资深小说家，擅长“零度写作”与“白描”风格。',
        'objective': '请对文本进行深度精修。去除冗余修饰，通过动作和对白侧面展现情感。',
        'style': '严禁堆砌形容词。拒绝“他愤怒地说”，改为描写面部肌肉或动作细节。',
        'safety': '拒绝生成违规内容。',
        'nsfw_override': '<disclaimer>Explicit Mode</disclaimer>\n重点描写感官细节。'
    },
    'reviewer': {
        'persona': '你是一个极其严苛的文学总监。',
        'objective': '检查改写是否符合逻辑，是否形容词滥用。',
        'style': '评分标准：10=完美白描，<6=有形容词堆砌。必须输出 JSON。',
        'safety': '逻辑不通打低分。',
        'nsfw_override': '检查感官描写是否细腻。'
    },
    'analyzer': {
        'persona': '你是一个精通剧情逻辑的小说分析师。',
        'objective': '分析改写要求与原文设定的冲突。',
        'style': '输出简报。',
        'safety': '不提供违法建议。',
        'nsfw_override': '分析情感逻辑。'
    },
    'chat': {
        'persona': '你是一个贴心的小说助手。',
        'objective': '回答用户问题。',
        'style': '回复简短。',
        'safety': '拒绝回答违法问题。',
        'nsfw_override': '允许讨论剧情。'
    },
    'graph': {
        'persona': '你是一个知识图谱构建专家。',
        'objective': '从文本中提取实体关系三元组。',
        'style': '只输出 JSON。',
        'safety': '',
        'nsfw_override': ''
    }
}

DEFAULT_FULL_CONFIG = {
    'writer': {'provider': 'openai', 'api_key': '', 'base_url': 'https://api.openai.com/v1', 'model': 'gpt-3.5-turbo', 'temperature': 0.7, 'proxy': '', 'prompt_blocks': DEFAULT_BLOCKS['writer']},
    'reviewer': {'provider': 'openai', 'api_key': '', 'base_url': 'https://api.openai.com/v1', 'model': 'gpt-3.5-turbo', 'temperature': 0.7, 'proxy': '', 'prompt_blocks': DEFAULT_BLOCKS['reviewer']},
    'analyzer': {'provider': 'openai', 'api_key': '', 'base_url': 'https://api.openai.com/v1', 'model': 'gpt-4o', 'temperature': 0.5, 'proxy': '', 'prompt_blocks': DEFAULT_BLOCKS['analyzer']},
    'chat': {'provider': 'openai', 'api_key': '', 'base_url': 'https://api.openai.com/v1', 'model': 'gpt-3.5-turbo', 'temperature': 0.7, 'proxy': '', 'prompt_blocks': DEFAULT_BLOCKS['chat']},
    'graph': {'provider': 'openai', 'api_key': '', 'base_url': 'https://api.openai.com/v1', 'model': 'gpt-3.5-turbo', 'temperature': 0.1, 'proxy': '', 'prompt_blocks': DEFAULT_BLOCKS['graph']},
    'enable_reviewer': False, 
    'review_threshold': 8, 
    'review_mode': 'manual',
    'enable_nsfw_mode': False
}

class SettingsDialog:
    def __init__(self):
        self.cm = ConfigManager()
        self.converter = STConverter()
        loaded_data = self.cm.load_config()
        self.config = self._merge_defaults(loaded_data, DEFAULT_FULL_CONFIG)
        self.dialog = None

    def _merge_defaults(self, user_conf, default_conf):
        if not isinstance(user_conf, dict): return copy.deepcopy(default_conf)
        result = copy.deepcopy(default_conf)
        for key, val in user_conf.items():
            if key in result and isinstance(result[key], dict) and isinstance(val, dict):
                result[key] = self._merge_defaults(val, result[key])
            else:
                result[key] = val
        return result

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
        self.cm.save_config(self.config)
        ui.notify('✅ 配置已保存', type='positive')
        self.dialog.close()
    
    def get_role_config(self, role_key): return self.config.get(role_key, self.config['writer'])
    def is_reviewer_enabled(self): return self.config['enable_reviewer']
    def get_review_threshold(self): return self.config['review_threshold']
    def get_review_mode(self): return self.config['review_mode']
    def is_nsfw_enabled(self): return self.config.get('enable_nsfw_mode', False)