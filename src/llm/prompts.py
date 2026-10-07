"""提示词组装与模型输出解析（纯函数，不依赖界面）。"""
import json
from typing import Optional


def assemble_system_prompt(role_config: dict, nsfw: bool = False, persona: str = "") -> str:
    """把设置里的提示词积木拼成系统提示词；persona（如角色卡人设）放在最前面。"""
    blocks = role_config.get("prompt_blocks") or {}
    if blocks:
        safety = blocks.get("nsfw_override", "") if nsfw else blocks.get("safety", "")
        prompt = (f"### Role\n{blocks.get('persona', '')}\n### Task\n{blocks.get('objective', '')}\n"
                  f"### Style\n{blocks.get('style', '')}\n### Safety\n{safety}")
    else:
        prompt = role_config.get("system_prompt", "")
    return f"{persona}\n{prompt}" if persona else prompt


def parse_json_object(text: str) -> Optional[dict]:
    """从模型输出里取出第一个 { 到最后一个 } 之间的 JSON 对象，失败返回 None。"""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def section(title: str, body: str) -> str:
    """生成一个【标题】段落；正文为空时返回空串，便于拼接时省略。"""
    body = (body or "").strip()
    return f"【{title}】\n{body}" if body else ""


def join_sections(*parts: str) -> str:
    return "\n\n".join(part for part in parts if part)
