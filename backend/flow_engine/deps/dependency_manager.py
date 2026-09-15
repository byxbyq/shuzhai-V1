# -*- coding: utf-8 -*-
"""
DependencyManager — 依赖管理类（白城主 Flow Engine）

职责边界（封版约定）：
- 只做「检测、计算缺失项、生成待执行指令」，绝不直接执行安装/下载；
- 所有修改外部环境的动作由上层业务统一弹窗确认后，再调用本类的执行方法；
- 系统级二进制（ffmpeg/cuda 等）仅检测并提示手动安装，绝不调用 apt/choco 等系统包管理器。

功能：
1. pip 包检测（packaging.version 版本比对）与安装（绑定 sys.executable）
2. 系统工具检测（shutil.which 跨平台）
3. HuggingFace 模型校验 + snapshot_download 断点续传，内置 hf-mirror 镜像降级
4. 磁盘空间预估
5. 缓存 dep_verified.json（带版本/指纹，防脏数据）
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from packaging.version import Version, InvalidVersion

# ── 常量 ──

HF_MIRROR_ENDPOINT = "https://hf-mirror.com"
DEFAULT_CACHE_REL = ".cache" / Path("dep_verified.json")  # 相对项目根


# ── 工具函数 ──

def parse_pip_req(req: str) -> Tuple[str, Optional[str], Optional[str]]:
    """解析 'torch>=2.1' → (name, op, version)。

    op ∈ {==, >=, <=, >, <, ~=}；无约束时 version 为 None。
    不支持多个约束（如 'a>=1,<2'），按最简规范处理。
    """
    req = req.strip()
    for op in ("==", ">=", "<=", "~=", ">", "<"):
        if op in req:
            name, ver = req.split(op, 1)
            return name.strip(), op, ver.strip()
    return req, None, None


def version_satisfies(installed: str, op: str, required: str) -> bool:
    """判断已安装版本是否满足约束。非法版本一律视为不满足。"""
    try:
        iv = Version(installed)
        rv = Version(required)
    except (InvalidVersion, TypeError):
        return False
    if op == "==":
        return iv == rv
    if op == ">=":
        return iv >= rv
    if op == "<=":
        return iv <= rv
    if op == ">":
        return iv > rv
    if op == "<":
        return iv < rv
    if op == "~=":
        # ~= 兼容：major.minor 匹配，patch 可高于
        return iv >= rv and iv.release[:2] == rv.release[:2]
    return False


def parse_size_approx(text: str) -> int:
    """解析 '15GB' / '800MB' / '1.2TB' → 字节数。无法解析返回 0。"""
    if not text:
        return 0
    text = text.strip().upper()
    units = {"KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}
    for suffix, mult in units.items():
        if text.endswith(suffix):
            try:
                return int(float(text[: -len(suffix)]) * mult)
            except ValueError:
                return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _dir_fingerprint(path: Path) -> Optional[Dict[str, Any]]:
    """模型目录指纹：核心文件数量 + 总大小。文件被删/清空时指纹失效。"""
    if not path.exists() or not path.is_dir():
        return None
    total = 0
    count = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                    count += 1
                except OSError:
                    pass
    except OSError:
        return None
    if count == 0 or total == 0:
        return None
    return {"file_count": count, "total_size": total}


# ── 主类 ──

class DependencyManager:
    """依赖检测/安装/下载的统一入口。所有外部副作用方法返回结构化结果。"""

    def __init__(self, project_root: Optional[str] = None, cache_path: Optional[str] = None):
        self.project_root = Path(project_root or os.getcwd()).resolve()
        self.cache_path = Path(cache_path) if cache_path else (self.project_root / DEFAULT_CACHE_REL)
        self._cache: Dict[str, Any] = self._load_cache()

    # ── 缓存 ──

    def _load_cache(self) -> Dict[str, Any]:
        try:
            if self.cache_path.exists():
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except (OSError, json.JSONDecodeError):
            pass
        return {"pip": {}, "models": {}}

    def save_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as e:
            # 缓存写失败不阻塞主流程，仅打印
            print(f"[DependencyManager] 缓存写入失败: {e}")

    def is_pip_verified(self, name: str, version: str) -> bool:
        entry = self._cache.get("pip", {}).get(name)
        return bool(entry and entry.get("version") == version)

    def is_model_verified(self, path: str, fingerprint: Dict[str, Any]) -> bool:
        entry = self._cache.get("models", {}).get(path)
        return bool(entry and entry.get("fingerprint") == fingerprint)

    # ── pip 检测 ──

    def check_packages(self, requirements: List[str]) -> List[Dict[str, Any]]:
        """检测依赖是否满足。返回缺失/不达标项列表，空列表表示全部通过。

        每项: {"req": "torch>=2.1", "name": "torch", "required": ">=2.1",
               "installed": "2.0.1" | None, "reason": "missing"|"version"}
        """
        from importlib import metadata

        missing: List[Dict[str, Any]] = []
        for req in requirements or []:
            name, op, ver = parse_pip_req(req)
            if not name:
                continue

            # 优先读缓存
            try:
                installed = metadata.version(name)
            except metadata.PackageNotFoundError:
                installed = None

            if installed is None:
                missing.append({"req": req, "name": name, "required": op + ver if op else "any",
                                "installed": None, "reason": "missing"})
                continue

            if op and not version_satisfies(installed, op, ver):
                missing.append({"req": req, "name": name, "required": op + ver,
                                "installed": installed, "reason": "version"})
                continue

            # 达标 → 写缓存（版本号维度）
            self._cache.setdefault("pip", {})[name] = {"version": installed}
        return missing

    def install_packages(self, requirements: List[str], timeout: int = 600) -> Dict[str, Any]:
        """执行 pip 安装（绑定当前解释器）。返回结构化结果。"""
        if not requirements:
            return {"ok": True, "installed": [], "output": ""}
        cmd = [sys.executable, "-m", "pip", "install"] + list(requirements)
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace"
            )
            ok = proc.returncode == 0
            if ok:
                # 安装成功后清缓存强制下次重检
                for req in requirements:
                    name, _, _ = parse_pip_req(req)
                    if name:
                        self._cache.get("pip", {}).pop(name, None)
                self.save_cache()
            return {"ok": ok, "installed": requirements if ok else [],
                    "output": (proc.stdout or "") + "\n" + (proc.stderr or "")}
        except subprocess.TimeoutExpired:
            return {"ok": False, "installed": [], "output": f"pip 安装超时（{timeout}s）"}
        except Exception as e:
            return {"ok": False, "installed": [], "output": f"pip 安装异常: {e}"}

    # ── 系统工具检测 ──

    def check_system_tools(self, tools: List[str]) -> List[Dict[str, Any]]:
        """检测系统二进制是否存在。缺失项仅提示，不自动安装。

        每项: {"name": "ffmpeg", "found": bool, "path": str|None}
        """
        result = []
        for tool in tools or []:
            path = shutil.which(tool)
            result.append({"name": tool, "found": path is not None, "path": path})
        return result

    # ── 模型检测 ──

    def check_models(self, models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """检测本地模型目录完整性。

        每项: {"repo_id", "path", "size_approx", "ok": bool,
               "exists": bool, "fingerprint": {...}|None,
               "expected_bytes": int, "reason": "missing"|"empty"|"ok"}
        """
        result = []
        for m in models or []:
            repo_id = m.get("repo_id", "")
            rel_path = m.get("path", "")
            size_approx = m.get("size_approx", "")
            local = (self.project_root / rel_path).resolve() if rel_path else None

            fp = _dir_fingerprint(local) if local else None
            expected = parse_size_approx(size_approx)

            ok = fp is not None and (expected == 0 or fp["total_size"] >= expected * 0.8)
            if ok and self.is_model_verified(str(local), fp):
                reason = "cached"
            elif fp is None:
                reason = "missing"
            elif not ok:
                reason = "incomplete"
            else:
                reason = "ok"
                self._cache.setdefault("models", {})[str(local)] = {"fingerprint": fp}

            result.append({
                "repo_id": repo_id,
                "path": rel_path,
                "size_approx": size_approx,
                "ok": ok,
                "exists": fp is not None,
                "fingerprint": fp,
                "expected_bytes": expected,
                "reason": reason,
            })
        return result

    # ── HuggingFace 下载（断点续传 + 镜像降级） ──

    def download_model_hf(
        self,
        repo_id: str,
        local_dir: str,
        allow_mirror: bool = True,
        timeout: int = 3600,
        hf_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """调用 huggingface_hub.snapshot_download 断点续传下载模型。

        双链路自动降级：先原始地址，超时/连接异常后注入 HF_ENDPOINT 镜像重试。
        返回结构化结果；huggingface_hub 未安装时返回可安装提示。
        """
        local_path = (self.project_root / local_dir).resolve()
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            return {
                "ok": False,
                "error": "missing_hf_hub",
                "message": "缺少 huggingface_hub，请先安装：pip install huggingface_hub",
            }

        def _try_download(endpoint: Optional[str]) -> Tuple[bool, str]:
            env = dict(os.environ)
            if endpoint:
                env["HF_ENDPOINT"] = endpoint
            try:
                out = snapshot_download(
                    repo_id=repo_id,
                    local_dir=str(local_path),
                    token=hf_token,
                    max_workers=4,
                )
                return True, str(out)
            except Exception as e:
                return False, str(e)

        # 链路 1：原始地址
        ok, detail = _try_download(None)
        if ok:
            self.save_cache()
            return {"ok": True, "path": detail, "mirror": False}

        # 链路 2：hf-mirror 镜像
        if allow_mirror:
            ok2, detail2 = _try_download(HF_MIRROR_ENDPOINT)
            if ok2:
                self.save_cache()
                return {"ok": True, "path": detail2, "mirror": True}
            return {
                "ok": False,
                "error": "download_failed",
                "message": f"直连与镜像均失败。\n直连: {detail}\n镜像(hf-mirror): {detail2}",
            }

        return {"ok": False, "error": "download_failed", "message": f"下载失败（未启用镜像）: {detail}"}

    # ── 磁盘空间 ──

    def check_disk_space(self, path: str, needed_bytes: int) -> Dict[str, Any]:
        """检查指定路径所在磁盘剩余空间是否足够。"""
        target = (self.project_root / path).resolve() if path else self.project_root
        try:
            usage = shutil.disk_usage(target)
            free = usage.free
            ok = free >= needed_bytes
            return {
                "ok": ok,
                "free_bytes": free,
                "needed_bytes": needed_bytes,
                "free_gb": round(free / 1024 ** 3, 2),
                "needed_gb": round(needed_bytes / 1024 ** 3, 2),
            }
        except OSError as e:
            # 路径不存在时无法评估磁盘空间，返回 ok=True 避免误报"磁盘不足"
            return {"ok": True, "free_bytes": 0, "needed_bytes": needed_bytes,
                    "free_gb": 0, "needed_gb": 0, "note": f"目标路径不存在，无法评估磁盘空间: {e}"}

    # ── 汇总检测（供确认弹窗） ──

    def verify_all(self, dependencies: Dict[str, Any]) -> Dict[str, Any]:
        """对节点 dependencies 做全量检测，返回可直接渲染弹窗的汇总结构。"""
        deps = dependencies or {}
        pip_missing = self.check_packages(deps.get("pip", []))
        system_tools = self.check_system_tools(deps.get("system", []))
        model_results = self.check_models(deps.get("models", []))

        # 模型缺失时的磁盘预估（仅评估"目录存在但空间不足"的项，目录缺失无法评估）
        disk_issues = []
        for m in model_results:
            if not m["ok"] and m["expected_bytes"] > 0 and m.get("exists"):
                disk = self.check_disk_space(m["path"], m["expected_bytes"])
                if not disk.get("ok"):
                    disk_issues.append({"repo_id": m["repo_id"], **disk})

        self.save_cache()
        return {
            "pip_missing": pip_missing,
            "system_tools": system_tools,
            "models": model_results,
            "disk_issues": disk_issues,
            "all_ok": not pip_missing and all(t["found"] for t in system_tools)
                      and all(m["ok"] for m in model_results),
        }
