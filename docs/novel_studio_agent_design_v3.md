# Novel Studio — 角色智能体 + 场景驱动 设计方案 v3

## 核心思想

> 角色不是数据，是 agent。
> 
> 每个角色有自己的记忆（生平+经历），在场景中根据"在场人物+环境"做出行为，
> 大纲最多提供引导词，不直接控制角色。

---

## 一、角色即 Agent

### 现有基础（不用改）

```
Character 模型已有:
  - personality: list[str]    # 性格标签（如["谨慎","隐忍","果断"]）
  - background: str           # 一句话背景
  - motivation: str            # 动机
  - goal: str                 # 目标
  - arc: str                  # 角色弧光
  - attributes: Attributes    # 六维属性
  - relationships: dict       # {角色名: 关系描述}
```

### 新增：角色记忆系统

```
每个角色独立存储的记忆文件：
  data/novel_studio/agents/{novel_id}/{char_id}/
    ├── profile.json    # 基础设定（从 Character 同步）
    ├── memories.jsonl  # 生平大事 + 故事经历，按时间追加
    └── state.json      # 当前状态（位置、关系权重、情绪等）
```

**记忆条目（Memory 已有模型，直接复用）：**
```python
class AgentMemory(BaseModel):
    """角色记忆——生平+经历，角色自己的视角"""
    id: str
    timestamp: int           # 故事时间
    content: str             # 角色视角的叙述
    scene_id: str            # 发生在哪个场景
    scene_name: str          # 场景名（冗余，方便排查）
    participants: list[str]  # 在场其他角色
    emotion: str = ""        # 当时情绪
    importance: float = 0.5  # 0~1，重要性
    tags: list[str] = []     # [生平, 关键事件, 日常]
```

### 角色 Agent 的行为逻辑

```
给定"场景 + 在场角色 + 引导词"
  →  角色 agent 读取自己的记忆（特别是与该场景/人物相关的）
  →  结合性格标签，生成"角色会怎么做"
  →  输出行为描述
```

**不是写死规则**，而是通过 prompt 让 AI 模拟角色的思考过程：
```
你现在是严世藩。
你的性格：狡诈、贪婪、深沉。
你的记忆：
  - 你与张明远第一次见面时，他识破了你的布局（重要度 0.8）
  - 你在江南的走私网络被张明远查到（重要度 0.9）
  - 你安排影杀暗中刺杀张明远但失败（重要度 0.7）
当前场景：苏州码头，夜色中
在场人物：张明远、阿依古丽
你会怎么做？
```

---

## 二、场景驱动的行为流程

### 整体流程

```
用户：写新章节，月下追凶
  →  1. 读取当前场景（苏州码头/废弃货栈...）
  →  2. 确定涉及角色（张明远、严世藩、杨逸...）
  →  3. 每个角色 agent 加载记忆
  →  4. 根据"场景 + 在场人物 + 引导词"产生行为方向
  →  5. AI 综合所有角色的行为方向，生成章节
```

### 引导词的层次

```
大纲引导（最外层）
  └── 写章节指令（用户输入）
       └── 当前场景约束
            └── 角色记忆 + 性格 → 自主行为（最内层）
```

引导词只给方向，不给细节：
- ✅ "严世藩暗中布局" ✓
- ❌ "严世藩派影杀去联系倭寇" ✗（太具体，替角色做决定了）

---

## 三、实现方案

### 需要新增的组件

| 组件 | 职责 |
|------|------|
| `AgentManager` | 管理所有角色 agent，加载/保存记忆 |
| `AgentMemoryStore` | 持久化存储记忆（jsonl 追加） |
| `SceneDriver` | 场景驱动引擎：给定场景→确定角色→加载记忆→生成行为 |

### 不需要改的组件

| 组件 | 原因 |
|------|------|
| `Character` 模型 | 基础设定已有，够用 |
| `WorldEvent` | 世界级事件，与角色记忆互补 |
| `ContextCenter` | 会话持久化，保持 |
| `ToolCallingEngine` | 调用链不变 |

### 存储结构

```
data/novel_studio/agents/{novel_id}/
  ├── {char_id}/
  │   ├── profile.json        # Character 的序列化快照
  │   ├── memories.jsonl      # 追加写入的记忆
  │   └── state.json          # 当前场景位置+情绪状态
  └── ...
```

**记忆只追加（append-only）**：
- 新章节生成后 → 每个经历的角色追加一条记忆
- 保持时间线完整性
- 可按 `timestamp` 回溯角色的完整心路历程

---

## 四、与原设计的关系

| 原设计 v2 | v3 新方向 |
|-----------|-----------|
| `NarrativeLifeEvent` 单独模型 | 复用已有 `Memory`，扩展为 `AgentMemory` |
| `CharacterLifeSkill` 叙事模块 | `AgentManager` + `SceneDriver` |
| 每个角色存生平列表 | 每个角色是 agent，有完整记忆+状态 |
| API 增删查改生平 | API 自动追加记忆+记忆查询 |
| prompt 注入生平摘要 | prompt 注入角色 agent 视角 |

## 五、实现顺序

| 步骤 | 内容 |
|------|------|
| 1 | 新增 `AgentMemory` 模型（基于已有 Memory 扩展） |
| 2 | 新增 `AgentMemoryStore` — 按角色独立存储 memories.jsonl |
| 3 | 新增 `AgentManager` — 加载角色、读取记忆、保存 |
| 4 | 新增 `SceneDriver` — 场景→角色→记忆→行为方向 |
| 5 | 改造 `_format_novel_state` — 注入每个角色的记忆摘要 |
| 6 | 改造 `main.md` prompt — 增加角色 agent 行为指令 |
| 7 | 完成后新增 `POST /chapter` 时自动注入记忆 |
| 8 | 持久化缓冲：`ChatResultStore` 同上 |
