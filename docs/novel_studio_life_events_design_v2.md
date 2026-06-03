# Novel Studio — 角色生平轨迹 + 持久化缓冲 设计方案 v2

## 一、角色生平轨迹 — 叙事 Skill 模块（非 Character 模型）

### 设计原则
- 不改动 `Character` 模型
- 生平的"读写"只在叙事环节发生
- 做成一个独立的 Skill 模块，由叙事引擎按需加载

### 数据模型

```python
class NarrativeLifeEvent(BaseModel):
    """角色生平事件——塑造性格的关键经历"""
    id: str = Field(default_factory=lambda: _unique_id("life"))
    character_id: str
    character_name: str
    timestamp: int                # 故事时间刻度（负值=故事开始前）
    title: str                    # 事件标题
    description: str              # 事件描述
    impact: str = ""              # 对性格/信念的影响
    personality_changes: list[str] = []  # 此事后新增的性格标签
    involved_chars: list[str] = []      # 涉及的其他角色
    location: str = ""            # 发生地点
    is_public: bool = True        # 是否公开信息
    chapter_ref: str = ""         # 关联的章节编号
```

### 存储方式
- 独立文件存储：`data/novel_studio/life_events/{novel_id}/{char_id}.json`
- 每个角色一个文件，内含按时间排序的 `list[NarrativeLifeEvent]`

### 调用链（叙事时注入）
```
用户请求"写新章节，张明远与严世藩对峙"
  → narrative_engine 检测涉及角色: [张明远, 严世藩]
  → CharacterLifeSkill.inject_context(char_ids)
     → 读取每个角色的生平事件
     → 生成摘要注入 prompt
  → AI 写作时自动参考生平事件驱动角色行为
```

### API
- `POST /api/novel/life_event/add` — 添加生平事件
- `POST /api/novel/life_event/list?novel_id=&char_id=` — 查看角色生平
- `call_asset_method("add_life_event", ...)` — AI 在写作过程中也可添加

---

## 二、世界事件时间线分层

### 改造现有 WorldEvent 模型

```python
class WorldEvent(BaseModel):
    """世界级大事件——含多维度索引"""
    id: str = Field(default_factory=lambda: _unique_id("wev"))
    timestamp: int
    event_type: str = ""          # 战争/天灾/政变/发现/刺杀
    title: str
    description: str
    location: str = ""            # ← 新增：地点维度
    characters_involved: list[str] = []  # ← 改造：明确角色列表
    importance: int = 3           # ← 新增：1-5 重要性分层
    chapter_ref: str = ""         # ← 新增：关联章节
    public_knowledge: bool = True
    tags: list[str] = []
```

### 新增 TimelineView 服务

```python
class TimelineView:
    """世界事件多维视图"""
    
    def by_location(self, location: str) -> list[WorldEvent]:
        """按地点查看（如苏州、京城）"""
        
    def by_type(self, event_type: str) -> list[WorldEvent]:
        """按事件类型查看（如战争、天灾）"""
        
    def by_character(self, char_id: str) -> list[WorldEvent]:
        """按涉及角色查看"""
        
    def by_importance(self, min_importance: int) -> list[WorldEvent]:
        """按重要性筛选"""
        
    def timeline(self, start: int = 0, end: int = None) -> list[WorldEvent]:
        """完整时间线"""
        
    def grouped_timeline(self) -> dict:
        """按层级返回：
        {
            "war": [...],
            "politics": [...],
            "disaster": [...],
        }
        """
```

### API
- `POST /api/novel/world/event/add` — 添加世界事件
- `GET /api/novel/world/timeline?novel_id=&by=location&value=苏州` — 多维时间线
- `GET /api/novel/world/timeline/grouped?novel_id=` — 分层时间线

---

## 三、持久化缓冲（浏览器重连）

### 现状
- ContextCenter 已持久化会话记录到 `data/context_center/detail/`
- 但结果以流式发送后未被索引，无法按 session_id 回溯拉取
- 浏览器关闭后，无法重新获取最新结果

### 新增组件

```python
class ChatResultStore:
    """持久化聊天结果存储"""
    
    def save_result(session_id, result: ToolCallingResult):
        """保存完成的结果"""
        
    def get_result(session_id) -> dict:
        """按 session_id 获取结果"""
        
    def list_pending(novel_id) -> list[dict]:
        """列出未消费的结果"""
        
    def mark_consumed(session_id):
        """标记为已消费"""
```

### 存储位置
`data/novel_studio/chat_results/{novel_id}/{session_id}.json`

### 新增 API
```python
@router.get("/chat/pending")
async def api_pending_results(novel_id: str):
    """获取未消费的聊天结果"""
    pending = result_store.list_pending(novel_id)
    return {"success": True, "pending": pending}

@router.get("/chat/result/{session_id}")
async def api_chat_result(session_id: str):
    """获取指定会话的完整结果"""
    result = result_store.get_result(session_id)
    if not result:
        return {"success": False, "error": "结果未找到"}
    return {"success": True, "result": result}
```

### 前端行为
1. 页面加载 → `GET /api/novel/chat/pending?novel_id=xxx`
2. 有 `done` 状态 → 展示"你有 X 条未阅读的回复"
3. 点击查看 → `GET /api/novel/chat/result/{session_id}`
4. 已阅读 → 自动调 `mark_consumed`

---

## 四、与现有系统的关系

| 现有组件 | 关系 |
|----------|------|
| `Character.background` | 保留为"一句话背景"，不替代生平事件 |
| `Memory`（演化引擎） | 角色视角的记忆，与全知视角的 LifeEvent 互补 |
| `WorldEvent`（现有） | 扩展为多维度索引 |
| `ContextCenter` | 提供会话持久化基础，ChatResultStore 在其上构建 |
| `_format_novel_state` | 注入新增的生平摘要 + 分层时间线 |

## 五、实现顺序

| 步骤 | 内容 |
|------|------|
| 1 | 新增 `NarrativeLifeEvent` 模型 + `CharacterLifeSkill` 存储 |
| 2 | 新增 `POST /life_event/add`, `GET /life_event/list` API |
| 3 | 扩展 `WorldEvent` 模型 + 新增 `TimelineView` 服务 |
| 4 | 新增世界事件分层 API |
| 5 | 新增 `ChatResultStore` + 持久化 API |
| 6 | prompt 注入：`_format_novel_state` 增加生平 + 时间线摘要 |
| 7 | prompt 指令：`main.md` 增加生平驱动规则 |
| 8 | 前端改造：重连时拉取 pending 结果 |
