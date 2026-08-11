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
    refactorability: str = "unknown"   # high / medium / low（可拆性评估）
    refactor_rationale: str = ""       # 可拆性判断依据
    auto_apply: bool = False    # 恒 False（人工审批）
    functions: list[str] = field(default_factory=list)   # 文件内所有函数
    classes: list[str] = field(default_factory=list)     # 文件内所有类
    validation_checklist: list[str] = field(default_factory=list)
    rollback: str = "git checkout 该文件（未提交前）"
    verify: dict = field(default_factory=dict)   # 验证结果（syntax/import）


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


def _verify_file(file: str) -> dict:
    """对目标文件做只读验证：AST 可解析 + py_compile 通过。"""
    result: dict = {"syntax_ok": False, "parse_error": None}
    try:
        with open(file) as f:
            ast.parse(f.read())
        result["syntax_ok"] = True
    except (OSError, SyntaxError) as e:
        result["parse_error"] = str(e)
        return result
    try:
        import py_compile
        py_compile.compile(file, doraise=True)
        result["compile_ok"] = True
    except Exception as e:  # noqa: BLE001
        result["compile_ok"] = False
        result["compile_error"] = str(e)
    return result


def _classify_refactorability(file: str, tree: ast.AST, kind: str, size: int) -> tuple[str, str]:
    """基于 AST 结构判断 God Object 的可拆性（high/medium/low + 依据）。

    准则来自实战验证的可拆性边界识别：
    - 模块含多个独立职责类，或单类含连续且只被 dispatch 表引用一次的方法簇 → 可拆（high）
    - 巨型 if 链分发器（同层多独立分支）→ 可拆为 handler 方法表（high）
    - 单函数顺序组装依赖（内聚构造函数），变量紧密耦合 → 拆辅助函数会参数膨胀，低收益（low）
    - 方法被类内 10+ 处广泛调用（横切工具方法簇）→ 拆分无意义（low）
    """
    try:
        if kind == "god_object_function":
            # 超长函数：检查是否为 if 链分发器（多同层 if 分支且各自 return）
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if getattr(node, "end_lineno", 0) - getattr(node, "lineno", 0) + 1 < size:
                        continue
                    top_ifs = [s for s in node.body if isinstance(s, ast.If)]
                    has_returns = any(isinstance(s, (ast.Return, ast.If)) for s in node.body)
                    if len(top_ifs) >= 5 and has_returns:
                        return "high", f"巨型 if 链分发器（{len(top_ifs)} 个独立分支），可按 handler 方法表拆分"
                    # 内聚顺序逻辑（注释分阶段但变量紧密耦合）
                    return "low", "高内聚顺序逻辑（单函数组装流程），拆分辅助函数会引入大量参数传递，收益低"
            return "low", "超长函数无独立 if 分支，属内聚逻辑"

        # god_object_module
        classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        # 已拆分痕迹：模块含 *Mixin 类，或主类继承 *Mixin（mixin 拆分模式）
        mixin_names = [c.name for c in classes if c.name.endswith("Mixin")]
        inherits_mixin = any(
            any(isinstance(b, ast.Name) and b.id.endswith("Mixin") for b in c.bases)
            for c in classes
        )
        if mixin_names or inherits_mixin:
            trace = ", ".join(mixin_names) or "主类继承 Mixin"
            return "done", f"模块已有 mixin 拆分痕迹（{trace}），已处理，无需重复拆分"
        if len(classes) >= 2:
            return "high", f"模块含 {len(classes)} 个职责可能独立的类，可按类拆分"
        if len(classes) == 1:
            cls = classes[0]
            methods = [m for m in cls.body if isinstance(m, ast.FunctionDef)]
            # 统计每个方法在类内被调用的次数（横切工具 vs 独立簇）
            import collections
            name_count: dict[str, int] = collections.Counter()
            for m in methods:
                for sub in ast.walk(m):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and isinstance(sub.func.value, ast.Name) and sub.func.value.id == "self":
                        name_count[sub.func.attr] += 1
            # 找到连续方法区间中，内部互相调用但很少被外部调用的簇（候选可拆簇）
            clustered = 0
            for m in methods:
                # 方法内部只调用少数其他方法（低横切）视为可独立
                internal = name_count.get(m.name, 0)
                if internal <= 3:
                    clustered += 1
            if clustered >= 5:
                return "high", f"单类含 {clustered} 个低横切方法，可能构成独立职责簇（如 dispatch handler / 子域）"
            return "low", "单类方法高度内聚且被广泛调用（横切工具簇），拆分破坏 cohesion，收益低"
        if len(funcs) >= 8 and len(classes) == 0:
            return "medium", "模块为多顶层函数集合，边界需人工确认是否构成独立职责簇"
        return "low", "模块无清晰独立职责边界，拆分收益不确定"
    except Exception:  # noqa: BLE001
        return "unknown", "可拆性分析失败，需人工判断"


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
            verify = _verify_file(file)

            if kind == "god_object_module":
                pid = f"refactor.{rel}.module"
                refact, rationale = _classify_refactorability(file, tree, kind, size)
                proposals.append(CodeRefactorProposal(
                    proposal_id=pid,
                    file=rel,
                    target="module",
                    problem=f"超大模块 {size} 行，承担过多职责（cohesion 过高/职责混杂）",
                    suggestion=(
                        "该模块已拆分处理过（mixin 拆分痕迹），无需重复拆分。"
                        if refact == "done"
                        else (
                            "按业务子域拆分为独立子模块：识别文件中相互独立的职责簇，"
                            "将每簇提取为子模块（子目录 + 独立 .py）。参考 http_test_server 已拆分 "
                            "OS/静态页/认证域的先例（deps.py setter 注入模式）。"
                            if refact in ("high", "medium")
                            else f"该模块可拆性评估为 {refact}（{rationale}）。若确需拆分，先人工确认职责边界；"
                                 "若属内聚逻辑，不建议强行拆分（避免破坏 cohesion 与参数膨胀）。"
                        )
                    ),
                    risk_level=_guess_risk(size),
                    refactorability=refact,
                    refactor_rationale=rationale,
                    functions=functions[:40],
                    classes=classes[:20],
                    validation_checklist=[
                        "拆分后各子模块可独立导入",
                        "运行 scripts/scan_import_defects.py 确认无新增导入缺陷",
                        "全量 py_compile 语法检查通过",
                        "重启服务器验证受影响端点 200",
                    ],
                    rollback=f"git checkout -- {file}",
                    verify=verify,
                ))
            elif kind == "god_object_function":
                pid = f"refactor.{rel}.{obj.get('name','fn')}"
                refact, rationale = _classify_refactorability(file, tree, kind, size)
                proposals.append(CodeRefactorProposal(
                    proposal_id=pid,
                    file=rel,
                    target=obj.get("name", "?"),
                    problem=f"超长函数 {obj.get('name')} {size} 行，单一函数承载过多逻辑",
                    suggestion=(
                        "提取辅助方法/纯函数：将函数内相互独立的逻辑块抽离为命名清晰的"
                        "私有方法或模块级函数。遵循『独立关注点=独立 step』原则，不往函数里堆 if/else。"
                        if refact in ("high", "medium")
                        else f"该函数可拆性评估为 {refact}（{rationale}）。若非 if 链分发器，建议保留为内聚逻辑；"
                             "仅当存在重复代码或明确独立子块时才提取。"
                    ),
                    risk_level=_guess_risk(size),
                    refactorability=refact,
                    refactor_rationale=rationale,
                    functions=functions[:40],
                    classes=classes[:20],
                    validation_checklist=[
                        "提取后函数可读性提升（单一职责）",
                        "行为等价（不改外部契约）",
                        "全量 py_compile 语法检查通过",
                        "相关回归测试通过",
                    ],
                    rollback=f"git checkout -- {file}",
                    verify=verify,
                ))
        return proposals

    def build_dev_report(self, diagnose_report: dict[str, Any]) -> dict[str, Any]:
        """整合诊断 + 方案，产出自治开发报告。"""
        god_objects = diagnose_report.get("god_objects", [])
        proposals = self.propose_refactors(god_objects)
        # 待办队列：refactorability 为 high/medium（未处理且值得拆）的提案
        todo_queue = [
            {
                "file": p.file,
                "target": p.target,
                "refactorability": p.refactorability,
                "risk_level": p.risk_level,
                "rationale": p.refactor_rationale,
            }
            for p in proposals
            if p.refactorability in ("high", "medium")
        ]
        return {
            "root_dir": self._root_dir,
            "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "diagnosis": {
                "import_defects": len(diagnose_report.get("import_defects", [])),
                "god_objects": len(god_objects),
            },
            "proposals": [p.__dict__ for p in proposals],
            "proposal_count": len(proposals),
            "todo_queue": todo_queue,
            "todo_queue_count": len(todo_queue),
            "note": "方案仅供审批参考，未自动应用任何代码变更（人机协作边界：高风险变更由人类审批）。todo_queue 为待办重构清单。",
        }
