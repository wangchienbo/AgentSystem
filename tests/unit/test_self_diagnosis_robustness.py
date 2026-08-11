"""Tests for SelfDiagnosisService robustness.

Verifies that the diagnostic service does NOT silently return empty when given
an invalid root_dir (which would cause the self-iteration observation layer to
report a false "healthy" codebase), but instead raises so the problem surfaces.
"""

from __future__ import annotations

import os

import pytest

from app.system.self_diagnosis import SelfDiagnosisService


def _nonexistent_dir() -> str:
    # 一个确定不存在的目录（不依赖 cwd）
    base = os.path.dirname(__file__)
    return os.path.join(base, "no_such_dir_xyz", "nested")


def test_scan_import_defects_raises_on_invalid_root() -> None:
    svc = SelfDiagnosisService(root_dir=_nonexistent_dir())
    with pytest.raises(FileNotFoundError):
        svc.scan_import_defects()


def test_scan_god_objects_raises_on_invalid_root() -> None:
    svc = SelfDiagnosisService(root_dir=_nonexistent_dir())
    with pytest.raises(FileNotFoundError):
        svc.scan_god_objects()


def test_diagnose_codebase_raises_on_invalid_root() -> None:
    svc = SelfDiagnosisService(root_dir=_nonexistent_dir())
    with pytest.raises(FileNotFoundError):
        svc.diagnose_codebase(include_god_objects=True)


def test_valid_root_still_scans() -> None:
    # 用本测试文件所在目录（tests/unit 是有效目录）验证不误抛
    valid = os.path.dirname(__file__)
    svc = SelfDiagnosisService(root_dir=valid)
    # 只要不抛 FileNotFoundError 即视为通过；返回结构为 dict
    report = svc.diagnose_codebase(include_god_objects=True)
    assert isinstance(report, dict)
    assert "counts" in report
