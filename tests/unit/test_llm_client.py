"""LLM 客户端：请求构造、服务商地址、流式解析、错误提示。用 MockTransport 拦截 HTTP，不联网。"""
import asyncio
import json

import httpx2
import openai
import pytest

from src.llm.client import GEMINI_BASE_URL, LLMClient, LLMError

CONFIG = {"provider": "openai", "api_key": "sk-test", "base_url": "https://relay.example.com/v1",
          "model": "deepseek-chat", "temperature": 0.3, "proxy": ""}


def sse(*pieces: str) -> bytes:
    events = [
        json.dumps({"id": "x", "object": "chat.completion.chunk", "created": 0, "model": "m",
                    "choices": [{"index": 0, "delta": {"content": p}, "finish_reason": None}]})
        for p in pieces
    ]
    return "".join(f"data: {e}\n\n" for e in events).encode() + b"data: [DONE]\n\n"


class Recorder:
    """记录请求并按预设返回响应的 MockTransport 处理器。"""

    def __init__(self, respond=None):
        self.requests: list[httpx2.Request] = []
        self.proxies: list = []
        self.respond = respond or (lambda request: httpx2.Response(
            200, content=sse("你好", "，", "世界"), headers={"content-type": "text/event-stream"}))

    def __call__(self, request):
        self.requests.append(request)
        return self.respond(request)

    def client(self, **kwargs) -> LLMClient:
        def factory(proxy):
            self.proxies.append(proxy)
            return openai.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(self))
        return LLMClient(http_client_factory=factory, max_retries=0, **kwargs)

    def body(self, index: int = -1) -> dict:
        return json.loads(self.requests[index].content)


def collect(client: LLMClient, config: dict, messages=None) -> list[str]:
    async def run():
        return [t async for t in client.stream(config, messages or [{"role": "user", "content": "hi"}])]
    return asyncio.run(run())


def test_stream_yields_tokens_and_sends_request():
    rec = Recorder()
    assert collect(rec.client(), CONFIG) == ["你好", "，", "世界"]

    request = rec.requests[0]
    assert str(request.url) == "https://relay.example.com/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer sk-test"
    body = rec.body()
    assert body["model"] == "deepseek-chat"
    assert body["stream"] is True
    assert body["temperature"] == 0.3
    assert "top_p" not in body and "presence_penalty" not in body


def test_optional_sampling_params_are_forwarded():
    rec = Recorder()
    collect(rec.client(), {**CONFIG, "top_p": 0.9, "presence_penalty": 0.5, "frequency_penalty": 0})
    body = rec.body()
    assert body["top_p"] == 0.9 and body["presence_penalty"] == 0.5
    assert "frequency_penalty" not in body  # 0 视为未设置，与旧版一致


@pytest.mark.parametrize("base_url", ["", "https://api.openai.com/v1", "https://api.openai.com/v1/"])
def test_google_provider_uses_gemini_compat_endpoint(base_url):
    rec = Recorder()
    collect(rec.client(), {**CONFIG, "provider": "google", "base_url": base_url, "model": "gemini-2.5-flash"})
    assert str(rec.requests[0].url) == GEMINI_BASE_URL + "chat/completions"


def test_openai_provider_defaults_to_official_endpoint():
    rec = Recorder()
    collect(rec.client(), {**CONFIG, "base_url": ""})
    assert str(rec.requests[0].url) == "https://api.openai.com/v1/chat/completions"


def test_missing_api_key_is_rejected_for_remote_services():
    with pytest.raises(LLMError, match="API Key 未设置"):
        collect(Recorder().client(), {**CONFIG, "api_key": ""})


def test_local_services_work_without_api_key():
    rec = Recorder()
    collect(rec.client(), {**CONFIG, "api_key": "", "base_url": "http://localhost:11434/v1"})
    assert rec.requests[0].headers["authorization"] == "Bearer local"


def test_missing_model_is_rejected():
    with pytest.raises(LLMError, match="未设置模型名称"):
        collect(Recorder().client(), {**CONFIG, "model": ""})


@pytest.mark.parametrize("status, message", [
    (401, "API Key 无效"),
    (429, "额度不足"),
    (404, "找不到模型「deepseek-chat」"),
    (500, "模型服务返回错误（500）"),
])
def test_http_errors_become_friendly_messages(status, message):
    rec = Recorder(lambda request: httpx2.Response(status, json={"error": {"message": "boom"}}))
    with pytest.raises(LLMError, match=message):
        collect(rec.client(), CONFIG)


def test_connection_error_mentions_base_url():
    def refuse(request):
        raise httpx2.ConnectError("refused", request=request)
    with pytest.raises(LLMError, match="无法连接到 https://relay.example.com/v1"):
        collect(Recorder(refuse).client(), CONFIG)


def test_clients_are_cached_per_endpoint_key_and_proxy():
    rec = Recorder()
    client = rec.client()
    collect(client, CONFIG)
    collect(client, {**CONFIG, "model": "another-model", "temperature": 1})
    assert len(rec.proxies) == 1  # 同一服务、同一 Key：复用客户端

    collect(client, {**CONFIG, "api_key": "sk-new"})  # 换 Key 后立即生效
    collect(client, {**CONFIG, "proxy": "http://127.0.0.1:7890"})
    assert rec.proxies == [None, None, "http://127.0.0.1:7890"]
    assert rec.requests[2].headers["authorization"] == "Bearer sk-new"


def test_complete_joins_stream():
    assert asyncio.run(Recorder().client().complete(CONFIG, [])) == "你好，世界"


def test_list_models():
    rec = Recorder(lambda request: httpx2.Response(200, json={"object": "list", "data": [
        {"id": "m1", "object": "model", "created": 0, "owned_by": "x"},
        {"id": "m2", "object": "model", "created": 0, "owned_by": "x"},
    ]}))
    assert asyncio.run(rec.client().list_models(CONFIG)) == ["m1", "m2"]
    assert asyncio.run(Recorder().client().list_models({**CONFIG, "api_key": ""})) == []


def test_check_connection_returns_reply():
    rec = Recorder()
    assert asyncio.run(rec.client().check_connection(CONFIG)) == "你好，世界"
    assert "连接测试" in rec.body()["messages"][-1]["content"]


def test_check_connection_reports_friendly_error():
    rec = Recorder(lambda request: httpx2.Response(401, json={"error": {"message": "bad key"}}))
    with pytest.raises(LLMError, match="API Key 无效"):
        asyncio.run(rec.client().check_connection(CONFIG))


def test_check_connection_rejects_empty_reply():
    rec = Recorder(lambda request: httpx2.Response(
        200, content=sse(""), headers={"content-type": "text/event-stream"}))
    with pytest.raises(LLMError, match="没有返回内容"):
        asyncio.run(rec.client().check_connection(CONFIG))
