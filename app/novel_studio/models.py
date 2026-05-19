"""Novel Studio — 数据模型

定义小说创作应用的核心数据结构。
"""
from __future__ import annotations

from datetime import datetime, UTC
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, Field


def _unique_id(prefix: str = "id") -> str:
    ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    short = uuid.uuid4().hex[:8]
    return f"{prefix}_{ts}_{short}"


class CharacterPersonality(str, Enum):
    """角色性格类型"""
    BRAVE = "勇敢"
    CAUTIOUS = "谨慎"
    WITTY = "机智"
    MYSTERIOUS = "神秘"
    GENTLE = "温和"
    FIERY = "火爆"
    COLD = "冷酷"
    NAIVE = "天真"
    CUNNING = "狡诈"
    NOBLE = "高贵"
    ROGUISH = "痞气"
    MELANCHOLY = "忧郁"
    CUSTOM = "自定义"


class CharacterArchetype(str, Enum):
    """角色原型"""
    HERO = "主角"
    HEROINE = "女主角"
    VILLAIN = "反派"
    MENTOR = "导师"
    SIDEKICK = "伙伴"
    LOVE_INTEREST = "恋爱对象"
    ANTAGONIST = "对立角色"
    COMIC_RELIEF = "搞笑角色"
    SUPPORTING = "配角"
    NARRATOR = "叙述者"


class Character(BaseModel):
    """角色设定"""
    id: str = Field(default_factory=lambda: _unique_id("char"))
    name: str
    archetype: CharacterArchetype = CharacterArchetype.SUPPORTING
    personality: list[str] = Field(default_factory=list)  # 性格标签列表
    background: str = ""  # 背景故事
    motivation: str = ""  # 动机
    goal: str = ""  # 目标
    flaw: str = ""  # 缺点
    speech_style: str = ""  # 说话风格描述
    appearance: str = ""  # 外貌描述
    relationships: dict[str, str] = Field(default_factory=dict)  # {角色名: 关系描述}
    arc: str = ""  # 角色弧光（成长轨迹）
    is_active: bool = True

    def personality_prompt(self) -> str:
        """生成角色人格 prompt，用于 LLM 模拟该角色"""
        parts = [f"你扮演的角色是：{self.name}"]
        parts.append(f"角色类型：{self.archetype.value}")
        if self.personality:
            parts.append(f"性格特征：{'、'.join(self.personality)}")
        if self.speech_style:
            parts.append(f"说话风格：{self.speech_style}")
        if self.background:
            parts.append(f"背景：{self.background}")
        if self.motivation:
            parts.append(f"动机：{self.motivation}")
        if self.goal:
            parts.append(f"目标：{self.goal}")
        if self.flaw:
            parts.append(f"缺点：{self.flaw}")
        parts.append("\n你在所有回复中必须完全代入这个角色，用角色的口吻、语气和价值观说话。")
        parts.append("不要跳出角色，不要解释你在扮演。你就是这个角色本人。")
        return "\n".join(parts)


class POVConstraint(BaseModel):
    """视角约束——角色能看到/知道什么"""
    character_id: str = ""  # POV 角色 ID，空 = 全知视角
    character_name: str = ""  # 冗余，方便排查
    known_facts: list[str] = Field(default_factory=list)  # 角色当前已知的信息
    blind_spots: list[str] = Field(default_factory=list)  # 角色不知道/误解的事
    sensory_limitations: list[str] = Field(default_factory=list)  # 感官限制（如"左眼失明""听力受损"）
    sensory_advantages: list[str] = Field(default_factory=list)  # 感官优势（如"夜视""嗅觉敏锐"）


class SceneSetting(BaseModel):
    """场景设定——带感官细节和视角锁定"""
    id: str = Field(default_factory=lambda: _unique_id("scene"))
    name: str
    description: str = ""  # 全知描述（仅用于开发参考，生成正文时不暴露给 LLM）

    # ── 场地信息 ──
    time_period: str = ""  # 时代/时间
    location: str = ""  # 地点
    weather: str = ""
    lighting: str = ""  # 光线条件（"昏暗""正午阳光""紫灰色天光"）
    temperature: str = ""  # 温度体感

    # ── 感官细节（POV 角色能感知到的） ──
    sights: list[str] = Field(default_factory=list)    # 看到什么：["倒塌的黑石墙", "发光的碎片", "巨大的骨架"]
    sounds: list[str] = Field(default_factory=list)    # 听到什么：["风声", "远处的撞击声", "碎石滚动"]
    smells: list[str] = Field(default_factory=list)    # 闻到什么：["焦糊味", "尘土", "金属腥气"]
    textures: list[str] = Field(default_factory=list)  # 触感：["粗糙的石面", "锋利的碎石边缘", "湿冷的空气"]

    # ── 氛围 ──
    atmosphere: str = ""  # 整体氛围
    mood: str = ""  # 情绪基调

    # ── 视角锁定 ──
    pov: POVConstraint = Field(default_factory=POVConstraint)

    # ── 场景内元素 ──
    visible_objects: list[str] = Field(default_factory=list)  # POV 可见的物品
    hidden_objects: list[str] = Field(default_factory=list)   # 场景中隐藏的（不在 POV 视野内）
    rules: list[str] = Field(default_factory=list)  # 该场景的特殊规则
    tags: list[str] = Field(default_factory=list)


class WorldSetting(BaseModel):
    """世界观设定"""
    id: str = Field(default_factory=lambda: _unique_id("world"))
    name: str
    overview: str = ""
    rules: list[str] = Field(default_factory=list)  # 世界规则/物理定律
    factions: list[dict[str, Any]] = Field(default_factory=list)  # 势力/阵营
    magic_system: str = ""  # 魔法/超自然体系
    technology_level: str = ""
    history: str = ""
    geography: str = ""
    culture: str = ""
    scenes: dict[str, SceneSetting] = Field(default_factory=dict)  # {scene_id: scene}
    tags: list[str] = Field(default_factory=list)


class ChapterOutline(BaseModel):
    """章节大纲"""
    id: str = Field(default_factory=lambda: _unique_id("chout"))
    number: int = 1
    title: str = ""
    summary: str = ""
    key_events: list[str] = Field(default_factory=list)
    characters_involved: list[str] = Field(default_factory=list)  # 角色名列表
    settings: list[str] = Field(default_factory=list)  # 场景名列表
    pov_character: str = ""  # 视角角色
    word_count_estimate: int = 2000
    status: str = "draft"  # draft | writing | done


class Outline(BaseModel):
    """完整大纲"""
    id: str = Field(default_factory=lambda: _unique_id("outline"))
    title: str
    logline: str = ""  # 一句话梗概
    summary: str = ""  # 完整故事摘要
    three_act: dict[str, str] = Field(default_factory=lambda: {
        "act1": "", "act2": "", "act3": ""
    })
    chapters: list[ChapterOutline] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    tone: str = ""  # 基调（悬疑/轻松/黑暗/史诗）


class Chapter(BaseModel):
    """已完成的章节内容"""
    id: str = Field(default_factory=lambda: _unique_id("ch"))
    outline_id: str = ""
    number: int
    title: str
    content: str = ""
    word_count: int = 0
    status: str = "draft"  # draft | revised | final
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    notes: str = ""


class Novel(BaseModel):
    """小说主模型"""
    id: str = Field(default_factory=lambda: _unique_id("novel"))
    title: str
    author: str = ""
    genre: str = ""  # 类型
    outline: Outline | None = None
    characters: dict[str, Character] = Field(default_factory=dict)  # {char_id: character}
    world: WorldSetting | None = None
    chapters: list[Chapter] = Field(default_factory=list)
    status: str = "planning"  # planning | writing | editing | published
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    tags: list[str] = Field(default_factory=list)


class DialogueLine(BaseModel):
    """对话行（用于角色对话生成）"""
    speaker: str  # 角色名
    content: str
    emotion: str = ""  # 情绪指示
    action: str = ""  # 伴随动作


class StorySegment(BaseModel):
    """故事片段（生成结果）"""
    type: str = "narration"  # narration | dialogue | description | action
    content: str
    pov_character: str = ""


class GenerationRequest(BaseModel):
    """生成请求"""
    novel_id: str
    context: dict[str, Any] = Field(default_factory=dict)
    instruction: str = ""
    characters_to_involve: list[str] = Field(default_factory=list)
    style: str = "narration"


class GenerationResult(BaseModel):
    """生成结果"""
    content: str
    segments: list[StorySegment] = Field(default_factory=list)
    token_usage: dict[str, int] = Field(default_factory=dict)
