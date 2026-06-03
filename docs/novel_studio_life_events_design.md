# Novel Studio — 角色生平轨迹 + 持久化缓冲 设计方案

## 一、角色生平轨迹 (LifeEvent)

### 数据模型新增

```python
class LifeEvent(BaseModel):
    """角色生平事件——塑造性格的关键经历"""
    id: str
    timestamp: int                # 故事时间刻度（负值=故事开始前）
    title: str                    # 事件标题
    description: str              # 事件描述
    impact: str = ""              # 对性格/信念的影响
    personality_changes: list[str] = []  # 此事后新增的性格标签
    involved_chars: list[str] = []      # 涉及的其他角色
    location: str = ""            # 发生地点
    is_public: bool = True        # 是否公开信息
    chapter_ref: str = ""         # 关联的章节号（故事开始后的）

# Character 新增字段：
class Character:
    ...
    life_events: list[LifeEvent] = []  # 生平大事记（时间排序）
```

### API 新增
- `add_life_event(novel_id, char_id, title, description, impact, ...)`
- `get_character_timeline(novel_id, char_id)` → 返回角色生平时间线

---

## 二、场景叙事融入生平

### 修改 prompt 指令
在 `prompts/novel_studio/main.md` 中新增规则：
- 写章节时，必须检查涉及角色的 `life_events`，**优先用生平事件驱动角色行为**
- 角色决策应与其经历一致（如"曾被背叛的角色不会轻信他人"）

### 数据注入
`_format_novel_state()` 中增加 `life_events` 的摘要注入，给 LLM 明确的事件参考。

---

## 三、持久化缓冲系统

### 现状
- ContextCenter 已有 `session_id → records` 的上下文管理
- 浏览器通过 SSE (`/api/novel/chat/stream`) 获取流式结果
- **问题**: 浏览器断开后，后台继续运行的结果无法被重新拉取

### 方案

```
Browser ──SSE──→ Backend (FastAPI)
    │                    │
    │ 断开连接            │ 继续执行
    │                    │ 结果存入 `ResultStore`
    │                    │
    ├── 重新连接 ────────→
    │  GET /api/novel/chat/result/<session_id>
    │  ←── 返回完整结果
```

#### 新增组件
```python
class PendingResult(BaseModel):
    session_id: str
    status: str         # processing | done | error
    final_text: str = ""
    tool_calls: list = []
    token_usage: dict = {}
    created_at: str
    updated_at: str

class ResultStore:
    """持久化结果存储（文件/内存双写）"""
    
    def save(session_id, result): ...
    def get(session_id) -> PendingResult: ...
    def list_recent() -> list: ...
```

#### 前端行为
1. 进入页面 → 调用 `GET /api/novel/chat/pending?user_id=xxx` 拉取未消费的结果
2. 如果有 `done` 状态的结果 → 展示给用户
3. 如果有 `processing` 状态 → 显示"后台仍在处理中..."

---

## 四、实现顺序

| 步骤 | 内容 | 影响范围 |
|------|------|----------|
| 1 | 新增 `LifeEvent` 模型 + `Character.life_events` | models.py |
| 2 | 新增 `add_life_event` API + storage 方法 | api.py, storage.py |
| 3 | 新增 `get_character_timeline` API | api.py |
| 4 | prompt 注入：`_format_novel_state` 增加生平摘要 | api.py |
| 5 | prompt 指令：在 `main.md` 增加生平驱动规则 | prompts/ |
| 6 | 新增 `ResultStore` 持久化结果存储 | storage.py |
| 7 | 新增 `GET /result/<session_id>` + `GET /pending` API | api.py |
| 8 | 前端改造：进入页面拉取未消费结果 | studio UI |
