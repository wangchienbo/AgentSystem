"""
self_dev.py — 自治开发闭环的「分析 → 方案」层（Phase 1）

基于 diagnose_codebase 的诊断结果，对 God Object / 超长函数生成
**结构化的代码重构方案（CodeRefactorProposal）**。方案只做分析建议，
不自动应用——高风险变更由人类审批后执行（人机协作边界）。

每条 proposal 包含：
  - 目标文件 / 目标函数
  - 问题诊断（为什么是 God Object）
  - 具体的重构建议（拆分子域、提取辅助函数等）
  - 风险等级 / 验证清单 / 回滚方案
  - 结构摘要（函数列表、类列表）供人类快速判断

设计原则：
  - 纯只读，不修改任何代码
  - 规则式生成（AST 结构分析），不依赖 LLM，可靠可验证
  - 与 app 域的 PatchProposal 完全分离（独立关注点 = 独立模块）
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CodeRefactorProposal:
    """一条代码重构方案（供人类审批，不自动应用）。"""
    proposal_id: str
    file: str
    target: str                 # 函数名或 "module"
    problem: str                # 问题诊断
    suggestion: str             # 重构建议
    risk_level: str             # low / medium / high
    auto_apply: bool = False    # 恒 False（人工审批）
    functions: list[str] = field(default_factory=list)   # 文件内所有函数
    classes: list[str] = field(default_factory=list)     # 文件内所有类
    validation_checklist: list[str] = field(default_factory=list)
    rollback: str = "git checkout 该文件（未提交前）"


def _collect_functions(tree: ast.AST) -> list[str]:
    return [
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _collect_classes(tree: ast.AST) -> list[str]:
    return [
        n.name for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef)
    ]


def _guess_risk(size_lines: int) -> str:
    if size_lines >= 2000:
        return "high"
    if size_lines >= 1000:
        return "medium"
    return "low"


class SelfDevService:
    """代码自治开发方案生成器。纯只读。"""

    def __init__(self, root_dir: str = "app") -> None:
        self._root_dir = root_dir

    def propose_refactors(self, god_objects: list[dict[str, Any]]) -> list[CodeRefactorProposal]:
        """基于 God Object 诊断结果，生成重构方案。"""
        proposals: list[CodeRefactorProposal] = []
        for obj in god_objects:
            file = obj["file"]
            path = os.path.join(self._root_dir, file) if not file.startswith(self._root_dir) else file
            # 相对 root_dir 的路径
            rel = os.path.relpath(file, self._root_dir)
            kind = obj.get("kind")

            try:
                src = open(file).read()
                tree = ast.parse(src)
            except (OSError, SyntaxError):
                continue

            functions = _collect_functions(tree)
            classes = _collect_classes(tree)
            size = obj.get("size_lines", 0)

            if kind == "god_object_module":
                pid = f"refactor.{rel}.module"
                proposals.append(CodeRefactorProposal(
                    proposal_id=pid,
                    file=rel,
                    target="module",
                    problem=f"超大模块 {size} 行，承担过多职责（cohesion 过高/职责混杂）",
                    suggestion=(
                        "按业务子域拆分为独立子模块：识别文件中相互独立的职责簇，"
                        "将每簇提取为子模块（子目录 + 独立 .py）。参考 http_test_server 已拆分 "
                        "OS/静态页/认证域的先例（deps.py setter 注入模式）。"
                    ),
                    risk_level=_guess_risk(size),
                    functions=functions[:40],
                    classes=classes[:20],
                    validation_checklist=[
                        "拆分后各子模块可独立导入",
                        "运行 scripts/scan_import_defects.py 确认无新增导入缺陷",
                        "全量 py_compile 语法检查通过",
                        "重启服务器验证受影响端点 200",
                    ],
                    rollback=f"git checkout -- {file}",
                ))
            elif kind == "god_object_function":
                pid = f"refactor.{rel}.{obj.get('name','fn')}"
                proposals.append(CodeRefactorProposal(
                    proposal_id=pid,
                    file=rel,
                    target=obj.get("name", "?"),
                    problem=f"超长函数 {obj.get('name')} {size} 行，单一函数承载过多逻辑",
                    suggestion=(
                        "提取辅助方法/纯函数：将函数内相互独立的逻辑块抽离为命名清晰的"
                        "私有方法或模块级函数。遵循『独立关注点=独立 step』原则，不往函数里堆 if/else。"
                    ),
                    risk_level=_guess_risk(size),
                    functions=functions[:40],
                    classes=classes[:20],
                    validation_checklist=[
                        "提取后函数可读性提升（单一职责）",
                        "行为等价（不改外部契约）",
                        "全量 py_compile 语法检查通过",
                        "相关回归测试通过",
                    ],
                    rollback=f"git checkout -- {file}",
                ))
        return proposals

    def build_dev_report(self, diagnose_report: dict[str, Any]) -> dict[str, Any]:
        """整合诊断 + 方案，产出自治开发报告。"""
        god_objects = diagnose_report.get("god_objects", [])
        proposals = self.propose_refactors(god_objects)
        return {
            "root_dir": self._root_dir,
            "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "diagnosis": {
                "import_defects": len(diagnose_report.get("import_defects", [])),
                "god_objects": len(god_objects),
            },
            "proposals": [p.__dict__ for p in proposals],
            "proposal_count": len(proposals),
            "note": "方案仅供审批参考，未自动应用任何代码变更（人机协作边界：高风险变更由人类审批）。",
        }
