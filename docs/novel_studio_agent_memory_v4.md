# Novel Studio — 角色 Agent 记忆系统设计 v4

## 核心架构

每个角色 = 一个 ContextCenter SessionNode
├── 实际上下文 (detail) = 角色经历过的完整事件记录
├── 记忆 (summary) = 压缩后的"角色记得什么"
└── 实际获取 → 取记忆 (summary)，不取原始上下文

## 已有机制（无需重复实现）

| 组件 | 位置 | 功能 |
|------|------|------|
| `ContextCenter` | `app/services/context_center.py` | session 管理 + 分层读写 |
| `ContextSummaryWorker` | `app/services/context_summary_worker.py` | 记忆压缩（summary 写入） |
| `ContextQueryService` | `app/services/context_query_service.py` | 按 session_id 读取 detail/summary |
| `DurableContextBuffer` | `app/services/durable_context_buffer.py` | 缓冲/待处理事件 |
| `ContextRetrievalService` | `app/system/gateway/context_retrieval_service.py` | 分层检索（优先 summary） |
| `get_or_create_dialogue_session` | `novel_context_builder.py:80` | 角色对话 session 注册（可复用） |

## 需要新增的组件

### 1. CharacterSessionRegistry — 注册角色 session

```python
# 复用 novel_context_builder.py 的 session 注册模式

CHARACTER_SESSION_PREFIX = "novel:char:"

def character_session_id(novel_id: str, char_id: str) -> str:
    return f"{CHARACTER_SESSION_PREFIX}{novel_id}:{char_id}"

def get_or_create_character_session(
    novel_id: str, char_id: str, char_name: str,
    context_center, novel_session_id: str,
) -> str:
    """注册每个角色为独立的 ContextCenter session"""
    
def log_character_experience(
    char_session_id: str, content: str,
    scene_name: str, participants: list[str],
    context_center,
) -> None:
    """记录角色经历到 detail 层（实际上下文）"""
```

### 2. CharacterMemoryRetriever — 跨 session 记忆检索

```python
class CharacterMemoryRetriever:
    """跨 session 检索角色记忆"""
    
    def get_memory(
        self, novel_id: str, char_id: str,
        context_center,
    ) -> str:
        """获取角色的记忆（summary 层）"""
        
    def batch_get_memories(
        self, novel_id: str, char_ids: list[str],
        context_center,
    ) -> dict[str, str]:
        """批量获取多个角色的记忆"""
        
    def retrieve_relevant(
        self, novel_id: str, query: str,
        char_ids: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """按问题匹配检索相关记忆
        
        1. 按 topic_key 筛选该小说的所有角色 session
        2. 读取每个角色的 summary（记忆）
        3. 与 query 做文本匹配 → 返回最相关的记忆条目
        """
```

### 3. SceneWriter — 场景写作时的注入

```python
# 写场景时的完整流程：

def write_scene(
    novel_id, scene_context, involved_chars, guiding_words,
):
    1. Get novel data (已有)
    2. For each involved character:
       a. Get character session
       b. Get memory (summary) via CharacterMemoryRetriever
       c. Get recent relevant detail context (当前场景相关信息)
    3. Compose prompt:
       - 大纲引导词
       - 当前场景描述
       - 在场角色列表
       - 每个角色的记忆（不是原始经历）
       - 每个角色在当前场景中的感知
    4. Call LLM
    5. After generation:
       For each involved character:
         - 追加一条 detail event（角色经历）
         - 触发 SummaryWorker（更新记忆压缩）
```

### 4. 持久化缓冲（沿用 ContextCenter 已有机制）

不需要新组件，只需要：
- **前端 API**: `GET /api/novel/chat/pending` → 查询 ContextCenter 中未消费的 session
- **前端 API**: `GET /api/novel/chat/result/{session_id}` → 按 ID 拉取结果

用 ContextCenter 的 `_durable_buffer` + `_query_service` 即可实现。

## 实现顺序

| 步 | 内容 |
|----|------|
| 1 | `novel_context_builder.py`: 新增 `character_session_id()` + `get_or_create_character_session()` |
| 2 | 新增 `CharacterMemoryRetriever` — 读取角色的 summary 记忆 |
| 3 | 新增 `log_character_experience()` — 事件后追加角色 detail 记录 |
| 4 | `api.py`: 新增 `GET /chat/pending` + `GET /chat/result/{session_id}` |
| 5 | prompt 改造：`_format_novel_state` 增加角色记忆注入 |
| 6 | main.md 增加角色 agent 行为指令 |
