"""Prompt 加载工具 — 分层提示词工程的核心

每个模块的提示词存放在模块文件夹下的 prompts/ 目录中。
- pipeline/narrative/prompts/     → 叙事模块的提示词
- pipeline/character_action/prompts/ → 角色行动模块的提示词
- pipeline/editorial_review/prompts/ → 审核模块的提示词

使用方式：
    from .prompt_loader import load_prompt
    template = load_prompt("narrative", "system_writer.md")
    prompt = template.format(novel_title=novel.title)
"""

from pathlib import Path

# prompt_loader.py 自身所在的目录 = pipeline/
_BASE_DIR = Path(__file__).resolve().parent


def load_prompt(module_name: str, prompt_name: str) -> str:
    """从模块的 prompts/ 目录加载提示词模板

    Args:
        module_name: 模块文件夹名称 (如 "narrative", "character_action")
        prompt_name: 提示词文件名称 (如 "system_writer.md")

    Returns:
        提示词模板文本（含 {placeholder} 占位符，供 .format() 填充）
    """
    path = _BASE_DIR / module_name / "prompts" / prompt_name
    if not path.exists():
        raise FileNotFoundError(
            f"提示词文件未找到: {path}\n"
            f"请确认文件存在于 pipeline/{module_name}/prompts/ 目录中"
        )
    return path.read_text(encoding="utf-8")


# ─── 小说上下文构建 ───────────────────────────────────────
def build_novel_context(novel) -> str:
    """从 Novel 对象构建统一的「小说级上下文块」

    包含小说类型、世界观设定、世界规则、专属写作指令等信息。
    注入到每个 pipeline 步骤的 prompt 中，让 LLM 始终了解小说的核心设定。

    返回格式化的标记块，可注入到任意 prompt 顶部。
    """
    if novel is None:
        return ""

    parts = [
        f"【小说】{novel.title}",
        f"【类型】{novel.genre}" if novel.genre else "",
    ]

    # 小说简介（面向用户的故事概述，也帮助 AI 理解故事定位）
    description = getattr(novel, "description", "") or ""
    if description:
        parts.append(f"【小说简介】{description}")

    # 世界观概述
    world = getattr(novel, "world", None)
    if world is not None:
        overview = getattr(world, "overview", "") or ""
        if overview:
            parts.append(f"【世界观概述】{overview}")
        rules = getattr(world, "rules", None) or []
        if rules:
            parts.append("【世界规则】")
            for r in rules:
                parts.append(f"  {r}")

    # 小说专属写作指令/提示词
    custom_prompt = getattr(novel, "custom_prompt", "") or ""
    if custom_prompt:
        parts.append(f"【小说专属写作指令】\n{custom_prompt}")

    # 过滤空段落
    parts = [p for p in parts if p]

    if not parts:
        return ""

    context = "\n".join(parts)
    return f"\n## 📖 小说核心设定\n{context}\n"
