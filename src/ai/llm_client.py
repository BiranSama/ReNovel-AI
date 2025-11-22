import httpx
import os
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

class LLMClient:
    def __init__(self):
        pass

    def _apply_proxy(self, config: dict):
        """强制设置代理环境变量"""
        proxy = config.get('proxy', '').strip()
        if proxy:
            # 这里的 key 必须覆盖全，以防万一
            os.environ['http_proxy'] = proxy
            os.environ['https_proxy'] = proxy
            os.environ['HTTP_PROXY'] = proxy
            os.environ['HTTPS_PROXY'] = proxy
            print(f"[LLMClient] 已启用代理: {proxy}")

    async def get_available_models(self, config: dict) -> list:
        provider = config.get('provider', 'openai')
        self._apply_proxy(config) # 应用代理
        
        if provider != 'openai': return []
        api_key = config.get('api_key', '')
        base_url = config.get('base_url', 'https://api.openai.com/v1')
        
        if not api_key: return []

        try:
            if base_url.endswith('/v1'): url = f"{base_url}/models"
            else: url = f"{base_url}/v1/models"
            headers = {"Authorization": f"Bearer {api_key}"}
            
            async with httpx.AsyncClient(trust_env=True) as client:
                resp = await client.get(url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    return [item['id'] for item in data.get('data', [])]
        except: pass
        return []

    def _get_llm(self, config: dict):
        provider = config.get('provider', 'openai')
        api_key = config.get('api_key', '')
        
        # 应用代理
        self._apply_proxy(config)
        
        if not api_key: raise ValueError("API Key 未设置")

        if provider == 'google':
            return ChatGoogleGenerativeAI(
                model=config.get('model', 'gemini-1.5-flash'),
                google_api_key=api_key,
                temperature=config.get('temperature', 0.7),
                top_p=config.get('top_p', 0.9),
                convert_system_message_to_human=True,
                transport='rest' # 这一行对代理很重要
            )
        elif provider == 'openai':
            kwargs = {
                'model': config.get('model', 'gpt-3.5-turbo'),
                'api_key': api_key,
                'base_url': config.get('base_url', 'https://api.openai.com/v1'),
                'temperature': config.get('temperature', 0.7),
                'streaming': True
            }
            if config.get('presence_penalty'): kwargs['presence_penalty'] = config.get('presence_penalty')
            if config.get('frequency_penalty'): kwargs['frequency_penalty'] = config.get('frequency_penalty')
            return ChatOpenAI(**kwargs)
        else:
            raise ValueError(f"不支持的服务商: {provider}")

    async def stream_rewrite(self, text: str, instruction: str, config: dict):
        llm = self._get_llm(config)
        
        system_prompt_content = config.get('system_prompt', '你是一个小说助手。')
        
        messages = [
            SystemMessage(content=system_prompt_content),
            HumanMessage(content=f"指令：{instruction}\n\n内容：\n{text}")
        ]

        async for chunk in llm.astream(messages):
            if hasattr(chunk, 'content'):
                yield chunk.content