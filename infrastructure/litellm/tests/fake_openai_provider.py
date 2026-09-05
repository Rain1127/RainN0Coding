import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


app = FastAPI()
MODE = os.getenv("FAKE_PROVIDER_MODE", "success")
REQUEST_COUNT = 0


@app.get("/health")
async def health():
    return {"status": "ok", "mode": MODE}


@app.get("/test/state")
async def state():
    return {"mode": MODE, "request_count": REQUEST_COUNT}


@app.post("/test/reset")
async def reset():
    global REQUEST_COUNT
    REQUEST_COUNT = 0
    return {"status": "reset"}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    global REQUEST_COUNT
    REQUEST_COUNT += 1
    body = await request.json()
    messages = body.get("messages", [])
    force_all_fail = any(
        message.get("content") == "fail-all"
        for message in messages
        if isinstance(message, dict)
    )
    if MODE == "fail" or force_all_fail:
        return JSONResponse(
            {"error": {"message": "forced upstream failure"}},
            status_code=500,
        )
    return {
        "id": "chatcmpl-contract",
        "object": "chat.completion",
        "created": 1,
        "model": body.get("model", "fake"),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "fallback-ok"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
