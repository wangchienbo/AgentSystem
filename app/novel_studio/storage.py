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
            # 清理关联的角色状态和演化状态目录
            chars_dir = self._root / "characters" / novel_id
            if chars_dir.exists():
                import shutil
                shutil.rmtree(chars_dir)
            evo_dir = self._root / "evolution" / novel_id
            if evo_dir.exists():
                import shutil
                shutil.rmtree(evo_dir)
            return True
        return False

    # ──── 章节删除 ────

    def delete_chapter(self, novel_id: str, chapter_number: int) -> bool:
        """删除指定编号的章节"""
        novel = self.get_novel(novel_id)
        if novel is None:
            return False
        before = len(novel.chapters)
        novel.chapters = [c for c in novel.chapters if c.number != chapter_number]
        if len(novel.chapters) == before:
            return False
        self.save_novel(novel)
        return True

    def delete_chapters_range(self, novel_id: str, from_number: int, to_number: int) -> int:
        """删除编号范围内的章节，返回删除数量"""
        novel = self.get_novel(novel_id)
        if novel is None:
            return 0
        before = len(novel.chapters)
        novel.chapters = [c for c in novel.chapters if c.number < from_number or c.number > to_number]
        deleted = before - len(novel.chapters)
        if deleted > 0:
            self.save_novel(novel)
        return deleted

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

    def remove_scene(self, novel_id: str, scene_id: str) -> Novel | None:
        """删除世界观下的一个场景"""
        novel = self.get_novel(novel_id)
        if novel is None or novel.world is None or scene_id not in novel.world.scenes:
            return None
        del novel.world.scenes[scene_id]
        self.save_novel(novel)
        return novel

    def update_scene(self, novel_id: str, scene_id: str, updates: dict) -> Novel | None:
        """更新场景属性"""
        novel = self.get_novel(novel_id)
        if novel is None or novel.world is None or scene_id not in novel.world.scenes:
            return None
        scene = novel.world.scenes[scene_id]
        for k, v in updates.items():
            if hasattr(scene, k) and v is not None:
                setattr(scene, k, v)
        self.save_novel(novel)
        return novel

    # ──── 角色级存储（演化用） ────

    def save_character_state(self, novel_id: str, agent_data: dict) -> None:
        """保存角色的完整状态（包含记忆）到独立文件"""
        chars_dir = self._root / "characters" / novel_id
        _ensure_dir(chars_dir)
        char_id = agent_data.get("character", {}).get("id", "unknown")
        path = chars_dir / f"{char_id}.json"
        path.write_text(
            json.dumps(agent_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_character_state(self, novel_id: str, char_id: str) -> dict | None:
        """从独立文件加载角色状态"""
        chars_dir = self._root / "characters" / novel_id
        path = chars_dir / f"{char_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_character_states(self, novel_id: str) -> list[str]:
        """列出所有保存的角色状态 ID"""
        chars_dir = self._root / "characters" / novel_id
        _ensure_dir(chars_dir)
        return [f.stem for f in chars_dir.glob("*.json")]

    # ──── 演化状态存储 ────

    def save_evolution_state(self, novel_id: str, state: dict) -> None:
        """保存演化状态"""
        evo_dir = self._root / "evolution" / novel_id
        _ensure_dir(evo_dir)
        path = evo_dir / "state.json"
        path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_evolution_state(self, novel_id: str) -> dict | None:
        """加载演化状态"""
        evo_dir = self._root / "evolution" / novel_id
        path = evo_dir / "state.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

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

    def export_to_directory(self, novel_id: str, output_dir: Path | str | None = None) -> dict:
        """按「小说名/卷/章」目录结构导出小说，生成 TOC.md 索引
        
        目录结构：
            {output_dir}/{novel_title}/
            ├── TOC.md
            ├── 第001章_标题.md
            ├── 第002章_标题.md
            └── ...
        """
        from pathlib import Path as _Path

        novel = self.get_novel(novel_id)
        if novel is None:
            return {"success": False, "error": "小说未找到"}

        base = _Path(output_dir) if output_dir else self._root / "export"
        novel_dir = base / self._sanitize_path(novel.title)
        novel_dir.mkdir(parents=True, exist_ok=True)

        chapters_dir = novel_dir / "chapters"
        chapters_dir.mkdir(parents=True, exist_ok=True)

        toc_lines = [
            f"# {novel.title}",
            f"",
            f"作者：{novel.author}",
            f"类型：{novel.genre}",
            f"状态：{novel.status}",
            f"",
            "---",
            f"",
            "## 目录",
            f"",
        ]

        exported = []
        for ch in sorted(novel.chapters, key=lambda x: x.number):
            safe_title = self._sanitize_path(ch.title or f"第{ch.number}章")
            filename = f"{ch.number:03d}_{safe_title}.md"
            ch_path = chapters_dir / filename

            # 写章节文件
            ch_content = f"# {ch.title or f'第{ch.number}章'}\n\n{ch.content}"
            ch_path.write_text(ch_content, encoding="utf-8")

            # TOC 条目
            toc_lines.append(f"- [{ch.title or f'第{ch.number}章'}](chapters/{filename})")
            exported.append({
                "chapter_number": ch.number,
                "title": ch.title,
                "file": str(ch_path.relative_to(novel_dir)),
                "word_count": ch.word_count,
            })

        # 写大纲（如果有）
        if novel.outline:
            outline_path = novel_dir / "outline.md"
            outline_content = f"# {novel.title} — 大纲\n\n"
            if novel.outline.summary:
                outline_content += f"## 故事梗概\n\n{novel.outline.summary}\n\n"
            if novel.outline.logline:
                outline_content += f"## 一句话梗概\n\n{novel.outline.logline}\n\n"
            if novel.outline.three_act:
                outline_content += "## 三幕结构\n\n"
                for act_name, act_desc in novel.outline.three_act.items():
                    outline_content += f"### {act_name}\n\n{act_desc}\n\n"
            outline_path.write_text(outline_content, encoding="utf-8")
            toc_lines.insert(6, f"- [故事大纲](outline.md)")

        # 写世界观（如果有）
        if novel.world:
            world_path = novel_dir / "world.md"
            world_content = f"# {novel.world.name}\n\n{novel.world.overview}\n\n"
            if novel.world.rules:
                world_content += "## 世界规则\n\n"
                for rule in novel.world.rules:
                    world_content += f"- {rule}\n"
            if novel.world.scenes:
                world_content += "\n## 场景\n\n"
                for scene in novel.world.scenes.values():
                    world_content += f"### {scene.name}\n\n{scene.description}\n\n"
            world_path.write_text(world_content, encoding="utf-8")
            toc_lines.insert(7, f"- [世界观](world.md)")

        # 写 TOC
        toc_path = novel_dir / "TOC.md"
        toc_path.write_text("\n".join(toc_lines), encoding="utf-8")

        total_words = sum(ch.word_count for ch in novel.chapters)
        return {
            "success": True,
            "novel_title": novel.title,
            "output_dir": str(novel_dir),
            "chapter_count": len(exported),
            "total_words": total_words,
            "files": [str(novel_dir / f) for f in ["TOC.md"] + [e["file"] for e in exported]],
        }

    @staticmethod
    def _sanitize_path(name: str) -> str:
        """清理文件名中的非法字符"""
        import re
        # 移除路径分隔符和常见非法字符
        name = re.sub(r'[\\/:*?"<>|]', '_', name)
        name = name.strip()
        return name or "untitled"
