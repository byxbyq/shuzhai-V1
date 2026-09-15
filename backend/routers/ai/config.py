# -*- coding: utf-8 -*-
import os, json, logging
from fastapi import APIRouter, Request

from backend.services.project_service import state
from backend.ai_client import AIClient
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/task-models")
def get_task_models():
    """获取任务型模型映射表"""
    ai = AIClient()
    return {"ok": True, "task_models": ai.TASK_MODEL_MAP, "models": ai.TASK_MODEL_MAP, "provider": ai.get_provider()}

def _mask_api_key(key: str) -> str:
    """脱敏 API Key：只保留前3位和后2位，中间用 **** 替代"""
    if not key or len(key) < 8:
        return ""
    return key[:3] + "****" + key[-2:]


def _is_invalid_key(key) -> bool:
    """判断传入的 key 是否无效（空或脱敏值）：无效时保留已有密钥，防止前端回写覆盖"""
    return (not key) or ("****" in str(key))


def _cfg_path() -> str:
    """配置文件路径：与 AIClient 保持完全一致（项目根 data/ai_config.json）。
    历史 bug：本接口曾读写 backend/data/ai_config.json，而 AIClient 读项目根路径，
    导致设置页填的密钥永远不生效。"""
    return AIClient().config_path

@router.get("/config")
def get_ai_config():
    """返回 AI 配置（api_key 脱敏，不暴露明文密钥）"""
    cfg_path = _cfg_path()
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            # 脱敏：将各 provider 的 api_key 替换为 has_key 标志 + 脱敏预览
            for prov in ("deepseek", "openai", "doubao", "kimi"):
                if prov in config and isinstance(config[prov], dict):
                    raw_key = config[prov].get("api_key", "")
                    # 同时检查环境变量（后端 _get_api_key 优先读环境变量）
                    env_map = {"deepseek": "DEEPSEEK_API_KEY", "openai": "OPENAI_API_KEY",
                               "doubao": "DOUBAO_API_KEY", "kimi": "KIMI_API_KEY"}
                    has_key = bool(raw_key) or bool(os.environ.get(env_map.get(prov, ""), ""))
                    config[prov]["api_key"] = ""
                    config[prov]["has_key"] = has_key
                    if has_key and raw_key:
                        config[prov]["key_preview"] = _mask_api_key(raw_key)
            return {"ok": True, "config": config}
        except Exception as e:
            return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")
    return {"ok": True, "config": None}

@router.get("/api-key")
def get_ai_api_key():
    """安全获取当前 provider 的 API Key（前端按需异步调用，不写入 localStorage）

    返回结构：{ ok, provider, api_key, has_key }
    api_key 仅在内存中短暂使用，不持久化到前端存储。
    """
    try:
        client = AIClient()
        provider = client.get_provider()
        # _get_api_key 优先读环境变量，其次读配置文件
        prov_cfg = client.config.get(provider, {})
        api_key = client._get_api_key(prov_cfg, provider=provider)
        return {
            "ok": True,
            "provider": provider,
            "api_key": api_key,
            "has_key": bool(api_key),
        }
    except Exception as e:
        logger.warning(f"get_ai_api_key error: {e}")
        return {"ok": True, "provider": "deepseek", "api_key": "", "has_key": False}

@router.post("/config")
async def save_ai_config(request: Request):
    try:
        body = await request.json()
        cfg_path = _cfg_path()
        os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
        existing = {}
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        # 兼容前端向导传的顶层字段，映射到嵌套结构
        if "api_key" in body and "deepseek" not in body:
            prov = body.get("provider", existing.get("provider", "deepseek"))
            if prov in ("deepseek", "openai", "doubao", "kimi"):
                ak = body.pop("api_key")
                if prov not in existing:
                    existing[prov] = {}
                # 空/脱敏 key 不覆盖：前端读到的是脱敏值，页面加载时会自动回写保存，
                # 若不拦截会把真实密钥清空（历史事故）
                if not _is_invalid_key(ak):
                    existing[prov]["api_key"] = ak
                if "endpoint" in body:
                    existing[prov]["base_url"] = body.pop("endpoint")
                if "model" in body:
                    existing[prov]["model"] = body.pop("model")
                existing["provider"] = prov
        # 嵌套结构中的空/脱敏 api_key 同样拦截
        for _prov_cfg in body.values():
            if isinstance(_prov_cfg, dict) and "api_key" in _prov_cfg:
                if _is_invalid_key(_prov_cfg["api_key"]):
                    _prov_cfg.pop("api_key")
        def deep_merge(base, update):
            for k, v in update.items():
                if isinstance(v, dict) and isinstance(base.get(k), dict):
                    deep_merge(base[k], v)
                else:
                    base[k] = v
            return base
        merged = deep_merge(existing, body)
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        if state.generator:
            state.generator.ai = AIClient()
        return {"ok": True}
    except Exception as e:
        return err(ErrorCode.INTERNAL_ERROR, f"操作失败: {str(e)}")

@router.get("/test")
def test_ai():
    # 测试连接不依赖当前打开的项目，直接创建 AIClient 验证配置
    try:
        connected = AIClient().test_connection()
        return {"ok": True, "connected": connected}
    except Exception as e:
        logger.warning(f"[test_ai] connection failed: {e}")
        return {"ok": True, "connected": False, "error": str(e)}

@router.post("/test")
def test_ai_post():
    return test_ai()
