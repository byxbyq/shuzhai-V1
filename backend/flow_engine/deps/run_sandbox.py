# -*- coding: utf-8 -*-
"""
白城主 Flow Engine — run_code 沙箱执行器（一期：AST 静态扫描 + 子进程受限）

run_code 子进程协议（与 deps/schema.py NODE_SCHEMA_EXAMPLE 一致）：
- 入参: sys.argv[1] 指向临时 JSON 文件，内容为 {"inputs": {...}, "params": {...}}
- 出参: stdout 打印 JSON {"ok": bool, "outputs": {...}, "error": str?}
- 兼容写法: 代码内直接定义 OUTPUTS = {...}（wrapper 自动收集）

执行安全（一期）：
1. 执行前 AST 静态扫描，高危风险直接阻断，不进入子进程；
2. 子进程运行于独立临时目录，cwd 与输出文件隔离；
3. 硬超时（默认 120s），超时强杀；
4. 临时目录执行后自动清理。

二期（规划）：OS 级真沙箱（容器/受限账户）。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, Optional

from backend.flow_engine.deps.ast_scanner import scan_code_risks, scan_has_high_risk

logger = logging.getLogger(__name__)

_WRAPPER_CODE = r"""
import json, os, sys, traceback

payload_path = sys.argv[1]
sandbox_dir = os.path.dirname(os.path.abspath(payload_path))
code_path = os.path.join(sandbox_dir, "user_code.py")

try:
    with open(payload_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    with open(code_path, "r", encoding="utf-8") as f:
        code = f.read()
    sys.argv = [code_path, payload_path]
    g = {
        "__name__": "__main__",
        "__file__": code_path,
        "sys": sys,
        "os": os,
        "json": json,
        "INPUTS": payload.get("inputs", {}),
        "PARAMS": payload.get("params", {}),
        "OUTPUTS": None,
    }
    exec(compile(code, code_path, "exec"), g)
    outputs = g.get("OUTPUTS")
    if outputs is None:
        outputs = {}
    print("__WC_SANDBOX_OK__" + json.dumps({"ok": True, "outputs": outputs}, ensure_ascii=False))
except SystemExit:
    raise
except Exception:
    print("__WC_SANDBOX_ERR__" + json.dumps({"ok": False, "error": traceback.format_exc()}, ensure_ascii=False))
"""


class SandboxError(Exception):
    """沙箱执行异常（非用户代码错误）"""
    pass


class SandboxExecutor:
    """
    run_code 沙箱执行器。

    用法::

        result = SandboxExecutor().run_code(
            code="OUTPUTS = {'text': INPUTS['text'].upper()}",
            inputs={"text": "hello"},
        )
        # result = {"ok": True, "status": "completed", "outputs": {"text": "HELLO"}}
    """

    def __init__(self, timeout: float = 120.0, keep_temp: bool = False):
        self.timeout = timeout
        self.keep_temp = keep_temp  # 调试用：保留临时目录

    # ── 核心入口 ──

    def run_code(
        self,
        code: str,
        inputs: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """执行一段 run_code，返回统一结果结构。

        Returns:
            {"ok": bool, "status": "completed"|"blocked"|"error"|"timeout",
             "outputs": dict, "error": str?, "risks": [...]?, "duration_ms": float}
        """
        code = code or ""
        t0 = time.time()

        risks = scan_code_risks(code)
        if scan_has_high_risk(code):
            return {
                "ok": False,
                "status": "blocked",
                "outputs": {},
                "error": "run_code 存在高危风险，已阻断执行（请修改代码后重试）",
                "risks": risks,
                "duration_ms": round((time.time() - t0) * 1000, 1),
            }

        sandbox_dir = tempfile.mkdtemp(prefix="wc_sandbox_")
        try:
            payload_path = os.path.join(sandbox_dir, "input.json")
            code_path = os.path.join(sandbox_dir, "user_code.py")
            with open(payload_path, "w", encoding="utf-8") as f:
                json.dump({"inputs": inputs or {}, "params": params or {}}, f, ensure_ascii=False)
            with open(code_path, "w", encoding="utf-8") as f:
                f.write(code)

            cmd = [sys.executable, "-c", _WRAPPER_CODE, payload_path]
            kwargs: Dict[str, Any] = {
                "cwd": sandbox_dir,
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "timeout": self.timeout,
            }
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

            try:
                proc = subprocess.run(cmd, **kwargs)
            except subprocess.TimeoutExpired:
                logger.warning("[sandbox] run_code 超时（%.0fs）", self.timeout)
                return {
                    "ok": False,
                    "status": "timeout",
                    "outputs": {},
                    "error": f"run_code 执行超时（{self.timeout:.0f}s）",
                    "risks": risks,
                    "duration_ms": round((time.time() - t0) * 1000, 1),
                }

            stdout = proc.stdout or ""
            stderr = proc.stderr or ""

            result = self._parse_stdout(stdout)
            if result is not None:
                result["status"] = "completed" if result.get("ok") else "error"
                result["risks"] = risks
                result["duration_ms"] = round((time.time() - t0) * 1000, 1)
                if not result.get("ok") and not result.get("error"):
                    result["error"] = stderr[:2000] or "未知错误"
                return result

            if proc.returncode == 0:
                return {
                    "ok": True,
                    "status": "completed",
                    "outputs": {"stdout": stdout[:200000]},
                    "risks": risks,
                    "duration_ms": round((time.time() - t0) * 1000, 1),
                }

            return {
                "ok": False,
                "status": "error",
                "outputs": {},
                "error": (stderr or stdout)[:2000],
                "risks": risks,
                "duration_ms": round((time.time() - t0) * 1000, 1),
            }

        finally:
            if not self.keep_temp:
                shutil.rmtree(sandbox_dir, ignore_errors=True)

    # ── 解析辅助 ──

    @staticmethod
    def _parse_stdout(stdout: str) -> Optional[Dict[str, Any]]:
        """解析 wrapper 标记 JSON。"""
        for marker in ("__WC_SANDBOX_OK__", "__WC_SANDBOX_ERR__"):
            if marker in stdout:
                idx = stdout.index(marker) + len(marker)
                try:
                    data = json.loads(stdout[idx:].strip())
                    return data
                except json.JSONDecodeError:
                    return {"ok": False, "error": stdout[idx:][:2000]}
        return None


# ── 便捷单例 ──

_default_executor = SandboxExecutor()


def run_code_sandboxed(
    code: str,
    inputs: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """单次执行 run_code 的便捷函数（使用默认执行器）。"""
    if timeout != _default_executor.timeout:
        return SandboxExecutor(timeout=timeout).run_code(code, inputs=inputs, params=params)
    return _default_executor.run_code(code, inputs=inputs, params=params)
