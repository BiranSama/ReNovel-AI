import json
import os

# 配置文件存放在 data 目录下
CONFIG_PATH = "data/config.json"

# 默认配置（如果第一次运行，或者配置文件坏了，就用这个）
DEFAULT_CONFIG = {
    'provider': 'openai',
    'api_key': '',
    'base_url': 'https://api.openai.com/v1',
    'model': 'gpt-3.5-turbo',
    'temperature': 0.7,
    'top_p': 0.9,
    'presence_penalty': 0.0,
    'frequency_penalty': 0.0
}

class ConfigManager:
    def __init__(self):
        self.path = CONFIG_PATH
        self._ensure_dir()

    def _ensure_dir(self):
        """确保 data 文件夹存在"""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def load_config(self) -> dict:
        """从硬盘读取配置，如果不存在则返回默认值"""
        if not os.path.exists(self.path):
            return DEFAULT_CONFIG.copy()
        
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                saved_config = json.load(f)
                # 合并默认配置，防止旧版本配置文件缺少新字段导致报错
                config = DEFAULT_CONFIG.copy()
                config.update(saved_config)
                return config
        except Exception as e:
            print(f"读取配置失败: {e}，将使用默认配置")
            return DEFAULT_CONFIG.copy()

    def save_config(self, config: dict):
        """将配置写入硬盘"""
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            print(f"配置已保存至 {self.path}")
        except Exception as e:
            print(f"保存配置失败: {e}")