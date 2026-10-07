import json
import base64
from PIL import Image
import os

class TavernParser:
    def __init__(self):
        pass

    def parse_card(self, file_path: str) -> dict:
        """
        读取角色卡文件 (支持 JSON 或 PNG)
        返回: 包含 name, description, personality 等字段的字典
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"找不到文件: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if ext == '.json':
                return self._parse_json(file_path)
            elif ext == '.png':
                return self._parse_png(file_path)
            else:
                raise ValueError("不支持的文件格式，仅支持 JSON 或 PNG")
        except Exception as e:
            print(f"解析卡片失败: {e}")
            # 返回一个空的安全模板，防止程序崩溃
            return self._get_empty_card()

    def _get_empty_card(self):
        return {
            "name": "未知角色",
            "description": "",
            "personality": "",
            "first_message": "",
            "scenario": ""
        }

    def _parse_json(self, path: str) -> dict:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 兼容不同版本的 JSON 结构 (V1/V2)
            if 'data' in data: 
                return data['data'] # V2 结构
            return data # V1 结构

    def _parse_png(self, path: str) -> dict:
        """
        核心逻辑：从 PNG 的元数据中提取 Tavern 格式信息
        """
        img = Image.open(path)
        img.load() # 强制加载图片信息
        
        info = img.info
        
        # 1. 尝试读取 'chara' 字段 (SillyTavern / V2 格式)
        if 'chara' in info:
            raw_data = info['chara']
            # Base64 解码
            decoded = base64.b64decode(raw_data).decode('utf-8')
            return json.loads(decoded)
            
        # 2. 尝试读取 'ccv3' (Character Card V3)
        elif 'ccv3' in info:
            raw_data = info['ccv3']
            decoded = base64.b64decode(raw_data).decode('utf-8')
            return json.loads(decoded)

        raise ValueError("该图片不包含有效的角色元数据 (不是酒馆卡)")

    def generate_system_prompt(self, card_data: dict) -> str:
        """
        将提取出的数据，组装成 AI 能听懂的 System Prompt
        """
        # 提取关键字段，如果没有则留空
        name = card_data.get('name', '未命名')
        desc = card_data.get('description', '')
        person = card_data.get('personality', '')
        scenario = card_data.get('scenario', '')
        
        # 组装 Prompt (这是 AI 的人设核心)
        prompt = f"""你现在需要根据以下设定来辅助小说创作：

【角色/世界观设定】
- 名称: {name}
- 简介: {desc}
- 性格特征: {person}
- 当前场景/背景: {scenario}

【任务要求】
请使用符合上述设定的语气和风格来改写或续写用户提供的文本。
如果设定是人物，请在对话中体现其性格；如果设定是世界观，请在环境描写中体现其氛围。
"""
        return prompt.strip()

# ==========================================
# 简单的测试脚本
# ==========================================
if __name__ == "__main__":
    # 这是一个模拟的测试
    print("--- 正在测试读卡器 ---")
    parser = TavernParser()
    
    # 我们手动造一个假数据来测试 generate_system_prompt
    fake_card = {
        "name": "赛博侦探",
        "description": "一个生活在2077年的疲惫私家侦探。",
        "personality": "冷漠，喜欢用简短的句子，烟不离手。",
        "scenario": "雨夜的霓虹街道。"
    }
    
    print("输入卡片数据:", fake_card['name'])
    print("-" * 20)
    prompt = parser.generate_system_prompt(fake_card)
    print(prompt)
    print("-" * 20)
    print("测试完成！")