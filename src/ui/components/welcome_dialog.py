"""首次启动引导：还没有可用的模型服务时，引导选择服务、填写 API Key 并测试连接。

只设置 Writer 的连接；其他角色没填 Key 时沿用 Writer 的连接，之后可在设置里分别调整。
"""
from nicegui import ui

from src.llm import LLMError
from src.llm.client import needs_api_key
from src.llm.presets import CUSTOM, PRESET_NAMES, apply_preset, detect_preset, find_preset


def needs_setup(settings) -> bool:
    return needs_api_key(settings.config["writer"])


class WelcomeDialog:
    def __init__(self, settings, llm):
        self.settings, self.llm = settings, llm
        self.draft, self.baseline = settings.draft(), settings.draft()
        writer = self.draft["writer"]
        with ui.dialog().props('persistent') as self.dialog, ui.card().classes('w-full max-w-xl welcome-dialog'):
            ui.label('欢迎使用 Re:Novel').classes('text-h6')
            ui.label('改写、续写、整理记忆都需要一个大模型服务。选择服务并填入 API Key 即可开始；'
                     '其他功能默认沿用这里的连接，之后可以在设置里分别调整。').classes('text-sm text-gray-600')
            ui.select(PRESET_NAMES, label='模型服务', value=detect_preset(writer),
                      on_change=lambda e: self._apply_preset(e.value)).classes('w-full')
            self.hint = ui.label().classes('text-xs text-gray-500')
            ui.input('API Key', password=True, password_toggle_button=True).bind_value(writer, 'api_key').classes('w-full')
            ui.input('Base URL').bind_value(writer, 'base_url').classes('w-full')
            ui.input('Model').bind_value(writer, 'model').classes('w-full')
            with ui.row().classes('w-full justify-between items-center'):
                self.test_button = ui.button('测试连接', icon='wifi_tethering', on_click=self.test).props('flat color=green')
                with ui.row().classes('gap-1'):
                    ui.button('稍后再说', on_click=self.dialog.close).props('flat')
                    ui.button('保存并开始', on_click=self.save).props('unelevated color=indigo')
        self._show_hint(detect_preset(writer))

    def _apply_preset(self, name):
        writer = self.draft["writer"]
        if name != CUSTOM and detect_preset(writer) != name:
            apply_preset(writer, name)
        self._show_hint(name)

    def _show_hint(self, name):
        preset = find_preset(name)
        if not preset:
            self.hint.text = '填写任意 OpenAI 兼容接口的地址、Key 和模型名'
        elif preset.key_hint:
            self.hint.text = f'API Key 可在 {preset.key_hint} 申请'
        else:
            self.hint.text = '本地服务无需 API Key，请先启动 Ollama 并下载模型'

    async def test(self):
        self.test_button.props('loading')
        try:
            reply = await self.llm.check_connection(dict(self.draft["writer"]))
        except LLMError as error:
            ui.notify(f'连接失败：{error}', type='negative', multi_line=True)
        else:
            ui.notify(f'连接成功：模型回复「{reply[:30]}」', type='positive')
        finally:
            self.test_button.props(remove='loading')

    def save(self):
        if needs_api_key(self.draft["writer"]):
            return ui.notify('请填写 API Key（本地服务除外）', type='warning')
        self.settings.apply(self.draft, self.baseline)
        self.dialog.close()
        ui.notify('设置已保存，点右上角「+」导入一本小说开始吧', type='positive')
