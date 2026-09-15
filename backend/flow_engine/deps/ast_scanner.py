# -*- coding: utf-8 -*-
"""
AST 静态扫描校验器（只读，零副作用）。

对 AI 生成的 run_code 做静态风险扫描，输出结构化告警，
供前端复合确认弹窗渲染"代码风险"一栏，并在执行前兜底拦截。

告警分级：
- high   : 高危 —— 删除文件、格式化、执行 shell、eval/exec、网络下载执行
- medium : 中危 —— 网络请求、写文件、subprocess 调用、base64 混淆
- low    : 提示 —— 外部 import、交互输入等

本模块只解析源码字符串，绝不执行、不写盘、不发网络请求。
"""

from __future__ import annotations

import ast
from typing import Dict, Any, List


# ── 扫描规则 ──

# 高危调用：函数名（支持 a.b 链式）→ 告警文案
_HIGH_CALLS: List[tuple] = [
    (("os", "system"), "调用 os.system 执行系统命令，可能造成不可控副作用"),
    (("os", "popen"), "调用 os.popen 执行系统命令，可能造成不可控副作用"),
    (("os", "remove"), "调用 os.remove 删除文件"),
    (("os", "unlink"), "调用 os.unlink 删除文件"),
    (("os", "rmdir"), "调用 os.rmdir 删除目录"),
    (("os", "removedirs"), "调用 os.removedirs 递归删除目录"),
    (("os", "makedirs"), "调用 os.makedirs 创建目录（请确认目标路径）"),
    (("shutil", "rmtree"), "调用 shutil.rmtree 递归删除目录树"),
    (("shutil", "move"), "调用 shutil.move 移动/覆盖文件"),
    (("shutil", "copy"), "调用 shutil.copy 复制文件"),
    (("shutil", "copy2"), "调用 shutil.copy2 复制文件（含元数据）"),
    (("shutil", "copytree"), "调用 shutil.copytree 复制目录树"),
    (("eval",), "调用 eval 动态执行表达式"),
    (("exec",), "调用 exec 动态执行代码"),
    (("compile",), "调用 compile 编译动态代码"),
    (("__import__",), "动态导入模块（可被用于绕过静态检查）"),
    (("pickle", "load"), "pickle.load 反序列化不可信数据存在 RCE 风险"),
    (("pickle", "loads"), "pickle.loads 反序列化不可信数据存在 RCE 风险"),
    (("cPickle", "load"), "cPickle.load 反序列化不可信数据存在 RCE 风险"),
    (("cPickle", "loads"), "cPickle.loads 反序列化不可信数据存在 RCE 风险"),
    (("marshal", "loads"), "marshal.loads 反序列化不可信数据存在 RCE 风险"),
    (("os", "startfile"), "调用 os.startfile 打开外部程序/文件"),
]

# 中危调用
_MEDIUM_CALLS: List[tuple] = [
    (("open",), None),  # open 单独处理（区分读写模式）
    (("subprocess", "call"), "subprocess.call 执行外部进程"),
    (("subprocess", "run"), "subprocess.run 执行外部进程"),
    (("subprocess", "Popen"), "subprocess.Popen 启动外部进程"),
    (("subprocess", "check_call"), "subprocess.check_call 执行外部进程"),
    (("subprocess", "check_output"), "subprocess.check_output 执行外部进程"),
    (("requests", "get"), "发起 HTTP 请求（联网行为）"),
    (("requests", "post"), "发起 HTTP 请求（联网行为）"),
    (("requests", "put"), "发起 HTTP 请求（联网行为）"),
    (("requests", "delete"), "发起 HTTP 请求（联网行为）"),
    (("urllib", "request"), "发起网络请求（联网行为）"),
    (("httpx", "get"), "发起 HTTP 请求（联网行为）"),
    (("httpx", "post"), "发起 HTTP 请求（联网行为）"),
    (("aiohttp",), "使用 aiohttp 发起网络请求（联网行为）"),
    (("socket",), "使用 socket 建立网络连接"),
    (("base64", "b64decode"), "base64 解码（常见于混淆载荷，请核对内容）"),
    (("base64", "b64encode"), "base64 编码（常见于混淆载荷，请核对内容）"),
    (("input",), "input() 交互输入（无控制台场景会卡死）"),
]

# 高危导入模块（import 本身提示，配合调用命中高危规则）
_HIGH_IMPORTS = {
    "os": "导入 os 模块（可执行系统命令/文件删除）",
    "shutil": "导入 shutil 模块（可递归删除/移动文件）",
    "subprocess": "导入 subprocess 模块（可执行外部进程）",
    "pickle": "导入 pickle 模块（反序列化存在 RCE 风险）",
    "cPickle": "导入 cPickle 模块（反序列化存在 RCE 风险）",
    "marshal": "导入 marshal 模块（反序列化存在 RCE 风险）",
}

# 中危导入模块
_MEDIUM_IMPORTS = {
    "requests": "导入 requests（联网模块）",
    "httpx": "导入 httpx（联网模块）",
    "urllib": "导入 urllib（联网模块）",
    "aiohttp": "导入 aiohttp（联网模块）",
    "socket": "导入 socket（网络模块）",
    "base64": "导入 base64（编码混淆常用）",
}


def _attr_chain(node: ast.AST) -> tuple:
    """将 Attribute/Name/Call 解析为点分链（如 os.system）。"""
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    elif isinstance(cur, ast.Call):
        parts.append("__call__")
    return tuple(reversed(parts))


def _has_shell_kwarg(call_node: ast.Call) -> bool:
    for kw in call_node.keywords:
        if kw.arg == "shell" and isinstance(kw.value, ast.Constant):
            return bool(kw.value.value)
    return False


def _open_mode(call_node: ast.Call) -> str:
    """提取 open() 的 mode 参数（粗判读写）。"""
    # mode 关键字
    for kw in call_node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    # 第二个位置参数
    if len(call_node.args) >= 2 and isinstance(call_node.args[1], ast.Constant):
        return str(call_node.args[1].value)
    return "r"


def scan_code_risks(code: str) -> List[Dict[str, Any]]:
    """
    扫描一段 Python 源码字符串，返回风险告警列表。

    Args:
        code: run_code 源码（可含空行/注释）。

    Returns:
        [{"line": int, "severity": "high|medium|low", "code": str, "msg": str}, ...]
        无风险时返回 []；语法错误返回一条 high 级告警（line=0）。
    """
    if not code or not code.strip():
        return []

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [{
            "line": getattr(e, "lineno", 0) or 0,
            "severity": "high",
            "code": "syntax",
            "msg": f"Python 语法错误: {e.msg}（第 {getattr(e, 'lineno', 0)} 行）",
        }]

    risks: List[Dict[str, Any]] = []
    imported_high = set()
    imported_medium = set()

    class _Scanner(ast.NodeVisitor):
        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _HIGH_IMPORTS:
                    imported_high.add(top)
                elif top in _MEDIUM_IMPORTS:
                    imported_medium.add(top)
            self.generic_visit(node)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if node.module:
                top = node.module.split(".")[0]
                if top in _HIGH_IMPORTS:
                    imported_high.add(top)
                elif top in _MEDIUM_IMPORTS:
                    imported_medium.add(top)
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            chain = _attr_chain(node.func)
            # 高危调用
            for pat, msg in _HIGH_CALLS:
                if chain == pat:
                    risks.append({
                        "line": node.lineno,
                        "severity": "high",
                        "code": ".".join(chain),
                        "msg": msg,
                    })
                    break
            # 中危调用
            for pat, msg in _MEDIUM_CALLS:
                if chain == pat and pat[0] != "open":
                    risks.append({
                        "line": node.lineno,
                        "severity": "medium",
                        "code": ".".join(chain),
                        "msg": msg or f"调用 {'.'.join(chain)}",
                    })
                    break
            # open 写模式
            if chain == ("open",) or chain == ("builtins", "open"):
                mode = _open_mode(node)
                if any(w in mode for w in ("w", "a", "x", "+")):
                    risks.append({
                        "line": node.lineno,
                        "severity": "medium",
                        "code": "open",
                        "msg": f"open() 以写模式（{mode!r}）打开文件，会修改磁盘文件",
                    })
            # subprocess + shell=True → 升级为 high
            if chain[:1] == ("subprocess",) and _has_shell_kwarg(node):
                risks.append({
                    "line": node.lineno,
                    "severity": "high",
                    "code": "subprocess(shell=True)",
                    "msg": "subprocess 调用带 shell=True，存在命令注入风险",
                })
            self.generic_visit(node)

    _Scanner().visit(tree)

    # import 提示（放在调用告警之后，低优先级）
    for mod in sorted(imported_high):
        risks.append({
            "line": 0,
            "severity": "low",
            "code": "import " + mod,
            "msg": _HIGH_IMPORTS[mod],
        })
    for mod in sorted(imported_medium):
        risks.append({
            "line": 0,
            "severity": "low",
            "code": "import " + mod,
            "msg": _MEDIUM_IMPORTS[mod],
        })

    # 稳定排序：high → medium → low，再按行号
    sev_order = {"high": 0, "medium": 1, "low": 2}
    risks.sort(key=lambda r: (sev_order.get(r["severity"], 9), r["line"]))
    return risks


def scan_has_high_risk(code: str) -> bool:
    """快速判断：是否含 high 级风险（供执行前兜底拦截）。"""
    return any(r["severity"] == "high" for r in scan_code_risks(code))
