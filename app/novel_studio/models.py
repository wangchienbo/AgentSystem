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

    def default_attributes(self) -> dict[str, int]:
        """按原型返回默认六维属性"""
        profiles = {
            "主角":     {"strength": 12, "dexterity": 12, "constitution": 12, "intelligence": 12, "wisdom": 12, "charisma": 12},
            "女主角":   {"strength": 10, "dexterity": 13, "constitution": 10, "intelligence": 14, "wisdom": 13, "charisma": 14},
            "反派":     {"strength": 14, "dexterity": 11, "constitution": 13, "intelligence": 15, "wisdom": 10, "charisma": 13},
            "导师":     {"strength": 8,  "dexterity": 10, "constitution": 10, "intelligence": 16, "wisdom": 16, "charisma": 12},
            "伙伴":     {"strength": 13, "dexterity": 12, "constitution": 14, "intelligence": 10, "wisdom": 11, "charisma": 10},
            "恋爱对象": {"strength": 10, "dexterity": 13, "constitution": 11, "intelligence": 13, "wisdom": 12, "charisma": 15},
            "对立角色": {"strength": 12, "dexterity": 14, "constitution": 12, "intelligence": 13, "wisdom": 11, "charisma": 10},
            "搞笑角色": {"strength": 10, "dexterity": 15, "constitution": 13, "intelligence": 9,  "wisdom": 8,  "charisma": 14},
            "配角":     {"strength": 10, "dexterity": 10, "constitution": 10, "intelligence": 10, "wisdom": 10, "charisma": 10},
            "叙述者":   {"strength": 8,  "dexterity": 10, "constitution": 9,  "intelligence": 15, "wisdom": 14, "charisma": 12},
        }
        return profiles.get(self.value, profiles["配角"])


# ═══════════════════════════════════════════════════════════════
# 角色属性面板（游戏化）
# ═══════════════════════════════════════════════════════════════

class Attributes(BaseModel):
    """角色六维属性"""
    strength: int = 10      # 力量（近战、负重）
    dexterity: int = 10     # 敏捷（闪避、潜行、精细操作）
    constitution: int = 10  # 体质（耐力、抗性）
    intelligence: int = 10  # 智力（知识、推理、魔法）
    wisdom: int = 10        # 感知（直觉、洞察、意志）
    charisma: int = 10      # 魅力（说服、领导、社交）

    def modifier(self, stat: str) -> int:
        """属性修正值 (D&D 5e 规则: (值-10)//2)"""
        val = getattr(self, stat, 10)
        return (val - 10) // 2

    def sheet(self) -> str:
        return (f"力量{self.strength} | 敏捷{self.dexterity} | 体质{self.constitution}\n"
                f"智力{self.intelligence} | 感知{self.wisdom} | 魅力{self.charisma}")


class EquipmentItem(BaseModel):
    """装备"""
    name: str
    slot: str = "tool"  # weapon | armor | accessory | tool | consumable
    effect: str = ""  # 装备效果描述
    stat_bonuses: dict[str, int] = Field(default_factory=dict)  # e.g. {"perception": 2}
    description: str = ""


class Faction(BaseModel):
    """势力/阵营"""
    name: str
    rank: str = "成员"
    description: str = ""


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
    # ── 演化扩展 ──
    current_scene: str = ""  # 当前所在场景 ID
    knowing_tags: list[str] = Field(default_factory=list)  # 角色"知道"的信息标签
    special_ability: str = ""  # 特殊能力/金手指描述（穿越者、异能者等）
    # ── 属性面板（游戏化） ──
    attributes: Attributes = Field(default_factory=Attributes)
    equipment: list[EquipmentItem] = Field(default_factory=list)
    faction: Faction | None = None

    def effective_perception(self) -> int:
        """有效感知值（含装备加成）"""
        base = self.attributes.wisdom
        for eq in self.equipment:
            base += eq.stat_bonuses.get("perception", 0)
            base += eq.stat_bonuses.get("wisdom", 0)
        return base

    def effective_intelligence(self) -> int:
        """有效智力值"""
        base = self.attributes.intelligence
        for eq in self.equipment:
            base += eq.stat_bonuses.get("intelligence", 0)
        return base

    def ability_tags(self) -> list[str]:
        """从属性/装备/势力推导的能力标签"""
        tags = []
        per = self.effective_perception()
        if per >= 14:
            tags.append("keen_senses")     # 敏锐感官
        if per >= 18:
            tags.append("sixth_sense")     # 第六感
        if self.effective_intelligence() >= 16:
            tags.append("arcane_knowledge") # 奥术知识
        if self.attributes.strength >= 16:
            tags.append("physically_imposing") # 气势凌人
        if self.attributes.charisma >= 16:
            tags.append("charismatic")     # 魅力出众
        if self.faction:
            tags.append(f"faction:{self.faction.name}")
        # 装备标签
        for eq in self.equipment:
            if eq.slot == "weapon":
                tags.append(f"armed:{eq.name}")
        return tags

    def sheet_block(self) -> str:
        """完整的角色面板文本"""
        lines = [
            f"【{self.name}】{self.archetype.value}",
            f"性格：{'、'.join(self.personality) if self.personality else '未知'}",
            f"属性：{self.attributes.sheet()}",
        ]
        if self.faction:
            lines.append(f"势力：{self.faction.name}（{self.faction.rank}）")
        if self.equipment:
            eq_str = "，".join(f"{e.name}[{e.slot}]" for e in self.equipment)
            lines.append(f"装备：{eq_str}")
        if self.goal:
            lines.append(f"目标：{self.goal}")
        if self.special_ability:
            lines.append(f"【特殊能力】{self.special_ability}")
        return "\n".join(lines)


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
    sights: list[str] = Field(default_factory=list)    # 看到什么
    sounds: list[str] = Field(default_factory=list)    # 听到什么
    smells: list[str] = Field(default_factory=list)    # 闻到什么
    textures: list[str] = Field(default_factory=list)  # 触感

    # ── 氛围 ──
    atmosphere: str = ""  # 整体氛围
    mood: str = ""  # 情绪基调

    # ── 视角锁定 ──
    pov: POVConstraint = Field(default_factory=POVConstraint)

    # ── 场景内元素 ──
    visible_objects: list[str] = Field(default_factory=list)
    hidden_objects: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
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

    @property
    def char_count(self) -> int:
        return len(self.characters)


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


# ═══════════════════════════════════════════════════════════════
# 演化引擎模型（世界沙盒）
# ═══════════════════════════════════════════════════════════════

class Memory(BaseModel):
    """角色记忆——角色视角记录的事件"""
    id: str = Field(default_factory=lambda: _unique_id("mem"))
    timestamp: int  # 故事时间刻度
    content: str  # 角色视角的叙述
    scene_id: str = ""
    char_pov: str = ""  # 谁的视角
    participants: list[str] = Field(default_factory=list)  # 在场其他角色
    importance: float = 0.5  # 0~1，影响是否被长期记住
    tags: list[str] = Field(default_factory=list)  # 信息标签


class WorldEvent(BaseModel):
    """世界级大事件——只包含世界/历史层面的事件"""
    id: str = Field(default_factory=lambda: _unique_id("wev"))
    timestamp: int  # 发生在故事时间刻度
    event_type: str = ""  # 战争/天灾/政变/发现
    title: str
    description: str  # 全知视角描述
    public_knowledge: bool = True  # 是否公开信息
    affected_scenes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class CharacterPerception(BaseModel):
    """角色在当前场景的感知"""
    visible_chars: list[str] = Field(default_factory=list)  # 看到的其他角色
    scene_description: str = ""  # 场景描述（角色能看到的版本）
    sounds: list[str] = Field(default_factory=list)
    smells: list[str] = Field(default_factory=list)
    mood: str = ""  # 氛围感受


class TickResult(BaseModel):
    """一次世界演化的结果"""
    tick: int
    actions: list[dict[str, str]] = Field(default_factory=list)  # 角色行动记录
    new_memories: int = 0
    summary: str = ""
