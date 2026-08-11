"""_classify_refactorability 可拆性判断的单元测试。

用真实项目文件验证——对应三轮实战验证的结论，防止可拆性判断逻辑回归：
- 内聚构造函数（build_runtime / execute_turns）→ low（不该拆）
- 已实际拆分的目标（skill_factory / light_brain_gateway）→ high（有可拆边界）
- 巨型 if 链分发器 → high
- 多顶层函数模块 → medium

同时也用小型构造样本覆盖各 AST 分支，确保判断逻辑本身正确。
"""
from __future__ import annotations

import ast

from app.system.self_dev import _classify_refactorability

BASE = "app"

# ── 构造样本：覆盖各 AST 分支 ─────────────────────────────────────────────

def _parse(src: str) -> ast.AST:
    return ast.parse(src)


def test_function_giant_if_chain_dispatcher_is_high():
    """巨型 if 链分发器（≥5 同层 if + return）→ high。"""
    src = """\
def _execute_step(self, x):
    if kind == 'a':
        return self._a(x)
    if kind == 'b':
        return self._b(x)
    if kind == 'c':
        return self._c(x)
    if kind == 'd':
        return self._d(x)
    if kind == 'e':
        return self._e(x)
    return None
"""
    tree = _parse(src)
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    size = fn.end_lineno - fn.lineno + 1
    refact, _ = _classify_refactorability("x.py", tree, "god_object_function", size)
    assert refact == "high"


def test_function_cohesive_sequential_is_low():
    """高内聚顺序逻辑（无独立 if 分支）→ low（拆辅助函数会参数膨胀）。"""
    src = """\
def build_runtime(config):
    a = config.get('a')
    b = config.get('b')
    c = compute(a)
    d = compute(b)
    return {'x': c, 'y': d}
"""
    tree = _parse(src)
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    size = fn.end_lineno - fn.lineno + 1
    refact, _ = _classify_refactorability("x.py", tree, "god_object_function", size)
    assert refact == "low"


def test_module_multiple_classes_is_high():
    """模块含 ≥2 个职责独立类 → high。"""
    src = """\
class ServiceA:
    def run(self):
        return 1

class ServiceB:
    def run(self):
        return 2
"""
    tree = _parse(src)
    refact, _ = _classify_refactorability("x.py", tree, "god_object_module", 50)
    assert refact == "high"


def test_module_with_mixin_trace_is_done():
    """模块已有 mixin 拆分痕迹（*Mixin 类 + 主类继承）→ done（已处理）。"""
    src = """\
class _XxxMixin:
    def a(self):
        return 1

class Service(_XxxMixin):
    def run(self):
        return self.a()
"""
    tree = _parse(src)
    refact, rationale = _classify_refactorability("x.py", tree, "god_object_module", 60)
    assert refact == "done"
    assert "Mixin" in rationale


def test_module_inheriting_mixin_is_done():
    """主类继承 Mixin（无独立 Mixin 定义，来自外部）→ 仍识别为已拆分。"""
    src = """\
class Service(_SkillToBlueprintMappingMixin):
    def run(self):
        return self.a()
"""
    tree = _parse(src)
    refact, _ = _classify_refactorability("x.py", tree, "god_object_module", 40)
    assert refact == "done"


def test_module_multiple_top_functions_is_medium():
    """模块为多顶层函数集合 → medium。"""
    src = """\
def f1(): return 1
def f2(): return 2
def f3(): return 3
def f4(): return 4
def f5(): return 5
def f6(): return 6
def f7(): return 7
def f8(): return 8
def f9(): return 9
"""
    tree = _parse(src)
    refact, _ = _classify_refactorability("x.py", tree, "god_object_module", 40)
    assert refact == "medium"


def test_single_high_cohesion_class_is_low():
    """单类方法高度内聚且被广泛调用（横切工具簇）→ low。

    构造：类内方法彼此互相调用（每个方法内部调用其他多个方法），
    无独立职责簇，属横切工具集合 → 不应拆。
    """
    src = """\
class Service:
    def run(self):
        self._a()
        self._b()
        self._c()
        self._d()
        return 1
    def _a(self):
        self._b(); self._c(); self._d(); self._e()
    def _b(self):
        self._a(); self._c(); self._e()
    def _c(self):
        self._a(); self._b(); self._d()
    def _d(self):
        self._b(); self._c(); self._e()
    def _e(self):
        self._a(); self._c(); self._d()
"""
    tree = _parse(src)
    refact, _ = _classify_refactorability("x.py", tree, "god_object_module", 80)
    assert refact == "low"


# ── 真实文件：对应实战验证结论 ────────────────────────────────────────────

def _classify_real(rel_path: str, kind: str, name: str | None = None) -> str:
    src = open(f"{BASE}/{rel_path}").read()
    tree = ast.parse(src)
    if kind == "god_object_function":
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == name)
        size = fn.end_lineno - fn.lineno + 1
        refact, _ = _classify_refactorability(f"{BASE}/{rel_path}", tree, kind, size)
    else:
        refact, _ = _classify_refactorability(f"{BASE}/{rel_path}", tree, kind, len(src.splitlines()))
    return refact


def test_real_build_runtime_is_low():
    """真实内聚构造函数 build_runtime → low（不该拆）。"""
    assert _classify_real("bootstrap/runtime.py", "god_object_function", "build_runtime") == "low"


def test_real_execute_turns_is_low():
    """真实高内聚顺序逻辑 execute_turns → low。"""
    assert _classify_real(
        "ai/tool_calling_engine.py", "god_object_function", "execute_turns"
    ) == "low"


def test_real_skill_factory_is_done():
    """真实 skill_factory 已有 mixin 拆分 → 识别为 done（已处理）。"""
    assert _classify_real("skills/skill_factory.py", "god_object_module") == "done"


def test_real_light_brain_gateway_is_done():
    """真实 light_brain_gateway 已有 mixin 拆分 → done（已处理）。"""
    assert _classify_real("system/gateway/light_brain_gateway.py", "god_object_module") == "done"
