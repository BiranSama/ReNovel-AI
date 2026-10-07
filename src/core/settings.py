"""应用设置：各 AI 角色的连接参数与提示词积木、审校策略。

所有浏览器标签页共享同一份设置；设置弹窗只负责界面绑定和保存。
"""
import copy

from src.ai.embeddings import DEFAULT_API_MODEL, DEFAULT_LOCAL_MODEL, DEFAULT_MIRROR
from src.core.config_manager import ConfigManager
from src.llm.client import needs_api_key

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
    'review_mode': 'manual',     # manual：未通过时弹窗询问；auto：自动按审校意见重试
    'max_review_retries': 2,
    'enable_nsfw_mode': False,
    # 向量记忆：local 用本地中文模型（首次使用时下载），api 用 OpenAI 兼容的 /embeddings 接口
    'embedding': {'provider': 'local', 'local_model': DEFAULT_LOCAL_MODEL, 'mirror': DEFAULT_MIRROR,
                  'api_key': '', 'base_url': '', 'model': DEFAULT_API_MODEL, 'proxy': ''},
}
REVIEW_MODES = {'manual': '弹窗询问我', 'auto': '自动按意见重试'}

# 角色没填 API Key 时沿用 Writer 的连接，但保留自己的提示词和温度
_INHERITED_KEYS = ("provider", "api_key", "base_url", "model", "proxy")


def merge_defaults(user_conf, default_conf):
    if not isinstance(user_conf, dict):
        return copy.deepcopy(default_conf)
    result = copy.deepcopy(default_conf)
    for key, val in user_conf.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = merge_defaults(val, result[key])
        else:
            result[key] = val
    return result


def resolve_role(config: dict, role_key: str) -> dict:
    """角色配置副本：缺 API Key 时沿用 Writer 的连接（设置界面测试未保存的配置时也用它）。"""
    conf = copy.deepcopy(config.get(role_key, config["writer"]))
    writer = config["writer"]
    if role_key != "writer" and needs_api_key(conf) and not needs_api_key(writer):
        conf.update({key: writer.get(key) for key in _INHERITED_KEYS})
    return conf


def inherits_writer(config: dict, role_key: str) -> bool:
    return role_key != "writer" and needs_api_key(config[role_key]) and not needs_api_key(config["writer"])


def assign(target: dict, source: dict) -> None:
    """把 source 的内容就地写入 target，嵌套的 dict 保持原对象（界面绑定的仍是同一个对象）。"""
    for key, val in source.items():
        if isinstance(val, dict) and isinstance(target.get(key), dict):
            assign(target[key], val)
        else:
            target[key] = copy.deepcopy(val)


class AppSettings:
    def __init__(self, config_manager: ConfigManager | None = None):
        self.cm = config_manager or ConfigManager()
        self.config = merge_defaults(self.cm.load_config(), DEFAULT_FULL_CONFIG)

    def save(self) -> None:
        self.cm.save_config(self.config)

    def draft(self) -> dict:
        """供设置界面编辑的副本；保存前不影响正在使用的设置。"""
        return copy.deepcopy(self.config)

    def apply(self, draft: dict) -> None:
        """采用编辑后的设置并保存。数字框被清空时用默认值。"""
        assign(self.config, draft)
        for key, low, high in (("review_threshold", 0, 10), ("max_review_retries", 0, 5)):
            value = self.config.get(key)
            self.config[key] = DEFAULT_FULL_CONFIG[key] if value is None else int(min(max(value, low), high))
        self.save()

    def get_role_config(self, role_key: str) -> dict:
        return self.config.get(role_key, self.config["writer"])

    def resolve_role(self, role_key: str) -> dict:
        """供实际调用使用的角色配置副本：缺 API Key 时沿用 Writer 的连接。"""
        return resolve_role(self.config, role_key)

    def is_reviewer_enabled(self) -> bool:
        return bool(self.config["enable_reviewer"])

    def get_review_threshold(self) -> float:
        return float(self.config["review_threshold"])

    def get_review_mode(self) -> str:
        return self.config["review_mode"]

    def get_max_review_retries(self) -> int:
        return int(self.config.get("max_review_retries", 2))

    def is_nsfw_enabled(self) -> bool:
        return bool(self.config.get("enable_nsfw_mode", False))
