"""测试用的假 OpenAI 兼容服务：/v1/models 与 /v1/chat/completions（支持流式）。

按请求内容返回可预测的结果，让冒烟测试不依赖真实 API Key 和网络。
用法: python fake_llm.py <port>
"""
import asyncio
import json
import sys
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
CALLS: list[dict] = []
EMBEDDING_CALLS: list[int] = []

REWRITE_MARK = "【FAKE改写】"
REJECT_ONCE = "【先驳回一次】"  # 指令里带上它时，第一次审校给低分
REJECT_ALWAYS = "【总是驳回】"  # 指令里带上它时，每次审校都给低分
SLOW = "【慢速】"  # 指令里带上它时，每次调用延迟 1 秒（用于测试停止）
VERY_SLOW = "【很慢】"  # 请求里带上它时延迟 3 秒：后台任务完成前留出时间做界面操作
_rejected: set[str] = set()


def reply_for(messages: list[dict]) -> str:
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user = messages[-1]["content"]
    if "data extractor" in system:  # 图谱三元组抽取
        return json.dumps(
            [{"source": "张三", "relation": "朋友", "target": "李四", "desc": "大学同学", "is_reveal": False}],
            ensure_ascii=False,
        )
    if "请整理这一章的记忆" in user:  # 章节记忆
        title = user.split("【章节标题】\n", 1)[1].split("\n", 1)[0] if "【章节标题】" in user else ""
        return json.dumps({"summary": f"{title}：张三与李四在咖啡馆叙旧。", "characters": ["张三", "李四"],
                           "events": ["张三在咖啡馆遇见李四", "两人聊起往事"],
                           "character_notes": [
                               {"name": "张三", "aliases": ["三哥"], "traits": "念旧", "status": f"{title}末与李四和好"},
                               {"name": "李四", "aliases": [], "traits": "沉稳", "status": ""}]},
                          ensure_ascii=False)
    if "评分" in user:  # Reviewer 打分
        if REJECT_ALWAYS in user:
            return json.dumps({"score": 2, "suggestion": "节奏太慢"}, ensure_ascii=False)
        if REJECT_ONCE in user and REJECT_ONCE not in _rejected:
            _rejected.add(REJECT_ONCE)
            return json.dumps({"score": 3, "suggestion": "形容词太多"}, ensure_ascii=False)
        return json.dumps({"score": 9, "suggestion": "ok"}, ensure_ascii=False)
    if "Extract 3 keywords" in user:  # 检索关键词
        return "张三 李四 咖啡馆"
    return REWRITE_MARK + user[-30:].replace("\n", " ")


@app.get("/v1/models")
def models():
    return {"data": [{"id": "fake-model"}]}


@app.get("/calls")
def calls():
    return CALLS


def char_vector(text: str, dim: int = 64) -> list[float]:
    """按字符计数的确定性向量：共用字越多越相似，足够让检索结果可预测。"""
    vector = [0.0] * dim
    for ch in text:
        vector[ord(ch) % dim] += 1.0
    return vector


@app.post("/v1/embeddings")
async def embeddings(req: Request):
    body = await req.json()
    texts = body["input"] if isinstance(body["input"], list) else [body["input"]]
    EMBEDDING_CALLS.append(len(texts))
    return {"object": "list", "model": body.get("model"),
            "data": [{"object": "embedding", "index": i, "embedding": char_vector(t)} for i, t in enumerate(texts)],
            "usage": {"prompt_tokens": 1, "total_tokens": 1}}


@app.get("/embedding_calls")
def embedding_calls():
    return EMBEDDING_CALLS


@app.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    messages = body["messages"]
    CALLS.append({"stream": body.get("stream"), "last": messages[-1]["content"]})
    if VERY_SLOW in messages[-1]["content"]:
        await asyncio.sleep(3)
    elif SLOW in messages[-1]["content"]:
        await asyncio.sleep(1)
    text = reply_for(messages)
    created = int(time.time())

    if not body.get("stream"):
        return JSONResponse({
            "id": "fake", "object": "chat.completion", "created": created, "model": body.get("model"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })

    def stream():
        for i in range(0, len(text), 8):
            chunk = {
                "id": "fake", "object": "chat.completion.chunk", "created": created, "model": body.get("model"),
                "choices": [{"index": 0, "delta": {"content": text[i:i + 8]}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
