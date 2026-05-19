"""Novel Studio — 存储模块

提供基于文件的小说数据持久化，支持 CRUD 操作。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from app.novel_studio.models import Novel, Character, Chapter, WorldSetting, Outline, SceneSetting


from app.runtime_paths import resolve_runtime_paths

DEFAULT_STORAGE_DIR = resolve_runtime_paths().data_dir / "novel_studio"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


class NovelStorage:
    """小说存储引擎"""

    def __init__(self, storage_dir: str | None = None):
        self._root = Path(storage_dir) if storage_dir else DEFAULT_STORAGE_DIR
        _ensure_dir(self._root)

    # ──── 小说 CRUD ────

    def list_novels(self) -> list[dict[str, Any]]:
        """列出所有小说摘要"""
        novels_dir = self._root / "novels"
        _ensure_dir(novels_dir)
        results = []
        for f in sorted(novels_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append({
                    "id": data.get("id", f.stem),
                    "title": data.get("title", "未命名"),
                    "genre": data.get("genre", ""),
                    "status": data.get("status", "planning"),
                    "char_count": len(data.get("characters", {})),
                    "chapter_count": len(data.get("chapters", [])),
                    "updated_at": data.get("updated_at", ""),
                })
            except Exception:
                continue
        return sorted(results, key=lambda x: x.get("updated_at", ""), reverse=True)

    def get_novel(self, novel_id: str) -> Novel | None:
        novels_dir = self._root / "novels"
        path = novels_dir / f"{novel_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Novel(**data)

    def save_novel(self, novel: Novel) -> None:
        novels_dir = self._root / "novels"
        _ensure_dir(novels_dir)
        novel.updated_at = datetime.now(UTC).isoformat()
        path = novels_dir / f"{novel.id}.json"
        path.write_text(
            json.dumps(novel.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def delete_novel(self, novel_id: str) -> bool:
        novels_dir = self._root / "novels"
        path = novels_dir / f"{novel_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    # ──── 角色管理 ────

    def add_character(self, novel_id: str, character: Character) -> Novel | None:
        novel = self.get_novel(novel_id)
        if novel is None:
            return None
        novel.characters[character.id] = character
        self.save_novel(novel)
        return novel

    def update_character(self, novel_id: str, char_id: str, updates: dict) -> Novel | None:
        novel = self.get_novel(novel_id)
        if novel is None or char_id not in novel.characters:
            return None
        char = novel.characters[char_id]
        for k, v in updates.items():
            if hasattr(char, k) and v is not None:
                setattr(char, k, v)
        self.save_novel(novel)
        return novel

    def remove_character(self, novel_id: str, char_id: str) -> Novel | None:
        novel = self.get_novel(novel_id)
        if novel is None or char_id not in novel.characters:
            return None
        del novel.characters[char_id]
        self.save_novel(novel)
        return novel

    # ──── 大纲管理 ────

    def set_outline(self, novel_id: str, outline: Outline) -> Novel | None:
        novel = self.get_novel(novel_id)
        if novel is None:
            return None
        novel.outline = outline
        self.save_novel(novel)
        return novel

    def add_chapter_outline(self, novel_id: str, chapter: "ChapterOutline") -> Novel | None:
        from app.novel_studio.models import ChapterOutline
        novel = self.get_novel(novel_id)
        if novel is None:
            return None
        if novel.outline is None:
            novel.outline = Outline(title=novel.title)
        novel.outline.chapters.append(chapter)
        self.save_novel(novel)
        return novel

    # ──── 已写章节管理 ────

    def add_chapter(self, novel_id: str, chapter: Chapter) -> Novel | None:
        novel = self.get_novel(novel_id)
        if novel is None:
            return None
        novel.chapters.append(chapter)
        novel.status = "writing"
        self.save_novel(novel)
        return novel

    def update_chapter(self, novel_id: str, chapter_id: str, updates: dict) -> Novel | None:
        novel = self.get_novel(novel_id)
        if novel is None:
            return None
        for ch in novel.chapters:
            if ch.id == chapter_id:
                for k, v in updates.items():
                    if hasattr(ch, k) and v is not None:
                        setattr(ch, k, v)
                ch.updated_at = datetime.now(UTC).isoformat()
                break
        self.save_novel(novel)
        return novel

    # ──── 世界观管理 ────

    def set_world(self, novel_id: str, world: WorldSetting) -> Novel | None:
        novel = self.get_novel(novel_id)
        if novel is None:
            return None
        novel.world = world
        self.save_novel(novel)
        return novel

    def add_scene(self, novel_id: str, scene: SceneSetting) -> Novel | None:
        novel = self.get_novel(novel_id)
        if novel is None:
            return None
        if novel.world is None:
            novel.world = WorldSetting(name=f"{novel.title}世界")
        novel.world.scenes[scene.id] = scene
        self.save_novel(novel)
        return novel

    # ──── 数据统计 ────

    def get_stats(self, novel_id: str) -> dict[str, Any]:
        novel = self.get_novel(novel_id)
        if novel is None:
            return {"error": "not_found"}
        return {
            "title": novel.title,
            "status": novel.status,
            "characters": len(novel.characters),
            "chapters_written": len([c for c in novel.chapters if c.status == "final"]),
            "chapters_draft": len([c for c in novel.chapters if c.status == "draft"]),
            "chapters_planned": len(novel.outline.chapters) if novel.outline else 0,
            "total_words": sum(c.word_count for c in novel.chapters),
            "world_scenes": len(novel.world.scenes) if novel.world else 0,
            "genre": novel.genre,
        }

    # ──── 导出 ────

    def export_text(self, novel_id: str) -> str:
        """导出全文为纯文本"""
        novel = self.get_novel(novel_id)
        if novel is None:
            return ""
        lines = [
            f"# {novel.title}",
            f"作者：{novel.author}",
            f"类型：{novel.genre}",
            "=" * 40,
        ]
        if novel.outline:
            lines.append(f"\n## 故事梗概\n{novel.outline.summary}\n")
        for ch in sorted(novel.chapters, key=lambda x: x.number):
            lines.append(f"\n## 第{ch.number}章 {ch.title}\n")
            lines.append(ch.content)
        return "\n".join(lines)
