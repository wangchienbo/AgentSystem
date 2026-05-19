"""Novel Studio — AgentSystem 小说创作应用"""
from app.novel_studio.models import (
    Novel, Character, Chapter, Outline, ChapterOutline,
    WorldSetting, SceneSetting, CharacterArchetype, CharacterPersonality,
    StorySegment, GenerationRequest, GenerationResult,
    DialogueLine,
)
from app.novel_studio.storage import NovelStorage
from app.novel_studio.engine import NovelStudioEngine, DEFAULT_CHARACTER_ARCHETYPES
from app.novel_studio.character_agent import CharacterAgent, CharacterAgentRegistry

__all__ = [
    "Novel", "Character", "Chapter", "Outline", "ChapterOutline",
    "WorldSetting", "SceneSetting", "CharacterArchetype", "CharacterPersonality",
    "StorySegment", "GenerationRequest", "GenerationResult", "DialogueLine",
    "NovelStorage", "NovelStudioEngine", "DEFAULT_CHARACTER_ARCHETYPES",
    "CharacterAgent", "CharacterAgentRegistry",
]
