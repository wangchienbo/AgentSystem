# Novel Studio — 世界演化引擎设计

## 核心理念

> 不是「写小说」，而是「搭世界，看它自己长成故事」。

```
角色Agent ←→ 角色Agent ←→ 角色Agent
     ↕           ↕           ↕
      ─── 世界模块（场景/时间线）───
                  ↕
           叙事模块（观察+旁白）
```

---

## 一、架构总览

```
┌──────────────────────────────────────────────────────────┐
│                    NovelStudioEngine                      │
├─────────────┬──────────────┬──────────────┬──────────────┤
│  世界模块    │  角色系统     │  场景调度     │  叙事引擎     │
│  WorldModule │  CharSystem  │  SceneManager│ NarrativeGen │
├─────────────┼──────────────┼──────────────┼──────────────┤
│ • 大事件时间线 │ • 角色Agent   │ • 场景状态    │ • 章节生成     │
│ • 地理/地点   │ • 记忆系统    │ • POV管理    │ • 旁白抽象     │
│ • 物理/社会规则│ • 关系网      │ • 感知过滤    │ • 风格控制     │
│ • 当前时间戳   │ • 知识隔离    │             │              │
└─────────────┴──────────────┴──────────────┴──────────────┘
                        ↕
┌──────────────────────────────────────────────────────────┐
│                    存储层 Storage                         │
│   novels/ | characters/ | sessions/ | world/ | scenes/   │
└──────────────────────────────────────────────────────────┘
```

---

## 二、模块设计

### 2.1 世界模块 (WorldModule)

```python
class WorldModule:
    """世界状态容器"""
    
    # 时间线：只存世界级大事件，不包含角色私人事件
    timeline: list[WorldEvent]
    # 场景库：所有地点及其描述
    scenes: dict[str, SceneDef]
    # 规则：物理/社会/超自然规则
    rules: list[Rule]
    # 当前时间（故事内）
    current_time: int  # 刻度单位
```

**设计原则：** 世界模块是「客观真实」。角色只能通过感知和社交间接了解它。

角色不知道的事：世界时间线上未公开的事件、角色不在场的场景。

---

### 2.2 角色系统 (CharacterSystem)

每个角色是一个**独立 Agent**，拥有自己的上下文/记忆。

```python
class Character:
    id: str
    name: str
    archetype: str        # 角色原型
    personality: list[str]  # 性格标签
    
    # 记忆系统（角色"知道"的事）
    memories: list[Memory]
    # 关系网 {角色id: 关系描述}
    relationships: dict[str, Relationship]
    # 当前位置
    current_scene: str | None
    # 当前知识（从记忆提取的摘要）
    knowledge: str
    
class Memory:
    timestamp: int
    content: str          # 角色视角的叙述
    scene_id: str         # 发生在哪
    participants: list[str]  # 谁在场
    importance: float     # 0~1，影响是否被长期记住
```

#### 角色 Agent 调用规则

当需要"角色做什么"时，构造 prompt：

```
你是{name}。
你的性格：{personality}
你当前在：{scene_name}
你看到/听到：{perceptions}
你知道的事：{knowing_summary}
你认识的人在场：{present_relations}

你在这个场景中会做什么？请用第一人称说一句话或做一个动作。
```

**关键约束：** 
- 不注入角色不知道的信息
- 只注入角色当前场景的感知
- 只注入角色记忆里有的知识

---

### 2.3 场景调度 (SceneManager)

```python
class SceneManager:
    """管理谁在哪个场景，谁能感知到什么"""
    
    # 当前场景的所有角色
    scene_occupants: dict[str, set[str]]  # scene_id → {char_ids}
    
    def get_perception(char_id, scene_id) -> Percept:
        """角色在场景中能看到/听到什么"""
        # 可见范围：同一场景的其他角色、场景特征
        # 不可见：不在场的角色行动、超出感知范围的事物
    
    def enter_scene(char_id, scene_id):
        """角色进入场景"""
    
    def get_visible_chars(char_id) -> list[str]:
        """角色在当前场景能看到哪些其他角色"""
```

---

### 2.4 叙事引擎 (NarrativeEngine)

叙事模块**不参与演化**，它只做两件事：

1. **观察**：记录角色在场景中的互动
2. **抽象**：从原始互动中提取有叙事价值的内容，写成章节

```python
class NarrativeEngine:
    def generate_chapter(self, time_range) -> Chapter:
        """从一段时间内的角色互动，抽象出叙事性章节"""
        # 1. 收集该时间段内的所有角色互动记录
        # 2. 按叙事相关性排序/筛选
        # 3. 以第三人称有限视角写故事
        # 4. 不暴露角色未被叙述的内心
```

---

## 三、演化流程

### 单轮演化（tick）

```
1. 世界时间 +1
2. 检查是否有预定的大事件（世界模块）
3. 对每个场景中的角色：
   a. 感知当前场景（SceneManager.get_perception）
   b. 角色 Agent 决策 → 产生行动/对话
   c. 行动结果存入角色记忆
   d. 行动结果可能改变场景状态
4. 场景间信息扩散：
   a. 角色离开场景 → 带走记忆
   b. 角色进入新场景 → 可能传播信息
5. 叙事检查：是否生成章节
```

### 信息隔离示例

```
场景：集市
在场角色：陆辰、摊贩甲

陆辰知道：
  - 自己昨晚在废墟中过夜（记忆）
  - 集市很热闹（感知）
  - 苏瑶昨天往北走了（如果知道的话）

陆辰不知道：
  - 苏瑶此刻在做什么（不在同一场景）
  - 暗影教团的总部在哪（没听说过）
  - 千里之外的某个事件（没渠道知道）
```

---

## 四、与现有系统的集成

```
用户 → dispatch_app_task(novel_studio, tick, {...})
  → MasterControl → Worker
    → Engine.tick() → 一次世界演化
    
用户 → dispatch_app_task(novel_studio, generate_chapter, {...})
  → MasterControl → Worker
    → NarrativeEngine.generate_chapter() → 写章节
```

每个角色 Agent 调用：
```
Worker → ModelRouter.chat(...)
  → 注入角色上下文（非全量模型调用）
  → 返回角色行动
```

---

## 五、数据模型

```
Novel
├─ id / title / genre
├─ world: WorldState
│  ├─ current_time: int
│  ├─ timeline: WorldEvent[]
│  ├─ scenes: SceneDef[]
│  └─ rules: Rule[]
├─ characters: Character[]
│  ├─ 每个 Character 有独立的 memories / relationships
│  └─ 每个 Character 有独立的 memory file
│      └─ memory/char_{id}.json
├─ chapters: Chapter[]
└─ evolved: bool  # 是否已演化
```

记忆存储分开：每个角色一个独立的记忆文件，不混在一起。
```
novels/{novel_id}/
├── novel.json          # 小说元数据 + 世界
├── world.json          # 世界状态
├── characters/
│   ├── char_luchen.json     # 角色数据
│   ├── char_luchen_mem.json # 角色记忆
│   ├── char_suyao.json
│   └── char_suyao_mem.json
├── scenes/
│   ├── scene_01.json
│   └── scene_02.json
├── chapters/
│   ├── chapter_01.json
│   └── chapter_02.json
└── timeline.json       # 大事件时间线
```

---

## 六、实现阶段

### Phase 1（现在能做的）
- 重构数据模型：角色拆出独立记忆文件
- 实现 `SceneManager`：场景内角色可见性
- 实现角色 Agent 调用（简单的：角色决策 → 行动/对话）
- 实现基本 tick 流程

### Phase 2
- 信息隔离：角色知识边界
- 社交传播：交谈 → 知识扩散
- 记忆重要度：角色遗忘机制

### Phase 3
- 叙事引擎：从互动记录抽象出章节
- 长期演化：数天数月的自动模拟
- 叙事风格控制
