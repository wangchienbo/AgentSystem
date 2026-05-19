"""PromptComposer — 按需组装 system prompt。

从 prompts/index.md 读取索引，根据当前执行上下文（授权态/任务模式/是否有 pending task）
筛选符合条件的子 prompt，按 weight 排序后组装为完整的 system prompt。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# 项目根目录（自动探测）
_PROJECT_ROOT: Path | None = None


def _get_project_root() -> Path:
    global _PROJECT_ROOT
    if _PROJECT_ROOT is None:
        # 从当前文件位置向上查找 pyproject.toml
        cwd = Path(os.getcwd())
        for parent in [cwd] + list(cwd.parents):
            if (parent / "pyproject.toml").exists():
                _PROJECT_ROOT = parent
                break
        if _PROJECT_ROOT is None:
            _PROJECT_ROOT = cwd
    return _PROJECT_ROOT


class PromptComposer:
    """根据上下文条件，从 prompts/ 目录按需组装 system prompt。

    用法:
        composer = PromptComposer()
        system_prompt = composer.compose({
            "authorization": {"is_authorized": True},
            "task_mode": {"mode": "engineering"},
        })
    """

    def __init__(self, prompts_dir: str | Path | None = None):
        self._prompts_dir = Path(prompts_dir) if prompts_dir else _get_project_root() / "prompts"
        self._index: list[dict[str, Any]] | None = None
        self._cache: dict[str, str] = {}

    # ── 公开方法 ──

    def compose(self, context: dict | None = None) -> str:
        """根据给定 context 组装 system prompt。

        Args:
            context: 包含 authorization/task_mode/has_pending_task 等的字典

        Returns:
            组装后的完整 system prompt 文本
        """
        if not self._index_path.exists():
            logger.warning("prompts/index.md not found at %s", self._index_path)
            return ""

        index = self._load_index()
        if not index:
            return ""

        # 按条件筛选
        matched = []
        for entry in index:
            if self._matches_condition(entry, context or {}):
                content = self._read_prompt_file(entry["path"])
                if content:
                    matched.append((entry.get("weight", 0), content))

        # 按 weight 降序排列
        matched.sort(key=lambda x: -x[0])

        # 组装
        parts = [content for _, content in matched]
        return "\n\n".join(parts)

    def reload(self) -> None:
        """重新加载索引和缓存。"""
        self._index = None
        self._cache.clear()

    # ── 条件匹配 ──

    def _matches_condition(self, entry: dict, context: dict) -> bool:
        """判断一条 prompt 是否应该被加载。"""
        load_mode = entry.get("load", "always")

        if load_mode == "always":
            return True

        if load_mode != "conditional":
            return False

        conditions = entry.get("when", [])
        if not conditions:
            return False

        for cond in conditions:
            key = cond.get("key", "")
            expected = cond.get("eq")
            expected_list = cond.get("in")

            # 从 context 读取值（支持点号分隔的多级 key）
            value = self._resolve_key(context, key)

            if expected is not None:
                if value == expected:
                    return True
            if expected_list is not None:
                if value in expected_list:
                    return True

        return False

    @staticmethod
    def _resolve_key(context: dict, key: str) -> Any:
        """从嵌套字典中解析多级 key（如 'authorization.is_authorized'）。"""
        parts = key.split(".")
        current = context
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    # ── 文件读写 ──

    def _load_index(self) -> list[dict[str, Any]]:
        """读取 prompts/index.md 的 YAML 前置数据。"""
        if self._index is not None:
            return self._index

        text = self._read_file(self._index_path)
        if not text:
            self._index = []
            return []

        # 解析 YAML front matter
        try:
            data = yaml.safe_load(text)
            self._index = data.get("prompts", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.warning("Failed to parse prompts/index.md: %s", e)
            self._index = []

        return self._index

    def _read_prompt_file(self, relative_path: str) -> str:
        """读取子 prompt 文件内容。"""
        # 缓存命中
        if relative_path in self._cache:
            return self._cache[relative_path]

        file_path = self._prompts_dir.parent / relative_path
        if not file_path.exists():
            # 也试试以 prompts_dir 为基路径
            file_path = self._prompts_dir / relative_path
        if not file_path.exists():
            logger.warning("Prompt file not found: %s", relative_path)
            return ""

        content = self._read_file(file_path)
        if content:
            self._cache[relative_path] = content
        return content or ""

    @staticmethod
    def _read_file(path: Path) -> str:
        """UTF-8 读文件。"""
        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to read %s: %s", path, e)
            return ""

    @property
    def _index_path(self) -> Path:
        return self._prompts_dir / "index.md"
