#!/usr/bin/env python3
"""
scan_import_defects.py — 扫描 Python 包内 from-import 缺陷

排查两类确凿的导入缺陷（此类缺陷只在被调用时才抛 ImportError，
运行日志中往往从未触发，是潜伏 bug）：
  1. 模块级 `from X import Y` 但 Y 在 X 中不存在
  2. 函数体/方法体内的延迟导入 `from X import Y` 但 Y 在 X 中不存在

用法:
  python scan_import_defects.py [package_dir]   # 默认 app/novel_studio
  python scan_import_defects.py app/system

原理: 用 AST 解析，importlib 加载目标模块，hasattr 校验每个导入名。
不执行目标代码，仅做名字存在性校验，安全无副作用。
"""
import ast
import importlib
import os
import sys


def _check(module_name: str, imported_names: list[str],
           path: str, lineno: int, problems: list) -> None:
    """校验单个 from-import 的所有名字"""
    try:
        mod = importlib.import_module(module_name)
    except Exception as e:  # noqa: BLE001
        problems.append((path, lineno,
                         f"模块导入失败: {module_name} -> {type(e).__name__}: {e}"))
        return
    for name in imported_names:
        if name == "*":
            continue
        if not hasattr(mod, name):
            problems.append((path, lineno,
                             f"导入名不存在: {module_name}.{name}"))


def _scan_node(node, path, problems) -> None:
    if not isinstance(node, ast.ImportFrom):
        return
    if not node.module or not node.module.startswith("app"):
        return
    _check(node.module, [a.name for a in node.names], path, node.lineno, problems)


def scan(package_dir: str) -> list[tuple[str, int, str]]:
    """扫描目录下所有 .py 的 from-import 缺陷，返回 [(path, lineno, msg)]"""
    problems: list[tuple[str, int, str]] = []
    if not os.path.isdir(package_dir):
        print(f"目录不存在: {package_dir}")
        return problems

    for root, _dirs, files in os.walk(package_dir):
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
                _scan_node(node, path, problems)

            # 函数体/方法体内延迟 from-import
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.ImportFrom):
                            _scan_node(sub, path, problems)

    return problems


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "app/novel_studio"
    problems = scan(target)
    print(f"=== from-import 缺陷扫描: {target} ===")
    if problems:
        seen = set()
        for path, ln, msg in problems:
            if (path, ln, msg) in seen:
                continue
            seen.add((path, ln, msg))
            print(f"  {path}:{ln}  {msg}")
        print(f"\n共 {len(problems)} 处缺陷")
        return 1
    print("  无缺陷 ✓ (所有 from-import 目标均真实存在)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
