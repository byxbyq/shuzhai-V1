# -*- coding: utf-8 -*-
"""书斋 V66 - AI 模型客户端

支持的 Provider：
  - deepseek  : DeepSeek V4 系列（默认）
  - ollama    : Ollama 本地模型
  - openai    : OpenAI GPT 系列
  - doubao    : 豆包（火山引擎 ark，OpenAI 兼容接口）
  - kimi      : Kimi / 月之暗面 Moonshot（OpenAI 兼容接口）

API Key 读取优先级（每个 provider 独立）：
  1. 对应的环境变量（见下方列表）
  2. data/ai_config.json 中的 api_key 字段

环境变量映射：
  DEEPSEEK_API_KEY  → deepseek
  OPENAI_API_KEY    → openai
  DOUBAO_API_KEY    → doubao（火山引擎 Ark API Key）
  KIMI_API_KEY      → kimi（月之暗面 Moonshot API Key）
"""
import json, os, time, logging, threading
import httpx
from typing import Callable, Tuple

logger = logging.getLogger(__name__)

# 进程级写锁：防止并发请求同时实例化 AIClient 时竞争同一临时文件
_save_config_lock = threading.Lock()


class AIClientException(Exception):
    """AI 调用异常 — 区分正常输出与调用失败"""
    def __init__(self, message: str, error_type: str = "unknown"):
        super().__init__(message)
        self.error_type = error_type  # config_error / network_error / api_error / timeout / parse_error


class AIClient:
    """统一 AI 调用接口"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "..", "data", "ai_config.json")
        self.config_path = config_path
        self.config = self._load_config()
        self._ensure_defaults()
        # 使用 httpx.Client 复用连接，300 秒超时匹配 AI 调用需求
        self._client = httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0))
        # 用量追踪
        self.usage_log: list = []
        self._usage_file = os.path.join(os.path.dirname(self.config_path), "ai_usage.json")
        self._load_usage()

    def _load_config(self) -> dict:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning("ai_config.json 损坏 (%s)，使用空配置并覆盖", e)
        return {}

    def _save_config(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        # 原子写：先写唯一临时文件再替换，避免进程被强杀时留下空/半截文件
        # （空文件会在下次启动时被判定为损坏并用空配置覆盖，导致密钥丢失）
        tmp_path = f"{self.config_path}.{os.getpid()}.{time.time_ns()}.tmp"
        try:
            with _save_config_lock:
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self.config_path)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise

    # ── 用量追踪 ──────────────────────────────────

    # 各 provider 的单价（元/百万 token，仅估算）
    _PRICING = {
        "deepseek": {"input": 1.0, "output": 2.0},
        "openai": {"input": 2.5, "output": 10.0},
        "doubao": {"input": 0.8, "output": 2.0},
        "kimi": {"input": 12.0, "output": 12.0},
        "ollama": {"input": 0, "output": 0},
    }

    def _load_usage(self):
        try:
            if os.path.exists(self._usage_file):
                with open(self._usage_file, 'r', encoding='utf-8') as f:
                    self.usage_log = json.load(f)
        except Exception:
            self.usage_log = []

    def _save_usage(self):
        try:
            os.makedirs(os.path.dirname(self._usage_file), exist_ok=True)
            # 只保留最近500条
            if len(self.usage_log) > 500:
                self.usage_log = self.usage_log[-500:]
            with open(self._usage_file, 'w', encoding='utf-8') as f:
                json.dump(self.usage_log, f, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"保存用量日志失败: {e}")

    def _record_usage(self, provider: str, model: str, usage: dict, task: str = "", task_type: str = "general"):
        """记录一次 API 调用的 token 用量

        Args:
            provider: 提供商名称
            model: 模型名称
            usage: API 返回的 usage 字典
            task: 任务描述（如 chapter_outline / chapter_content）
            task_type: 任务类型分类：生成 / 校验 / 蒸馏 / 拆书 / 其他（默认 general）
        """
        if not usage:
            return
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
        pricing = self._PRICING.get(provider, {"input": 0, "output": 0})
        cost = (prompt_tokens * pricing["input"] + completion_tokens * pricing["output"]) / 1_000_000
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "provider": provider,
            "model": model,
            "task": task,
            "task_type": task_type,
            "thinking": self.config.get(provider, {}).get("_thinking_level", ""),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_cny": round(cost, 4),
        }
        # P3-4: 可选 project/workflow 标签透传（由 generate() 设置）
        tags = getattr(self, "_usage_tags", None) or {}
        if tags.get("project"):
            entry["project"] = tags["project"]
        if tags.get("workflow"):
            entry["workflow"] = tags["workflow"]
        self.usage_log.append(entry)
        self._save_usage()

    def get_usage_stats(self) -> dict:
        """获取用量统计"""
        total_input = sum(e.get("prompt_tokens", 0) for e in self.usage_log)
        total_output = sum(e.get("completion_tokens", 0) for e in self.usage_log)
        total_cost = sum(e.get("cost_cny", 0) for e in self.usage_log)
        # 按天统计（含 task_type 明细）
        by_day = {}
        for e in self.usage_log:
            day = e.get("timestamp", "")[:10]
            if day not in by_day:
                by_day[day] = {"calls": 0, "tokens": 0, "cost": 0, "by_task_type": {}}
            by_day[day]["calls"] += 1
            by_day[day]["tokens"] += e.get("total_tokens", 0)
            by_day[day]["cost"] += e.get("cost_cny", 0)
            # 按 task_type 聚合
            tt = e.get("task_type", "general")
            if tt not in by_day[day]["by_task_type"]:
                by_day[day]["by_task_type"][tt] = {"calls": 0, "tokens": 0, "cost": 0}
            by_day[day]["by_task_type"][tt]["calls"] += 1
            by_day[day]["by_task_type"][tt]["tokens"] += e.get("total_tokens", 0)
            by_day[day]["by_task_type"][tt]["cost"] += e.get("cost_cny", 0)
        # P3-4: 按模型分组统计
        by_model = {}
        for e in self.usage_log:
            key = f"{e.get('provider', '')}/{e.get('model', '')}".strip("/") or "unknown"
            if key not in by_model:
                by_model[key] = {
                    "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                    "total_tokens": 0, "cost_cny": 0.0,
                }
            by_model[key]["calls"] += 1
            by_model[key]["prompt_tokens"] += e.get("prompt_tokens", 0)
            by_model[key]["completion_tokens"] += e.get("completion_tokens", 0)
            by_model[key]["total_tokens"] += e.get("total_tokens", 0)
            by_model[key]["cost_cny"] += e.get("cost_cny", 0)
        for key in by_model:
            by_model[key]["cost_cny"] = round(by_model[key]["cost_cny"], 4)
        # P3-4: 时间窗聚合（24h / 7d / 30d）
        now = time.time()
        windows = {}
        for label, hours in (("24h", 24), ("7d", 168), ("30d", 720)):
            cutoff = now - hours * 3600
            w = {"calls": 0, "tokens": 0, "cost_cny": 0.0}
            for e in self.usage_log:
                try:
                    ts = time.mktime(time.strptime(e.get("timestamp", ""), "%Y-%m-%d %H:%M:%S"))
                except (ValueError, OverflowError):
                    continue
                if ts >= cutoff:
                    w["calls"] += 1
                    w["tokens"] += e.get("total_tokens", 0)
                    w["cost_cny"] += e.get("cost_cny", 0)
            w["cost_cny"] = round(w["cost_cny"], 4)
            windows[label] = w
        return {
            "total_calls": len(self.usage_log),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "total_cost_cny": round(total_cost, 2),
            "by_day": by_day,
            "by_model": by_model,
            "windows": windows,
            "recent": self.usage_log[-20:],
        }

    def get_usage_summary(self, task_type: str = None) -> dict:
        """按 task_type 分组的 Token / 费用统计。

        Args:
            task_type: 过滤特定任务类型，None 返回全部分组

        Returns:
            包含 by_task_type 和 total 的字典
            by_task_type: {类型: {"calls": N, "prompt_tokens": N, "completion_tokens": N, "total_tokens": N, "cost_cny": N}}
        """
        by_type = {}
        for e in self.usage_log:
            tt = e.get("task_type", "general")
            if tt not in by_type:
                by_type[tt] = {
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost_cny": 0.0,
                }
            by_type[tt]["calls"] += 1
            by_type[tt]["prompt_tokens"] += e.get("prompt_tokens", 0)
            by_type[tt]["completion_tokens"] += e.get("completion_tokens", 0)
            by_type[tt]["total_tokens"] += e.get("total_tokens", 0)
            by_type[tt]["cost_cny"] += e.get("cost_cny", 0.0)

        # 四舍五入 cost
        for tt in by_type:
            by_type[tt]["cost_cny"] = round(by_type[tt]["cost_cny"], 4)

        # 计算总计
        total = {
            "calls": sum(v["calls"] for v in by_type.values()),
            "prompt_tokens": sum(v["prompt_tokens"] for v in by_type.values()),
            "completion_tokens": sum(v["completion_tokens"] for v in by_type.values()),
            "total_tokens": sum(v["total_tokens"] for v in by_type.values()),
            "cost_cny": round(sum(v["cost_cny"] for v in by_type.values()), 4),
        }

        if task_type is not None:
            return {
                "by_task_type": {task_type: by_type.get(task_type, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_cny": 0.0})},
                "total": by_type.get(task_type, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_cny": 0.0}),
            }

        return {"by_task_type": by_type, "total": total}

    # 各 provider 对应的环境变量名
    _ENV_KEY_MAP = {
        "deepseek": "DEEPSEEK_API_KEY",
        "openai":   "OPENAI_API_KEY",
        "doubao":   "DOUBAO_API_KEY",
        "kimi":     "KIMI_API_KEY",
    }

    def _get_api_key(self, cfg: dict, provider: str = None) -> str:
        """优先从环境变量读取 API Key，其次从配置文件"""
        if provider and provider in self._ENV_KEY_MAP:
            env_key = os.environ.get(self._ENV_KEY_MAP[provider], "")
            if env_key:
                return env_key
        # fallback: 兼容旧的 DEEPSEEK_API_KEY
        env_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if env_key:
            return env_key
        file_key = cfg.get("api_key", "")
        if file_key and (file_key.startswith("sk-") or file_key.startswith("ms-") or len(file_key) >= 20):
            return file_key
        return ""

    def _ensure_defaults(self):
        if "provider" not in self.config:
            self.config["provider"] = "deepseek"
        if "deepseek" not in self.config:
            self.config["deepseek"] = {
                "api_key": "", "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash", "thinking": "disabled",
                "temperature": 0.7, "max_tokens": 8192
            }
        if "ollama" not in self.config:
            self.config["ollama"] = {
                "base_url": "http://127.0.0.1:11434", "model": "qwen3:14b",
                "temperature": 0.7, "max_tokens": 4096
            }
        if "openai" not in self.config:
            self.config["openai"] = {
                "api_key": "", "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini", "temperature": 0.7, "max_tokens": 4096
            }
        if "doubao" not in self.config:
            self.config["doubao"] = {
                "api_key": "",
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "model": "doubao-pro-32k",
                "temperature": 0.7, "max_tokens": 4096,
                "_comment": "API Key 获取: 火山引擎控制台 → Ark 大模型 → API Key 管理 → 创建密钥"
            }
        if "kimi" not in self.config:
            self.config["kimi"] = {
                "api_key": "",
                "base_url": "https://api.moonshot.cn/v1",
                "model": "moonshot-v1-8k",
                "temperature": 0.7, "max_tokens": 4096,
                "_comment": "API Key 获取: https://platform.moonshot.cn → 开发者中心 → API Key 管理",
                "_available_models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]
            }
        if "task_provider" not in self.config:
            # 多模型协作：按任务类型路由 provider；未配置/无 key 时回退全局 provider
            self.config["task_provider"] = {
                "writing": "doubao",
                "architecture": "deepseek",
                "check": "deepseek",
                "summary": "deepseek",
                "chat": "deepseek",
            }
        self._save_config()

    # M1: 多模型路由 — 按任务类型自动选模型
    TASK_MODEL_MAP = {
        "architecture": {
            "deepseek": "deepseek-v4", "openai": "gpt-4o",
            "doubao": "doubao-pro-32k", "kimi": "moonshot-v1-32k",
            "desc": "架构/大纲/复杂设计"
        },
        "writing": {
            "deepseek": "deepseek-v4-flash", "openai": "gpt-4o-mini",
            "doubao": "doubao-pro-32k", "kimi": "moonshot-v1-8k",
            "desc": "正文写作"
        },
        "check": {
            "deepseek": "deepseek-v4-flash", "openai": "gpt-4o-mini",
            "doubao": "doubao-pro-32k", "kimi": "moonshot-v1-8k",
            "desc": "检查/审核"
        },
        "summary": {
            "deepseek": "deepseek-v4-flash", "openai": "gpt-4o-mini",
            "doubao": "doubao-pro-32k", "kimi": "moonshot-v1-8k",
            "desc": "摘要/提取"
        },
        "chat": {
            "deepseek": "deepseek-v4-flash", "openai": "gpt-4o-mini",
            "doubao": "doubao-pro-32k", "kimi": "moonshot-v1-8k",
            "desc": "对话/问答"
        },
    }

    def get_model_for_task(self, task_type: str = "chat", provider: str = None) -> str:
        """按任务类型返回推荐模型名（可指定 provider，缺省用全局）"""
        provider = provider or self.get_provider()
        task_map = self.TASK_MODEL_MAP.get(task_type, self.TASK_MODEL_MAP["chat"])
        return task_map.get(provider, task_map.get("deepseek", "deepseek-v4-flash"))

    def _get_provider_for_task(self, task_type: str) -> str:
        """多模型协作：按 task_provider 表路由 provider。

        - 表中未配置该任务类型 → 回退全局 provider
        - 路由到的 provider 无 API Key（非 ollama）→ 静默回退全局 provider
        """
        global_provider = self.get_provider()
        tp = self.config.get("task_provider", {}) or {}
        prov = tp.get(task_type) or global_provider
        if prov != "ollama":
            cfg = self.config.get(prov, {}) or {}
            if not self._get_api_key(cfg, provider=prov):
                return global_provider
        return prov

    def generate_for_task(self, prompt: str, task_type: str = "chat", **kwargs) -> str:
        """按任务类型调用AI（自动选 provider + 模型）"""
        import copy
        provider = self._get_provider_for_task(task_type)
        model = self.get_model_for_task(task_type, provider=provider)
        old_model = self.config.get(provider, {}).get("model", "")
        self.config[provider] = copy.deepcopy(self.config.get(provider, {}))
        self.config[provider]["model"] = model
        try:
            result = self.generate(prompt, task=task_type, provider_override=provider, **kwargs)
        finally:
            self.config[provider] = copy.deepcopy(self.config.get(provider, {}))
            self.config[provider]["model"] = old_model
        return result

    def set_provider(self, provider: str):
        self.config["provider"] = provider
        self._save_config()

    def get_provider(self) -> str:
        return self.config.get("provider", "deepseek")

    def generate(self, prompt: str, on_chunk: Callable = None, temperature: float = None,
                 max_tokens: int = None, raise_on_error: bool = False, task: str = "",
                 task_type: str = "general", project: str = "", workflow: str = "",
                 provider_override: str = None) -> str:
        # P3-4: project/workflow 标签透传到用量日志
        self._usage_tags = {"project": project or "", "workflow": workflow or ""}
        provider = provider_override or self.config["provider"]
        cfg = dict(self.config.get(provider, {}))
        if temperature is not None:
            cfg["temperature"] = temperature

        model = cfg.get("model", "unknown")

        # ── 弹性思考强度 + 输出预算（第5批：模型元数据注册表联动） ──
        from backend.services.model_registry import (
            resolve_thinking,
            resolve_output_budget,
            estimate_prompt_tokens,
            get_context_window,
        )
        thinking_cfg = cfg.get("thinking", "disabled")
        # 兼容 old-style: "disabled"/"enabled" → off/on；显式配置的 off/disabled 必须优先，
        # 否则会被弹性思考策略（task_type 默认档）覆盖成 enabled，导致模型输出思考文本。
        user_thinking = None
        if thinking_cfg in ("enabled", "high", "medium", "low", "max"):
            user_thinking = {"enabled": "high"}.get(thinking_cfg, thinking_cfg)
        elif thinking_cfg in ("disabled", "off"):
            user_thinking = "off"
        final_thinking = resolve_thinking(provider, model, task_type, user_thinking)
        # 仅 deepseek 系列支持 thinking 开关；其它 provider 不注入
        if provider == "deepseek":
            cfg["thinking"] = "enabled" if final_thinking not in ("off", "disabled") else "disabled"
            cfg["_thinking_level"] = final_thinking

        mt = resolve_output_budget(provider, model, task_type, max_tokens or cfg.get("max_tokens"))
        cfg["max_tokens"] = mt

        # 窗口预检：prompt 过长时警告（不阻断，避免破坏现有流程）
        try:
            window = get_context_window(provider, model)
            est = estimate_prompt_tokens(prompt)
            if est + mt > window:
                logger.warning(
                    f"[AI] prompt 接近超窗: est={est}, output={mt}, window={window}, "
                    f"provider={provider}, model={model}"
                )
        except Exception:
            pass

        temp = cfg.get("temperature", 0.7)

        logger.info(f"[AI] 开始调用: provider={provider}, model={model}, temp={temp}, max_tokens={mt}, prompt_len={len(prompt)}, task={task}, thinking={final_thinking}")

        # ── 上下文透视：记录本次注入的 prompt 结构快照（第5批） ──
        try:
            from backend.services.context_inspector import capture as _ctx_capture
            _ctx_capture(
                prompt,
                task=task,
                task_type=task_type,
                provider=provider,
                model=model,
            )
        except Exception:
            pass

        # ── 调用链追踪：将本次 AI 调用挂到当前 trace（第5批） ──
        span_ctx = None
        try:
            from backend.agents.trace import get_current_trace
            trace = get_current_trace()
            if trace is not None:
                span_ctx = trace.new_span(f"ai:{task or task_type}")
                span_ctx.log_event("start", {"provider": provider, "model": model, "prompt_len": len(prompt)})
        except Exception:
            span_ctx = None

        # 指数退避重试（最多3次，总等待~14秒）
        last_error = None
        try:
            for attempt in range(3):
                if provider == "ollama":
                    result = self._ollama_generate(prompt, cfg, on_chunk, raise_on_error=False, task=task, task_type=task_type)
                elif provider in ("deepseek", "openai", "doubao", "kimi"):
                    result = self._openai_compatible(prompt, cfg, on_chunk, raise_on_error=False, task=task, task_type=task_type)
                else:
                    msg = f"不支持的 provider: {provider}"
                    logger.error(f"[AI] 调用失败: {msg}")
                    if raise_on_error:
                        raise AIClientException(msg, "config_error")
                    return f"[错误] {msg}"

                if isinstance(result, str) and result.startswith(("[错误]", "[生成失败:")):
                    last_error = result
                    if attempt < 2:
                        wait = 2 ** attempt  # 1s, 2s, 4s
                        logger.warning(f"[AI] 调用失败，{wait}秒后重试 ({attempt+1}/3): {result[:100]}")
                        time.sleep(wait)
                        continue
                else:
                    logger.info(f"[AI] 调用成功: result_len={len(result)}")
                    if span_ctx is not None:
                        span_ctx.log_event("end", {"status": "ok", "result_len": len(result)})
                    return result
        finally:
            if span_ctx is not None and last_error is not None:
                span_ctx.log_event("end", {"status": "error", "error": last_error[:200]})

        logger.error(f"[AI] 调用失败 ({attempt+1}次重试后): {last_error}")
        if raise_on_error and last_error:
            raise AIClientException(last_error, "api_error")
        return last_error or "[生成失败: 未知错误]"

    def generate_safe(self, prompt: str, **kwargs) -> Tuple[bool, str]:
        """安全调用：返回 (ok, result_or_error)，永不抛出异常"""
        kwargs["raise_on_error"] = False
        result = self.generate(prompt, **kwargs)
        if isinstance(result, str) and result.startswith(("[错误]", "[生成失败:")):
            return False, result
        return True, result

    def _ollama_generate(self, prompt: str, cfg: dict, on_chunk: Callable = None,
                         raise_on_error: bool = False, task: str = "",
                         task_type: str = "general") -> str:
        base = cfg.get("base_url", "http://127.0.0.1:11434")
        model = cfg.get("model", "qwen3:14b")
        body = {
            "model": model, "prompt": prompt,
            "stream": on_chunk is not None,
            "options": {
                "temperature": cfg.get("temperature", 0.7),
                "num_predict": cfg.get("max_tokens", 4096)
            }
        }
        try:
            if on_chunk:
                result = []
                parse_errors = 0
                with self._client.stream("POST", f"{base}/api/generate", json=body) as resp:
                    for line_bytes in resp.iter_lines():
                        line = line_bytes.strip()
                        if line:
                            try:
                                chunk = json.loads(line)
                                token = chunk.get("response", "")
                                if token:
                                    on_chunk(token)
                                    result.append(token)
                            except json.JSONDecodeError:
                                parse_errors += 1
                if parse_errors > 0:
                    logger.warning(f"Ollama 流式解析错误 {parse_errors} 行")
                return "".join(result)
            else:
                resp = self._client.post(f"{base}/api/generate", json=body)
                return resp.json().get("response", "")
        except httpx.RequestError as e:
            msg = f"Ollama 连接失败: {e}"
            logger.error(msg)
            if raise_on_error:
                raise AIClientException(msg, "network_error") from e
            return f"[生成失败: {e}]"
        except Exception as e:
            msg = f"Ollama 生成失败: {e}"
            logger.error(msg)
            if raise_on_error:
                raise AIClientException(msg, "api_error") from e
            return f"[生成失败: {e}]"

    def _openai_compatible(self, prompt: str, cfg: dict, on_chunk: Callable = None,
                           raise_on_error: bool = False, task: str = "",
                           task_type: str = "general") -> str:
        base = cfg.get("base_url", "https://api.deepseek.com")
        provider = self.get_provider()
        api_key = self._get_api_key(cfg, provider=provider)
        model = cfg.get("model", "deepseek-v4-flash")

        if not api_key:
            # ── Demo Mode: 无 API Key 时返回高质量示例结果，保证前端按钮可用 ──
            logger.warning("[AI] 未配置 API Key，进入 Demo 模式返回示例内容")
            return self._demo_response(prompt, cfg, on_chunk)

        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": cfg.get("temperature", 0.7),
            "max_tokens": cfg.get("max_tokens", 4096),
            "stream": on_chunk is not None
        }
        # 流式模式下请求 usage 信息（OpenAI 兼容 API 支持）
        if on_chunk is not None:
            body["stream_options"] = {"include_usage": True}
        thinking = cfg.get("thinking", "disabled")
        if provider == "deepseek":
            body["thinking"] = {"type": "enabled" if thinking == "enabled" else "disabled"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        try:
            if on_chunk:
                result = []
                parse_errors = 0
                stream_usage = None
                with self._client.stream("POST", f"{base}/chat/completions",
                                         json=body, headers=headers) as resp:
                    for line_bytes in resp.iter_lines():
                        line = line_bytes.strip()
                        if line.startswith("data: ") and line != "data: [DONE]":
                            try:
                                chunk = json.loads(line[6:])
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                token = delta.get("content", "")
                                if token:
                                    on_chunk(token)
                                    result.append(token)
                                # 捕获流式 usage（最后一个 chunk 可能携带）
                                if chunk.get("usage"):
                                    stream_usage = chunk["usage"]
                            except Exception:
                                parse_errors += 1
                if parse_errors > 0:
                    logger.warning(f"OpenAI兼容流式解析错误 {parse_errors} 行")
                # 记录流式用量
                if stream_usage:
                    self._record_usage(provider, model, stream_usage, task, task_type)
                return "".join(result)
            else:
                resp = self._client.post(f"{base}/chat/completions", json=body, headers=headers)
                data = resp.json()
                # 解析用量
                usage = data.get("usage")
                if usage:
                    self._record_usage(provider, model, usage, task, task_type)
                choice = data.get("choices", [{}])[0]
                msg = choice.get("message", {})
                content = msg.get("content", "")
                if content:
                    return content
                reasoning = msg.get("reasoning_content", "")
                if reasoning:
                    return reasoning
                finish_reason = choice.get("finish_reason", "")
                if finish_reason == "length":
                    logger.warning("AI输出被截断(finish_reason=length), content空")
                logger.warning("AI返回content和reasoning_content均为空, raw_keys=%s, finish=%s, msg=%s",
                               list(msg.keys()), finish_reason, json.dumps(msg, ensure_ascii=False)[:500])
                return ""
        except httpx.HTTPStatusError as e:
            try:
                err_detail = ""
                try:
                    err_json = e.response.json()
                    err_detail = err_json.get("error", {}).get("message", str(err_json))
                except Exception:
                    err_detail = e.response.text[:200]
                msg = f"API 错误 {e.response.status_code}: {err_detail}"
            except Exception:
                msg = f"API 错误 {e.response.status_code}"
            logger.error(msg)
            if raise_on_error:
                raise AIClientException(msg, "api_error") from e
            return f"[生成失败: {msg}]"
        except httpx.RequestError as e:
            msg = f"网络连接失败: {e}"
            logger.error(msg)
            if raise_on_error:
                raise AIClientException(msg, "network_error") from e
            return f"[生成失败: {e}]"
        except Exception as e:
            msg = f"生成失败: {e}"
            logger.error(msg)
            if raise_on_error:
                raise AIClientException(msg, "unknown") from e
            return f"[生成失败: {e}]"

    def test_connection(self) -> bool:
        try:
            # 有API Key时才真的请求；Demo模式下直接视为连接可用
            provider = self.get_provider()
            cfg = dict(self.config.get(provider, {}))
            if self._get_api_key(cfg, provider=provider):
                result = self.generate("回复'OK'", raise_on_error=True)
                return len(result) > 0
            return True
        except AIClientException:
            return False
        except Exception:
            return False

    # ── Demo Mode ── 委托到 backend.services.demo_responses ──
    def _demo_response(self, prompt: str, cfg: dict, on_chunk):
        from backend.services.demo_responses import _demo_response
        return _demo_response(prompt, cfg, on_chunk)


    def close(self):
        """关闭 httpx 客户端连接"""
        self._client.close()

    def __del__(self):
        try:
            self._client.close()
        except Exception:
            pass
