import json
from src.ai.llm_client import LLMClient

class STConverter:
    def __init__(self):
        self.llm = LLMClient()

    async def convert_file_to_prompt(self, file_content: str, config: dict) -> str:
        """
        使用 AI 将 SillyTavern 的复杂预设转换为单一的 System Prompt
        """
        # 1. 尝试解析 JSON (如果用户传的是 JSON 格式的预设)
        try:
            data = json.loads(file_content)
            # 提取关键字段，转成字符串供 AI 参考
            content_summary = json.dumps(data, indent=2, ensure_ascii=False)
        except:
            # 如果不是 JSON，直接当做纯文本处理
            content_summary = file_content

        # 2. 构建转换指令
        conversion_prompt = f"""
你是一个 Prompt 优化专家。
【任务】：将以下 SillyTavern (酒馆) 风格的预设文件内容，整合成一段清晰、连贯的 System Prompt。
【要求】：
1. 提取其中的核心人设、世界观、主要指令 (Main Prompt)。
2. 整合破限 (Jailbreak) 和 NSFW 规则 (如果有)。
3. 去除软件特定的配置代码（如 UI 设置），只保留对 AI 行为的指导。
4. 输出格式为纯文本，适合作为 System Message 输入给 LLM。

【待转换内容】：
{content_summary[:6000]} 
""" 
        # 截断防止 token 溢出，通常预设不会太大

        print("[Converter] 正在调用 AI 进行预设清洗...")
        
        full_result = ""
        try:
            # 使用当前传入的 config (比如 writer 的配置) 来调用 AI
            async for token in self.llm.stream_rewrite("请执行转换", conversion_prompt, config):
                full_result += token
        except Exception as e:
            return f"转换失败: {e}"

        return full_result.strip()