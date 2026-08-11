"""
self_diagnosis.py — 代码/架构自治诊断服务（自我迭代的"观察层"）

提供只读、无副作用的静态诊断能力，让系统能"看见自己代码的问题"：
  1. 导入缺陷扫描（模块级 + 函数体内延迟导入的 from-import 目标缺失）
  2. God Object 检测（超大模块、超长函数）

这些诊断是自治开发闭环的第一步——系统基于诊断结果才能进一步
生成修复方案、验证、产出可审阅变更。纯只读，不修改任何代码。

用法：
  from app.system.self_diagnosis import SelfDiagnosisService
  svc = SelfDiagnosisService(root_dir="app")
  report = svc.diagnose_codebase()
"""
from __future__ import annotations

import ast
import importlib
import os
from typing import Any

# God Object 阈值（行数超过即标记为潜在超大模块）
GOD_OBJECT_MODULE_LINES = 800
GOD_OBJECT_FUNCTION_LINES = 300


class SelfDiagnosisService:
    """只读代码健康诊断。"""

    def __init__(self, root_dir: str = "app") -> None:
        self._root_dir = root_dir

    # ── 导入缺陷扫描 ─────────────────────────────
    @staticmethod
    def _check_import(module_name: str, names: list[str],
                      path: str, lineno: int, problems: list) -> None:
        try:
            mod = importlib.import_module(module_name)
        except Exception as e:  # noqa: BLE001
            problems.append({
                "file": path, "line": lineno,
                "kind": "module_import_failure",
                "module": module_name,
                "detail": f"{type(e).__name__}: {e}",
            })
            return
        for name in names:
            if name == "*":
                continue
            if not hasattr(mod, name):
                problems.append({
                    "file": path, "line": lineno,
                    "kind": "import_name_missing",
                    "module": module_name,
                    "name": name,
                    "detail": f"from {module_name} import {name} 但 {name} 不存在",
                })

    def scan_import_defects(self) -> list[dict[str, Any]]:
        """扫描 root_dir 下所有 .py 的 from-import 缺陷（模块级 + 函数体内延迟导入）。"""
        problems: list[dict[str, Any]] = []
        if not os.path.isdir(self._root_dir):
            raise FileNotFoundError(
                f"self_diagnosis 的 root_dir 不存在: {self._root_dir!r}（当前 cwd={os.getcwd()!r}）。"
                "请传入有效绝对路径或在项目根目录运行。静默返回空会导致自治诊断'假健康'，故改为抛错暴露。"
            )

        for root, _dirs, files in os.walk(self._root_dir):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(root, fn)
                try:
                    src = open(path).read()
                    tree = ast.parse(src)
                except (OSError, SyntaxError):
                    continue

                # 模块级 from-import
                for node in tree.body:
                    self._scan_import_node(node, path, problems)
                # 函数体/方法体内延迟 from-import
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        for sub in ast.walk(node):
                            if isinstance(sub, ast.ImportFrom):
                                self._scan_import_node(sub, path, problems)
        return problems

    def _scan_import_node(self, node, path: str, problems: list) -> None:
        if not isinstance(node, ast.ImportFrom):
            return
        if not node.module or not node.module.startswith("app"):
            return
        self._check_import(
            node.module,
            [a.name for a in node.names],
            path, node.lineno, problems,
        )

    # ── God Object 检测 ───────────────────────────
    def scan_god_objects(self) -> list[dict[str, Any]]:
        """检测超大模块与超长函数（潜在 God Object / 上帝类）。"""
        findings: list[dict[str, Any]] = []
        if not os.path.isdir(self._root_dir):
            raise FileNotFoundError(
                f"self_diagnosis 的 root_dir 不存在: {self._root_dir!r}（当前 cwd={os.getcwd()!r}）。"
                "请传入有效绝对路径或在项目根目录运行。静默返回空会导致自治诊断'假健康'，故改为抛错暴露。"
            )

        for root, _dirs, files in os.walk(self._root_dir):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(root, fn)
                try:
                    src = open(path).read()
                    lines = src.splitlines()
                    tree = ast.parse(src)
                except (OSError, SyntaxError):
                    continue
                total = len(lines)
                if total >= GOD_OBJECT_MODULE_LINES:
                    findings.append({
                        "file": path, "line": 1,
                        "kind": "god_object_module",
                        "size_lines": total,
                        "detail": f"超大模块 {total} 行（阈值 {GOD_OBJECT_MODULE_LINES}）",
                    })
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        n_lines = (getattr(node, "end_lineno", 0) or 0) - node.lineno + 1
                        if n_lines >= GOD_OBJECT_FUNCTION_LINES:
                            findings.append({
                                "file": path, "line": node.lineno,
                                "kind": "god_object_function",
                                "name": node.name,
                                "size_lines": n_lines,
                                "detail": f"超长函数 {node.name} {n_lines} 行（阈值 {GOD_OBJECT_FUNCTION_LINES}）",
                            })
        return findings

    # ── 汇总诊断 ─────────────────────────────────
    def diagnose_codebase(self, *, include_god_objects: bool = True) -> dict[str, Any]:
        """运行全部诊断，产出结构化报告。纯只读。"""
        import_defects = self.scan_import_defects()
        result: dict[str, Any] = {
            "root_dir": self._root_dir,
            "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "import_defects": import_defects,
            "counts": {
                "import_defects": len(import_defects),
            },
        }
        if include_god_objects:
            god_objects = self.scan_god_objects()
            result["god_objects"] = god_objects
            result["counts"]["god_objects"] = len(god_objects)
        return result
