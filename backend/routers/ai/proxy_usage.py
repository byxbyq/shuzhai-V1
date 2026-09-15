# -*- coding: utf-8 -*-
import logging
from fastapi import APIRouter

from backend.ai_client import AIClient
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)

from ._models import AIProxyRequest

router = APIRouter()

@router.post("/proxy")
def ai_proxy(data: AIProxyRequest):
    """安全代理：前端只传 prompt，API Key 由后端从环境变量/配置文件读取"""
    import logging
    _log = logging.getLogger(__name__)
    try:
        client = AIClient()
        result = client.generate(data.prompt, temperature=data.temperature, max_tokens=data.max_tokens,
                                 raise_on_error=True)
        return {"ok": True, "content": result}
    except Exception as e:
        _log.warning(f"AI proxy error: {e}")
        return err(ErrorCode.AI_FAILED, f"AI 调用失败: {str(e)}")

@router.get("/usage")
def get_ai_usage():
    """获取 AI 用量统计"""
    try:
        client = AIClient()
        stats = client.get_usage_stats()
        return {"ok": True, "usage": stats}
    except Exception as e:
        logger.warning(f"get_ai_usage error: {e}")
        return err(ErrorCode.INTERNAL_ERROR, f"获取用量失败: {str(e)}")

@router.post("/usage/reset")
def reset_ai_usage():
    """清空用量记录"""
    try:
        client = AIClient()
        client.usage_log = []
        client._save_usage()
        return {"ok": True}
    except Exception as e:
        logger.warning(f"reset_ai_usage error: {e}")
        return err(ErrorCode.INTERNAL_ERROR, f"重置失败: {str(e)}")
