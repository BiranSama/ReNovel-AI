"""统一的 LLM 客户端：所有服务商都通过 OpenAI 兼容接口接入。

OpenAI、DeepSeek、硅基流动、各类中转、Ollama / LM Studio 本身就是 OpenAI 兼容接口；
Gemini 走 Google 官方的 OpenAI 兼容端点。

每个角色（writer / reviewer / ...）一份配置 dict，字段：
    provider      "openai" | "google"
    api_key       本地服务（localhost）可留空
    base_url      留空时按 provider 取默认地址
    model, temperature, proxy
    可选：top_p, presence_penalty, frequency_penalty, system_prompt
"""
from typing import AsyncIterator, Callable, Optional
from urllib.parse import urlparse

import openai

OPENAI_BASE_URL = "https://api.openai.com/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
DEFAULT_SYSTEM_PROMPT = "你是一个小说助手。"


class LLMError(Exception):
    """调用模型失败。消息面向用户，可以直接展示。"""


def resolve_base_url(config: dict) -> str:
    base_url = (config.get("base_url") or "").strip()
    if config.get("provider") == "google" and base_url.rstrip("/") in ("", OPENAI_BASE_URL):
        # 旧配置里 Gemini 角色的 base_url 默认填的是 OpenAI 地址，这里一并纠正
        return GEMINI_BASE_URL
    return base_url or OPENAI_BASE_URL


def _is_local(url: str) -> bool:
    return urlparse(url).hostname in LOCAL_HOSTS


def needs_api_key(config: dict) -> bool:
    """没填 API Key，且不是不需要 Key 的本地服务。"""
    return not (config.get("api_key") or "").strip() and not _is_local(resolve_base_url(config))


def _sampling_params(config: dict) -> dict:
    params = {"temperature": float(config.get("temperature", 0.7))}
    if config.get("top_p") is not None:
        params["top_p"] = float(config["top_p"])
    for key in ("presence_penalty", "frequency_penalty"):
        if config.get(key):
            params[key] = float(config[key])
    return params


def _default_http_client(proxy: Optional[str]):
    # 代理只作用于这个客户端，不再修改全局环境变量
    return openai.DefaultAsyncHttpxClient(proxy=proxy) if proxy else None


def _friendly_error(error: Exception, config: dict, base_url: str) -> LLMError:
    model = config.get("model", "")
    if isinstance(error, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return LLMError(f"API Key 无效或没有权限（{error.status_code}），请检查设置")
    if isinstance(error, openai.RateLimitError):
        return LLMError("请求过于频繁或额度不足（429），请稍后再试")
    if isinstance(error, openai.NotFoundError):
        return LLMError(f"找不到模型「{model}」或接口地址有误（404），请检查模型名和 Base URL")
    if isinstance(error, openai.APITimeoutError):
        return LLMError(f"连接 {base_url} 超时，请检查网络或代理")
    if isinstance(error, openai.APIConnectionError):
        return LLMError(f"无法连接到 {base_url}，请检查网络、代理或 Base URL")
    if isinstance(error, openai.APIStatusError):
        return LLMError(f"模型服务返回错误（{error.status_code}）：{error.message}")
    return LLMError(f"调用模型失败：{error}")


class LLMClient:
    def __init__(
        self,
        http_client_factory: Callable[[Optional[str]], object] = _default_http_client,
        max_retries: int = 2,
    ):
        self._http_client_factory = http_client_factory
        self._max_retries = max_retries
        self._clients: dict[tuple, openai.AsyncOpenAI] = {}

    def _client(self, config: dict) -> tuple[openai.AsyncOpenAI, str]:
        base_url = resolve_base_url(config)
        if needs_api_key(config):
            raise LLMError("API Key 未设置，请在设置里填写")
        api_key = (config.get("api_key") or "").strip() or "local"  # 本地服务不校验 Key
        proxy = (config.get("proxy") or "").strip() or None

        key = (base_url, api_key, proxy)
        if key not in self._clients:
            self._clients[key] = openai.AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                http_client=self._http_client_factory(proxy),
                max_retries=self._max_retries,
            )
        return self._clients[key], base_url

    async def stream(self, config: dict, messages: list[dict]) -> AsyncIterator[str]:
        """流式生成，逐段产出文本。失败时抛出 LLMError。"""
        model = (config.get("model") or "").strip()
        if not model:
            raise LLMError("未设置模型名称，请在设置里填写")
        client, base_url = self._client(config)
        try:
            response = await client.chat.completions.create(
                model=model, messages=messages, stream=True, **_sampling_params(config)
            )
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except openai.OpenAIError as error:
            raise _friendly_error(error, config, base_url) from error

    async def complete(self, config: dict, messages: list[dict]) -> str:
        return "".join([token async for token in self.stream(config, messages)])

    async def list_models(self, config: dict) -> list[str]:
        """列出可用模型，失败时返回空列表。"""
        try:
            client, _ = self._client(config)
            page = await client.models.list()
            return [model.id for model in page.data]
        except (openai.OpenAIError, LLMError):
            return []
