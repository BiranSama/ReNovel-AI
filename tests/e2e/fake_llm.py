"""测试用的假 OpenAI 兼容服务：/v1/models 与 /v1/chat/completions（支持流式）。

按请求内容返回可预测的结果，让冒烟测试不依赖真实 API Key 和网络。
用法: python fake_llm.py <port>
"""
import json
import sys
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
CALLS: list[dict] = []

REWRITE_MARK = "【FAKE改写】"
REJECT_ONCE = "【先驳回一次】"  # 指令里带上它时，第一次审校给低分
_rejected: set[str] = set()


def reply_for(messages: list[dict]) -> str:
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user = messages[-1]["content"]
    if "data extractor" in system:  # 图谱三元组抽取
        return json.dumps(
            [{"source": "张三", "relation": "朋友", "target": "李四", "desc": "大学同学", "is_reveal": False}],
            ensure_ascii=False,
        )
    if "评分" in user:  # Reviewer 打分
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


@app.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    messages = body["messages"]
    CALLS.append({"stream": body.get("stream"), "last": messages[-1]["content"]})
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
