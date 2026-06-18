"""Novel Studio Pipeline — 模块化小说生成管道

核心思想：
- 管道 = 一组独立模块的编排组合
- 每个模块 = 一个 skill，聚焦单一创作环节
- 角色隔离：每个角色独立 Agent + 独立 LLM 调用
- 感知隔离：SceneManager 过滤角色能看到的信息
- 上下文传递：PipelineContext._outputs[module_name] 命名空间
"""
from .base import (
    BaseModule,
    PipelineContext,
    PIPELINE_TEMPLATES,
)
from .orchestrator import (
    PipelineOrchestrator,
    get_orchestrator,
)
from .step_chapter_plan import ChapterPlanModule
from .step_scene_sequence import SceneSequenceModule
from .step_scene_build import SceneBuildModule
from .character_action.step_character_action import CharacterActionModule
from .narrative.step_narrative import NarrativeModule
from .editorial_review.step_editorial_review import EditorialReviewModule
from .world_check.step_world_check import WorldCheckModule
from .world_design.step_world_design import WorldDesignModule
from .world_evolve.step_world_evolve import WorldEvolveModule
from .setting_check.step_setting_check import SettingCheckModule
from .step_memory import MemoryUpdateModule
from .step_scene_loop import SceneLoopModule
from .step_outline_update import OutlineUpdateModule
from .character_emerge.step_character_emerge import CharacterEmergeModule

__all__ = [
    "BaseModule",
    "PipelineContext",
    "PIPELINE_TEMPLATES",
    "PipelineOrchestrator",
    "get_orchestrator",
    "ChapterPlanModule",
    "SceneSequenceModule",
    "SceneBuildModule",
    "CharacterActionModule",
    "NarrativeModule",
    "EditorialReviewModule",
    "WorldCheckModule",
    "WorldDesignModule",
    "WorldEvolveModule",
    "SettingCheckModule",
    "MemoryUpdateModule",
    "SceneLoopModule",
    "OutlineUpdateModule",
    "CharacterEmergeModule",
]


def register_default_modules():
    """注册所有默认模块到全局编排器"""
    orch = get_orchestrator()
    mods = [
        WorldCheckModule(),
        WorldDesignModule(),
        WorldEvolveModule(),
        ChapterPlanModule(),
        SceneSequenceModule(),
        SceneBuildModule(),
        CharacterActionModule(),
        NarrativeModule(),
        SettingCheckModule(),
        EditorialReviewModule(),
        MemoryUpdateModule(),
        SceneLoopModule(),
        OutlineUpdateModule(),
        CharacterEmergeModule(),
    ]
    for m in mods:
        orch.register(m)
    return orch
