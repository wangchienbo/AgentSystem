# 系统资产自注册与持久化方案

## 核心原则

**一切皆表，自注册，持久化。**

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    系统清单 (System Catalog)              │
│  data/system_catalog.json                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  App 注册表   │  │  Skill 注册表 │  │  Path 注册表  │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
│         │                 │                 │            │
│         └─────────────────┼─────────────────┘            │
│                           │                              │
│                    持久化到硬盘                            │
└───────────────────────────┼──────────────────────────────┘
                            │
┌───────────────────────────┼──────────────────────────────┐
│                    资产自注册流程                          │
│                                                            │
│  App 启动 → 调用 catalog.register()                        │
│    ├─ 写入自己的详细信息                                    │
│    ├─ 声明有哪些接口（functions）                           │
│    ├─ 声明输入输出 schema                                   │
│    └─ 声明 owner、visibility、权限要求                     │
│                                                            │
│  Skill 启动 → 同理                                          │
│                                                            │
│  用户首次访问 → user_service.ensure_user()                  │
│    ├─ 写入 data/users/{user_id}.json                       │
│    └─ 默认 role=user                                       │
└─────────────────────────────────────────────────────────┘
```

## 1. 系统清单 (SystemCatalog)

### 持久化位置
- `data/system_catalog.json` — 系统级 App/Skill/Path 注册表
- `data/users/{user_id}.json` — 用户级 App 注册表

### 每个资产注册的信息

```json
{
  "asset_id": "app.novel",
  "asset_type": "app",
  "owner_id": "user.alice",
  "name": "小说创作",
  "description": "帮助用户创作小说的 App",
  "status": "running",
  "visibility": "public",
  
  "interfaces": {
    "write_chapter": {
      "description": "写一个章节",
      "input_schema": {
        "genre": {"type": "string", "required": true},
        "chapter_title": {"type": "string", "required": false}
      },
      "output_schema": {
        "content": {"type": "string"},
        "word_count": {"type": "integer"}
      }
    }
  },
  
  "required_role_level": 0,
  "created_at": "2026-04-14T05:00:00Z",
  "updated_at": "2026-04-14T05:00:00Z",
  "metadata": {
    "app_instance_id": "novel_001",
    "skill_ids": ["skill.generic_writer", "skill.novel_planner"]
  }
}
```

## 2. 资产自注册流程

### App 启动时

```python
# 在 AppLifecycleService.transition() 中
def transition(self, app_instance_id, event, reason=""):
    result = self._do_transition(app_instance_id, event, reason)
    
    if event == "start" and result.current_status == "running":
        # 自注册到系统清单
        self._catalog.register_from_app(app_instance_id)
    
    elif event in ("stop", "fail"):
        self._catalog.unregister(app_instance_id)
    
    return result
```

### 注册时写入的信息

每个 App/Skill 启动时调用：

```python
catalog.register(
    asset_id="app.novel",
    asset_type="app",
    owner_id="user.alice",
    name="小说创作",
    description="...",
    interfaces={...},  # 接口定义
    required_role_level=0,
    visibility="public",
    metadata={...},
)
```

## 3. 用户表

已有 `user_service.py`，需要接入：

```python
# 在 gateway 入口
user = user_service.ensure_user(user_id, default_role="user")
# 首次访问自动创建并持久化到 data/users/{user_id}.json
```

## 4. LLM Tool Call 链路

```
用户消息
    ↓
意图识别
    ├── 精确正则 → 直调
    └── 模糊 → LLM 意图分析
                    ↓
            catalog.get_visible_assets(user_id)
                    ↓
            权限校验 (user role vs required_role_level)
                    ↓
            RPC 路由 → 执行
```

## 修改清单

| 文件 | 内容 |
|------|------|
| `app/services/system_catalog.py` | **新建**：系统清单服务 |
| `app/models/asset.py` | 增强：加 interfaces、持久化 |
| `app/services/lifecycle.py` | 注入资产注册钩子 |
| `app/services/user_service.py` | 加 ensure_user() |
| `app/services/light_brain_interpreter.py` | 接入 catalog 到 LLM |
| `app/services/light_brain_gateway.py` | 接入权限校验 |
| `data/system_catalog.json` | **新建**：持久化文件 |
