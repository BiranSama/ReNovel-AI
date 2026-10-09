"""设置：服务预设、编辑副本（保存前不生效）、审校选项的默认值与取值范围。"""
import pytest

from src.core.settings import AppSettings, inherits_writer, resolve_role
from src.llm.client import GEMINI_BASE_URL, OPENAI_BASE_URL, needs_api_key
from src.llm.presets import CUSTOM, PRESET_NAMES, apply_preset, detect_preset


class MemoryConfig:
    def __init__(self, config=None):
        self.config, self.saved = config or {}, 0

    def load_config(self):
        return self.config

    def save_config(self, config):
        self.config, self.saved = config, self.saved + 1


def test_presets_cover_roadmap_services():
    assert PRESET_NAMES == ["OpenAI", "DeepSeek", "硅基流动", "Gemini", "Ollama（本地）", CUSTOM]


def test_apply_preset_keeps_key_proxy_and_prompts():
    role = {"provider": "openai", "api_key": "sk-x", "base_url": OPENAI_BASE_URL, "model": "gpt",
            "proxy": "http://p", "prompt_blocks": {"persona": "我"}}
    assert apply_preset(role, "DeepSeek")
    assert (role["base_url"], role["model"]) == ("https://api.deepseek.com/v1", "deepseek-chat")
    assert (role["api_key"], role["proxy"], role["prompt_blocks"]) == ("sk-x", "http://p", {"persona": "我"})

    assert apply_preset(role, "Gemini") and role["provider"] == "google" and role["base_url"] == GEMINI_BASE_URL
    assert not apply_preset(role, CUSTOM) and role["provider"] == "google"  # 自定义：不改动


def test_local_preset_needs_no_key():
    role = {"api_key": ""}
    apply_preset(role, "Ollama（本地）")
    assert not needs_api_key(role)


@pytest.mark.parametrize("role, expected", [
    ({"base_url": "https://api.deepseek.com/v1/"}, "DeepSeek"),
    ({"base_url": "https://api.siliconflow.cn/v1"}, "硅基流动"),
    ({"provider": "google", "base_url": OPENAI_BASE_URL}, "Gemini"),  # 旧配置
    ({"base_url": "https://relay.example.com/v1"}, CUSTOM),
    ({}, CUSTOM),
])
def test_detect_preset(role, expected):
    assert detect_preset(role) == expected


def test_draft_changes_take_effect_only_after_apply():
    store = MemoryConfig()
    settings = AppSettings(store)
    draft = settings.draft()
    draft["writer"]["model"] = "deepseek-chat"
    draft["review_mode"] = "auto"
    assert settings.get_role_config("writer")["model"] != "deepseek-chat" and store.saved == 0

    writer = settings.config["writer"]
    settings.apply(draft)
    assert settings.config["writer"] is writer  # 原对象被就地更新
    assert writer["model"] == "deepseek-chat" and settings.get_review_mode() == "auto"
    assert store.saved == 1 and store.config["writer"]["model"] == "deepseek-chat"


def test_review_defaults_follow_roadmap():
    settings = AppSettings(MemoryConfig())
    assert (settings.get_review_mode(), settings.get_review_threshold(), settings.get_max_review_retries()) == \
        ("manual", 8, 2)


def test_apply_clamps_review_numbers():
    settings = AppSettings(MemoryConfig())
    draft = settings.draft()
    draft.update(review_threshold=12.0, max_review_retries=None)  # 数字框超出范围 / 被清空
    settings.apply(draft)
    assert (settings.config["review_threshold"], settings.config["max_review_retries"]) == (10, 2)


def test_resolve_role_on_unsaved_config():
    config = AppSettings(MemoryConfig()).draft()
    config["writer"].update(api_key="sk-w", model="w-model")
    assert inherits_writer(config, "chat") and resolve_role(config, "chat")["api_key"] == "sk-w"
    config["chat"]["api_key"] = "sk-c"
    assert not inherits_writer(config, "chat") and resolve_role(config, "chat")["api_key"] == "sk-c"


def test_embedding_defaults_to_local_model_and_keeps_user_choice():
    embedding = AppSettings(MemoryConfig()).config["embedding"]
    assert (embedding["provider"], embedding["local_model"], embedding["mirror"]) == \
        ("local", "Xenova/bge-small-zh-v1.5", "https://hf-mirror.com")
    custom = AppSettings(MemoryConfig({"embedding": {"provider": "api", "model": "bge-m3"}})).config["embedding"]
    assert (custom["provider"], custom["model"], custom["mirror"]) == ("api", "bge-m3", "https://hf-mirror.com")


def test_saving_only_writes_fields_changed_in_this_dialog():
    """两个标签页同时打开设置：各自保存时只写入自己改过的项，不会用旧值覆盖对方的修改。"""
    settings = AppSettings(MemoryConfig())
    tab_a, base_a = settings.draft(), settings.draft()
    tab_b, base_b = settings.draft(), settings.draft()

    tab_a["writer"]["model"] = "deepseek-chat"
    settings.apply(tab_a, base_a)
    tab_b["review_mode"] = "auto"
    settings.apply(tab_b, base_b)

    assert settings.config["writer"]["model"] == "deepseek-chat"
    assert settings.config["review_mode"] == "auto"


def test_default_model_matches_the_preselected_preset():
    """全新安装时首次启动引导预选的服务（按默认 Base URL 识别）与默认模型一致，只填 Key 就能用推荐模型。"""
    from src.llm.presets import find_preset

    writer = AppSettings(MemoryConfig()).config["writer"]
    assert writer["model"] == find_preset(detect_preset(writer)).model
