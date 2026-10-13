"""常用模型服务的连接预设：设置界面里一键填入 Base URL、默认模型。

都是 OpenAI 兼容接口；模型名只是建议值，可以用「获取模型」从服务端列出后再改。
"""
from dataclasses import dataclass

from src.llm.client import GEMINI_BASE_URL, OPENAI_BASE_URL


@dataclass(frozen=True)
class Preset:
    name: str
    provider: str
    base_url: str
    model: str
    key_hint: str = ""  # 去哪里申请 Key；本地服务为空


PRESETS = [
    Preset("OpenAI", "openai", OPENAI_BASE_URL, "gpt-4o-mini", "platform.openai.com"),
    Preset("DeepSeek", "openai", "https://api.deepseek.com/v1", "deepseek-chat", "platform.deepseek.com"),
    Preset("硅基流动", "openai", "https://api.siliconflow.cn/v1", "deepseek-ai/DeepSeek-V3", "cloud.siliconflow.cn"),
    Preset("Gemini", "google", GEMINI_BASE_URL, "gemini-2.5-flash", "aistudio.google.com"),
    Preset("Ollama（本地）", "openai", "http://localhost:11434/v1", "qwen2.5:7b"),
]
CUSTOM = "自定义"
PRESET_NAMES = [p.name for p in PRESETS] + [CUSTOM]


def find_preset(name: str):
    return next((p for p in PRESETS if p.name == name), None)


def apply_preset(role_conf: dict, name: str) -> bool:
    """把预设的连接参数写入角色配置（保留 API Key、代理与提示词）。选「自定义」时不改动，返回 False。"""
    preset = find_preset(name)
    if not preset:
        return False
    role_conf.update(provider=preset.provider, base_url=preset.base_url, model=preset.model)
    return True


def detect_preset(role_conf: dict) -> str:
    """按 Base URL 判断当前配置对应哪个预设，认不出时为「自定义」。"""
    base_url = (role_conf.get("base_url") or "").strip().rstrip("/")
    if role_conf.get("provider") == "google" and base_url in ("", OPENAI_BASE_URL):
        return "Gemini"  # 旧配置：Gemini 角色没填或填错 Base URL，实际调用时会纠正为 Gemini 端点
    for preset in PRESETS:
        if base_url == preset.base_url.rstrip("/"):
            return preset.name
    return CUSTOM
