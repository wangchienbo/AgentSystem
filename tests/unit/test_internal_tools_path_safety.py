"""internal_tools 路径边界 + 搜索遍历上限的单元测试。

覆盖 2026-08-16 修复：
- _normalize_path 强制限定在项目根内（防 LLM 传 ~ 或任意绝对路径卡死）
- search_files 遍历文件数上限（防 os.walk 遍历海量文件阻塞事件循环）
"""

from pathlib import Path

from app.tools.internal_tools import DEFAULT_REPO_ROOT, _normalize_path, search_files


def test_normalize_relative_path_stays_in_repo() -> None:
    assert _normalize_path("app") == DEFAULT_REPO_ROOT / "app"


def test_normalize_absolute_inside_repo_allowed() -> None:
    target = DEFAULT_REPO_ROOT / "app" / "tools"
    assert _normalize_path(str(target)) == target.resolve()


def test_normalize_home_dir_falls_back_to_repo_root() -> None:
    # 传 ~（用户主目录）→ 退回项目根，不允许遍历整个主目录
    result = _normalize_path("~")
    assert result == DEFAULT_REPO_ROOT
    assert str(result).startswith(str(DEFAULT_REPO_ROOT))


def test_normalize_outside_repo_falls_back_to_repo_root() -> None:
    # 传 /etc 或 /home/ubuntu（越界）→ 退回项目根
    result = _normalize_path("/etc")
    assert result == DEFAULT_REPO_ROOT
    result2 = _normalize_path(str(Path.home()))
    assert result2 == DEFAULT_REPO_ROOT


def test_search_files_returns_results_within_repo() -> None:
    result = search_files("def search_files", path="app/tools", file_pattern="*.py")
    assert result["success"] is True
    assert result["matches"] >= 1
    assert all(str(r["file"]).startswith(("app", "internal_tools")) for r in result["results"])


def test_search_files_has_scanned_files_count() -> None:
    result = search_files("__init__", path="app/tools", file_pattern="*.py")
    assert "scanned_files" in result
    assert isinstance(result["scanned_files"], int)


def test_search_outside_path_falls_back_and_completes() -> None:
    # 传越界路径：不抛异常、不卡死、返回成功（退回项目根扫描）
    result = search_files("python", path="/home/ubuntu")
    assert result["success"] is True
