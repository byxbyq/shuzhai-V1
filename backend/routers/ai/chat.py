# -*- coding: utf-8 -*-
import json, logging, threading, queue as queue_module
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.services.project_service import state, get_generator
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)

from ._models import ChatRequest

router = APIRouter()

@router.post("/chat")
def ai_chat(data: ChatRequest):
    if not state.project: return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    gen = get_generator()
    # 重新加载世界观设定（确保拿到最新设定）
    gen.reload_world()
    # 支持前端传入max_tokens覆盖默认值
    extra_kwargs = {}
    if hasattr(data, 'max_tokens') and data.max_tokens:
        extra_kwargs['max_tokens'] = data.max_tokens
    result = gen.chat(data.messages, temperature=data.temperature, **extra_kwargs)
    return {"ok": True, "content": result}

@router.post("/chat/stream")
def ai_chat_stream(data: ChatRequest):
    """C2: SSE 流式聊天端点"""
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "没有打开的项目")
    gen = get_generator()
    gen.reload_world()
    extra_kwargs = {}
    if hasattr(data, 'max_tokens') and data.max_tokens:
        extra_kwargs['max_tokens'] = data.max_tokens

    q = queue_module.Queue()

    def on_chunk(chunk):
        q.put(chunk)

    def run_generation():
        try:
            gen.chat(data.messages, temperature=data.temperature, on_chunk=on_chunk, **extra_kwargs)
        except Exception as e:
            q.put({"error": str(e)})
        finally:
            q.put(None)

    thread = threading.Thread(target=run_generation, daemon=True)
    thread.start()

    def event_stream():
        while True:
            try:
                chunk = q.get(timeout=300)
            except Exception:
                yield 'data: {"error": "timeout"}\n\n'
                break
            if chunk is None:
                yield 'data: {"done": true}\n\n'
                break
            if isinstance(chunk, dict) and "error" in chunk:
                yield f'data: {json.dumps(chunk)}\n\n'
                break
            yield f'data: {json.dumps({"content": chunk})}\n\n'

    return StreamingResponse(event_stream(), media_type="text/event-stream")
