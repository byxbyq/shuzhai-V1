# -*- coding: utf-8 -*-
"""
书斋 V66 — 自动代码检查与修复循环脚本

功能：
1. Python语法检查
2. 模块导入测试
3. Pytest单元测试
4. 静态代码审查（常见问题检测）
5. 低风险问题自动修复
6. 循环运行直到无问题或到达截止时间

用法：
    python auto_check_and_fix.py [--deadline HH:MM] [--max-rounds N]
"""
import sys
import os
import re
import ast
import subprocess
import json
import time
import datetime
import traceback
from pathlib import Path
from typing import List, Dict, Tuple, Optional

REPO_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = REPO_ROOT / "backend"
TESTS_DIR = REPO_ROOT / "tests"
REPORT_DIR = REPO_ROOT / "test_reports" / "auto_check"

os.chdir(str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

REPORT_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════
#  问题分类
# ═══════════════════════════════════════════

ISSUE_CATEGORIES = {
    "syntax_error": {"name": "语法错误", "severity": "high", "auto_fixable": False},
    "import_error": {"name": "导入错误", "severity": "high", "auto_fixable": False},
    "test_failure": {"name": "测试失败", "severity": "high", "auto_fixable": False},
    "unused_import": {"name": "未使用的导入", "severity": "low", "auto_fixable": True},
    "missing_encoding": {"name": "缺少编码声明", "severity": "low", "auto_fixable": True},
    "trailing_whitespace": {"name": "行尾空白", "severity": "low", "auto_fixable": True},
    "mixed_indentation": {"name": "缩进混用", "severity": "medium", "auto_fixable": True},
    "print_debug": {"name": "调试print语句", "severity": "low", "auto_fixable": False},
    "bare_except": {"name": "裸except", "severity": "medium", "auto_fixable": False},
    "todo_comment": {"name": "TODO/FIXME注释", "severity": "info", "auto_fixable": False},
}


# ═══════════════════════════════════════════
#  报告工具
# ═══════════════════════════════════════════

class CheckReport:
    """检查报告"""

    def __init__(self, round_num: int):
        self.round_num = round_num
        self.timestamp = datetime.datetime.now().isoformat()
        self.issues: List[Dict] = []
        self.fixed: List[Dict] = []
        self.errors: List[str] = []

    def add_issue(self, category: str, file_path: str, line: int, message: str,
                  severity: str = None, auto_fixable: bool = None):
        cat = ISSUE_CATEGORIES.get(category, {"name": category, "severity": "medium", "auto_fixable": False})
        self.issues.append({
            "category": category,
            "category_name": cat["name"],
            "severity": severity or cat["severity"],
            "auto_fixable": auto_fixable if auto_fixable is not None else cat["auto_fixable"],
            "file": file_path,
            "line": line,
            "message": message,
        })

    def add_fixed(self, category: str, file_path: str, line: int, message: str):
        self.fixed.append({
            "category": category,
            "file": file_path,
            "line": line,
            "message": message,
        })

    def add_error(self, error: str):
        self.errors.append(error)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def high_severity_count(self) -> int:
        return sum(1 for i in self.issues if i["severity"] == "high")

    @property
    def auto_fixable_count(self) -> int:
        return sum(1 for i in self.issues if i["auto_fixable"])

    def summary(self) -> str:
        lines = [
            f"═══ 第 {self.round_num} 轮检查报告 ═══",
            f"时间: {self.timestamp}",
            f"问题总数: {self.issue_count}",
            f"  高严重: {self.high_severity_count}",
            f"  可自动修复: {self.auto_fixable_count}",
            f"已修复: {len(self.fixed)}",
            f"执行错误: {len(self.errors)}",
        ]
        if self.issues:
            lines.append("\n问题详情:")
            by_severity = {"high": [], "medium": [], "low": [], "info": []}
            for issue in self.issues:
                by_severity[issue["severity"]].append(issue)
            for sev in ["high", "medium", "low", "info"]:
                if by_severity[sev]:
                    sev_label = {"high": "🔴 高", "medium": "🟡 中", "low": "🟢 低", "info": "🔵 信息"}[sev]
                    lines.append(f"\n  {sev_label}严重级 ({len(by_severity[sev])}个):")
                    for issue in by_severity[sev][:20]:
                        rel_path = os.path.relpath(issue["file"], str(REPO_ROOT))
                        fix_mark = " ✅可修复" if issue["auto_fixable"] else ""
                        lines.append(f"    - [{issue['category_name']}] {rel_path}:{issue['line']}{fix_mark}")
                        lines.append(f"      {issue['message'][:100]}")
                    if len(by_severity[sev]) > 20:
                        lines.append(f"    ... 还有 {len(by_severity[sev]) - 20} 个")
        if self.fixed:
            lines.append(f"\n已修复 ({len(self.fixed)}个):")
            for f in self.fixed[:10]:
                rel_path = os.path.relpath(f["file"], str(REPO_ROOT))
                lines.append(f"  ✅ {rel_path}:{f['line']} - {f['message']}")
        if self.errors:
            lines.append(f"\n执行错误 ({len(self.errors)}个):")
            for e in self.errors[:5]:
                lines.append(f"  ❌ {e[:150]}")
        return "\n".join(lines)

    def save(self, path: str = None):
        if path is None:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = str(REPORT_DIR / f"round_{self.round_num}_{ts}.json")
        data = {
            "round": self.round_num,
            "timestamp": self.timestamp,
            "issues": self.issues,
            "fixed": self.fixed,
            "errors": self.errors,
            "summary": {
                "total_issues": self.issue_count,
                "high_severity": self.high_severity_count,
                "auto_fixable": self.auto_fixable_count,
                "fixed_count": len(self.fixed),
            }
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path


# ═══════════════════════════════════════════
#  收集 Python 文件
# ═══════════════════════════════════════════

def collect_python_files() -> List[str]:
    """收集所有需要检查的 Python 文件"""
    # 排除自身，避免把检查脚本的 print 输出误判为"调试print语句"
    self_path = str(Path(__file__).resolve())
    files = []
    for py_file in REPO_ROOT.rglob("*.py"):
        if str(py_file.resolve()) == self_path:
            continue
        rel = py_file.relative_to(REPO_ROOT)
        parts = rel.parts
        skip_dirs = {"__pycache__", ".git", "venv", "env", "dist", "build", ".pytest_cache"}
        if any(p in skip_dirs for p in parts):
            continue
        if py_file.name.startswith("_") and py_file.name != "__init__.py":
            if py_file.parent == REPO_ROOT:
                continue
        files.append(str(py_file))
    return sorted(files)


# ═══════════════════════════════════════════
#  1. 语法检查
# ═══════════════════════════════════════════

def check_syntax(files: List[str], report: CheckReport):
    """检查 Python 语法错误"""
    print("  🔍 语法检查...", end=" ")
    count = 0
    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                source = f.read()
            ast.parse(source, filename=fpath)
        except SyntaxError as e:
            report.add_issue(
                "syntax_error", fpath, e.lineno or 0,
                f"语法错误: {e.msg}",
                severity="high", auto_fixable=False
            )
            count += 1
        except UnicodeDecodeError:
            try:
                with open(fpath, "r", encoding="gbk") as f:
                    source = f.read()
                ast.parse(source, filename=fpath)
            except Exception as e2:
                report.add_issue(
                    "syntax_error", fpath, 0,
                    f"编码/读取错误: {e2}",
                    severity="high", auto_fixable=False
                )
                count += 1
    print(f"发现 {count} 个问题")


# ═══════════════════════════════════════════
#  2. 模块导入测试
# ═══════════════════════════════════════════

def check_imports(report: CheckReport):
    """测试核心模块导入"""
    print("  🔍 导入测试...", end=" ")
    count = 0
    test_modules = [
        "backend.ledger",
        "backend.generator",
        "backend.project",
        "backend.auth",
        "backend.ai_client",
        "backend.services.project_service",
        "backend.services.chapter_service",
        "backend.services.memory_synthesizer",
        "backend.novel_engine.engine_core",
        "backend.agents.dispatcher",
    ]
    for mod_name in test_modules:
        try:
            __import__(mod_name)
        except Exception as e:
            report.add_issue(
                "import_error", mod_name, 0,
                f"导入失败: {e}",
                severity="high", auto_fixable=False
            )
            count += 1
    print(f"发现 {count} 个问题")


# ═══════════════════════════════════════════
#  3. Pytest 单元测试
# ═══════════════════════════════════════════

def run_pytest(report: CheckReport) -> bool:
    """运行 pytest 测试"""
    print("  🔍 运行单元测试...", end=" ")
    test_dir = TESTS_DIR
    if not test_dir.exists():
        print("无测试目录，跳过")
        return True

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_dir), "-v", "--tb=short", "-x"],
            capture_output=True, text=True, timeout=300,
            cwd=str(REPO_ROOT)
        )
        output = result.stdout + result.stderr

        if result.returncode == 0:
            print("全部通过")
            return True

        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("FAILED ") or "::FAILED" in line:
                match = re.search(r"(\S+\.py)::(\S+)", line)
                if match:
                    fpath = match.group(1)
                    test_name = match.group(2)
                    if not os.path.isabs(fpath):
                        fpath = str(REPO_ROOT / fpath)
                    report.add_issue(
                        "test_failure", fpath, 0,
                        f"测试失败: {test_name}",
                        severity="high", auto_fixable=False
                    )

        fail_match = re.search(r"(\d+) failed", output)
        fail_count = int(fail_match.group(1)) if fail_match else "?"
        print(f"{fail_count} 个失败")
        return False

    except subprocess.TimeoutExpired:
        report.add_error("pytest 执行超时（5分钟）")
        print("超时")
        return False
    except Exception as e:
        report.add_error(f"pytest 执行错误: {e}")
        print(f"错误: {e}")
        return False


# ═══════════════════════════════════════════
#  4. 静态代码审查
# ═══════════════════════════════════════════

def check_static_analysis(files: List[str], report: CheckReport):
    """静态代码审查 - 检测常见问题模式"""
    print("  🔍 静态代码审查...", end=" ")
    count = 0

    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            continue
        except Exception:
            continue

        has_encoding = False
        for i, line in enumerate(lines[:3], 1):
            if re.search(r"coding[=:]\s*utf-8", line, re.IGNORECASE):
                has_encoding = True
                break

        if not has_encoding and len(lines) > 5:
            base_name = os.path.basename(fpath)
            if not base_name.startswith("_"):
                report.add_issue(
                    "missing_encoding", fpath, 1,
                    "缺少编码声明 # -*- coding: utf-8 -*-",
                    severity="low", auto_fixable=True
                )
                count += 1

        in_comment = False
        for i, line in enumerate(lines, 1):
            stripped = line.rstrip("\n").rstrip("\r")

            if stripped != line.rstrip("\n").rstrip("\r"):
                if stripped.endswith(" ") or stripped.endswith("\t"):
                    pass
            if line.rstrip("\n").rstrip("\r") != line.rstrip("\n").rstrip("\r").rstrip():
                report.add_issue(
                    "trailing_whitespace", fpath, i,
                    "行尾有空白字符",
                    severity="low", auto_fixable=True
                )
                count += 1

            code_part = stripped
            if "#" in code_part:
                code_part = code_part[:code_part.index("#")]

            if "print(" in code_part and "def " not in code_part:
                if not code_part.strip().startswith("#"):
                    if "logger" not in code_part and "logging" not in code_part:
                        report.add_issue(
                            "print_debug", fpath, i,
                            f"调试print语句: {stripped.strip()[:80]}",
                            severity="low", auto_fixable=False
                        )
                        count += 1

            if re.search(r"except\s*:", stripped):
                report.add_issue(
                    "bare_except", fpath, i,
                    f"裸except: {stripped.strip()[:80]}",
                    severity="medium", auto_fixable=False
                )
                count += 1

            if re.search(r"(TODO|FIXME|XXX)", stripped, re.IGNORECASE):
                match = re.search(r"(TODO|FIXME|XXX)[\s:]*(.+)", stripped, re.IGNORECASE)
                msg = match.group(2).strip() if match else stripped.strip()
                report.add_issue(
                    "todo_comment", fpath, i,
                    f"待办: {msg[:80]}",
                    severity="info", auto_fixable=False
                )
                count += 1

        has_tabs = any("\t" in l for l in lines)
        has_spaces = any(re.match(r"^ +", l) for l in lines if l.strip())
        if has_tabs and has_spaces:
            report.add_issue(
                "mixed_indentation", fpath, 0,
                "文件中混用了制表符和空格缩进",
                severity="medium", auto_fixable=True
            )
            count += 1

    print(f"发现 {count} 个问题")


# ═══════════════════════════════════════════
#  5. 自动修复（低风险）
# ═══════════════════════════════════════════

def auto_fix_issues(report: CheckReport) -> int:
    """自动修复低风险问题"""
    fixed_count = 0

    fixable = [i for i in report.issues if i["auto_fixable"]]
    if not fixable:
        return 0

    print(f"  🔧 自动修复 {len(fixable)} 个可修复问题...")

    by_file: Dict[str, List[Dict]] = {}
    for issue in fixable:
        by_file.setdefault(issue["file"], []).append(issue)

    for fpath, issues in by_file.items():
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")
        except Exception:
            continue

        modified = False
        categories = set(i["category"] for i in issues)

        if "missing_encoding" in categories:
            encoding_line = "# -*- coding: utf-8 -*-"
            if not lines[0].lstrip().startswith("#"):
                lines.insert(0, encoding_line)
            else:
                lines[0] = encoding_line
            modified = True
            report.add_fixed("missing_encoding", fpath, 1, "添加编码声明")
            fixed_count += 1

        if "trailing_whitespace" in categories:
            new_lines = []
            tw_fixed = 0
            for line in lines:
                stripped = line.rstrip()
                if stripped != line:
                    tw_fixed += 1
                new_lines.append(stripped)
            lines = new_lines
            if tw_fixed > 0:
                modified = True
                report.add_fixed("trailing_whitespace", fpath, 0, f"移除 {tw_fixed} 行行尾空白")
                fixed_count += 1

        if "mixed_indentation" in categories:
            new_lines = []
            for line in lines:
                leading = len(line) - len(line.lstrip())
                if leading > 0 and line[0] == "\t":
                    tab_count = 0
                    for ch in line:
                        if ch == "\t":
                            tab_count += 1
                        else:
                            break
                    line = "    " * tab_count + line[tab_count:]
                new_lines.append(line)
            lines = new_lines
            modified = True
            report.add_fixed("mixed_indentation", fpath, 0, "统一为4空格缩进")
            fixed_count += 1

        if modified:
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
            except Exception as e:
                report.add_error(f"写入文件失败 {fpath}: {e}")

    print(f"    已修复 {fixed_count} 个")
    return fixed_count


# ═══════════════════════════════════════════
#  主循环
# ═══════════════════════════════════════════

def run_check_round(round_num: int) -> Tuple[CheckReport, bool]:
    """执行一轮检查"""
    report = CheckReport(round_num)

    print(f"\n{'='*60}")
    print(f"  第 {round_num} 轮检查")
    print(f"{'='*60}")

    files = collect_python_files()
    print(f"📁 待检查文件数: {len(files)}")

    check_syntax(files, report)
    check_imports(report)
    check_static_analysis(files, report)
    run_pytest(report)

    print()
    print(report.summary())

    report_path = report.save()
    print(f"\n📄 报告已保存: {os.path.relpath(report_path, str(REPO_ROOT))}")

    all_passed = report.high_severity_count == 0 and report.issue_count == 0
    return report, all_passed


def main():
    import argparse
    parser = argparse.ArgumentParser(description="自动代码检查与修复循环")
    parser.add_argument("--deadline", type=str, default=None,
                        help="截止时间 (HH:MM)，到点后停止")
    parser.add_argument("--max-rounds", type=int, default=0,
                        help="最大循环轮数 (0=无上限)")
    parser.add_argument("--auto-fix", action="store_true", default=True,
                        help="启用自动修复（低风险问题）")
    parser.add_argument("--no-auto-fix", action="store_true",
                        help="禁用自动修复")
    args = parser.parse_args()

    if args.no_auto_fix:
        args.auto_fix = False

    deadline_time = None
    if args.deadline:
        try:
            h, m = map(int, args.deadline.split(":"))
            now = datetime.datetime.now()
            deadline_time = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if deadline_time <= now:
                deadline_time += datetime.timedelta(days=1)
            print(f"⏰ 截止时间: {deadline_time.strftime('%Y-%m-%d %H:%M:%S')}")
        except ValueError:
            print(f"❌ 无效的截止时间格式: {args.deadline}，应为 HH:MM")
            sys.exit(1)

    print(f"🚀 书斋 V66 - 自动代码检查与修复循环启动")
    print(f"   项目根目录: {REPO_ROOT}")
    print(f"   自动修复: {'开启' if args.auto_fix else '关闭'}")
    if args.max_rounds > 0:
        print(f"   最大轮数: {args.max_rounds}")
    print()

    round_num = 1
    all_passed = False

    while True:
        if deadline_time and datetime.datetime.now() >= deadline_time:
            print(f"\n⏰ 到达截止时间 {args.deadline}，停止循环")
            break

        if args.max_rounds > 0 and round_num > args.max_rounds:
            print(f"\n🛑 达到最大轮数 {args.max_rounds}，停止循环")
            break

        report, all_passed = run_check_round(round_num)

        if all_passed:
            print(f"\n🎉 第 {round_num} 轮检查全部通过！无问题发现。")
            break

        if args.auto_fix and report.auto_fixable_count > 0:
            print(f"\n🔧 执行自动修复...")
            fixed = auto_fix_issues(report)
            if fixed > 0:
                print(f"✅ 已自动修复 {fixed} 个低风险问题，进入下一轮验证...")
                round_num += 1
                time.sleep(2)
                continue
            else:
                print("ℹ️  没有成功修复任何问题，停止循环")
                break
        else:
            if args.auto_fix:
                print("\n⚠️  没有可自动修复的问题（均为高/中风险），停止循环")
            else:
                print("\nℹ️  自动修复已禁用，停止循环")
            break

    print(f"\n{'='*60}")
    if all_passed:
        print("  ✅ 最终结果: 所有检查通过")
    else:
        print("  ⚠️  最终结果: 仍有未解决的问题")
    print(f"  总轮数: {round_num}")
    print(f"{'='*60}")

    summary_path = REPORT_DIR / "latest_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "finished_at": datetime.datetime.now().isoformat(),
            "total_rounds": round_num,
            "all_passed": all_passed,
            "auto_fix_enabled": args.auto_fix,
        }, f, ensure_ascii=False, indent=2)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
