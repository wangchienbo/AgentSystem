# 主控能力声明（Master Capability Declaration）

> 设计时间: 2026-04-14
> 状态: 方案设计
> 目的: 让交互层清楚知道主控是什么、能做什么、什么时候该调用

---

## 1. 主控身份声明

```
┌──────────────────────────────────────────────────────────────┐
│                  系统主控（Master Control）                    │
│                                                              │
│  我是谁: system.master                                        │
│  我是什么: 操作系统内核 = 全局唯一系统级 App                   │
│  我的职责: 权限审批、系统管理、基础设施                        │
│  我不做: 不直接跟用户对话，不理解用户意图                      │
│  我的入口: /api/v1/system/master/*                            │
│  我的状态: 始终运行，不可删除，不可修改（只能自我升级）        │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. 主控能力清单（Capability Manifest）

交互层启动时自动获取这个清单，就知道什么时候该调用主控：

```json
{
  "master": {
    "id": "system.master",
    "name": "系统主控",
    "version": "1.0.0",
    "status": "running",
    
    "capabilities": {
      "auth": {
        "description": "权限审批 — 所有操作的唯一权限决策者",
        "endpoint": "POST /api/v1/system/master/auth/request",
        "when_to_call": "任何修改操作前，先请求授权",
        "example": {
          "user_id": "user_123",
          "operation": "modify_app",
          "target": "app_novel",
          "params": { "add": "对话功能" }
        }
      },
      
      "execute": {
        "description": "执行操作 — 统一执行入口",
        "endpoint": "POST /api/v1/system/master/execute",
        "when_to_call": "授权通过后，执行实际操作",
        "operations": [
          "create_app", "modify_app", "delete_app",
          "create_skill", "modify_skill", "delete_skill",
          "system_upgrade", "system_rollback"
        ]
      },
      
      "suggest": {
        "description": "系统建议 — 评估用户建议的可行性",
        "endpoint": "POST /api/v1/system/master/suggest",
        "when_to_call": "用户提出系统级改进建议时",
        "example": {
          "user_id": "user_123",
          "category": "intent_understanding",
          "problem": "意图识别不准确",
          "expectation": "应该更准确理解用户需求"
        }
      },
      
      "query": {
        "description": "系统查询 — 查询系统状态/日志/架构",
        "endpoint": "GET /api/v1/system/master/query",
        "when_to_call": "用户想查看系统信息时",
        "query_types": ["system_logs", "app_list", "skill_list", "user_list", "system_status"]
      },
      
      "skill_manage": {
        "description": "Skill 管理 — 创建/修改/注册 Skill",
        "endpoint": "POST /api/v1/system/master/execute",
        "when_to_call": "需要创建或修改 Skill 时（仅 admin+）",
        "operations": ["create_skill", "modify_skill", "delete_skill", "register_skill"]
      },
      
      "app_manage": {
        "description": "App 管理 — 注册 App、生命周期管理",
        "endpoint": "POST /api/v1/system/master/execute",
        "when_to_call": "需要注册或删除 App 时",
        "operations": ["create_app", "modify_app", "delete_app", "start_app", "stop_app"]
      },
      
      "system_upgrade": {
        "description": "系统升级 — 执行系统级升级/回滚",
        "endpoint": "POST /api/v1/system/master/execute",
        "when_to_call": "需要升级系统组件时（仅 root）",
        "operations": ["system_upgrade", "system_rollback"]
      },
      
      "log_record": {
        "description": "日志记录 — 记录所有操作日志",
        "endpoint": "POST /api/v1/system/master/log",
        "when_to_call": "任何操作执行后，自动记录",
        "auto_called": true
      }
    },
    
    "permission_rules": {
      "app_modify": "用户 role_level >= App owner_role_level",
      "skill_modify": "用户 role_level >= Skill owner_role_level",
      "system_upgrade": "仅 root",
      "skill_create": "仅 admin+",
      "app_create": "所有用户（仅复用已有 skill）"
    }
  }
}
```

---

## 3. 交互层调用规则（写死在代码中）

交互层看到能力清单后，就知道什么时候该调用主控：

```python
class InteractionLayerRules:
    """交互层调用主控的规则（写死）"""
    
    # ── 必须调用主控的操作 ─────────────────────────────
    MUST_CALL_MASTER = [
        "create_app",      # 创建 App → 先请求授权
        "modify_app",      # 修改 App → 先请求授权
        "delete_app",      # 删除 App → 先请求授权
        "create_skill",    # 创建 Skill → 先请求授权
        "modify_skill",    # 修改 Skill → 先请求授权
        "system_upgrade",  # 系统升级 → 直接调用
        "query_system",    # 查询系统 → 直接调用
        "suggest_system",  # 系统建议 → 直接调用
    ]
    
    # ── 不需要调用主控的操作 ───────────────────────────
    NO_NEED_CALL_MASTER = [
        "greet",           # 打招呼 → 自己处理
        "list_apps",       # 列出 App → 自己处理（缓存）
        "query_help",      # 查看帮助 → 自己处理
        "format_output",   # 格式化输出 → 自己处理
        "manage_session",  # 会话管理 → 自己处理
        "understand_intent", # 意图理解 → 自己处理
    ]
    
    # ── 调用流程 ─────────────────────────────────────
    CALL_FLOW = {
        # 修改类操作
        "modify": [
            "1. 交互层理解意图",
            "2. POST /master/auth/request → 请求授权",
            "3. 主控返回 granted/denied",
            "4. 如果 granted → POST /master/execute → 执行",
            "5. 主控返回结果 → 交互层格式化展示",
        ],
        # 查询类操作
        "query": [
            "1. 交互层理解意图",
            "2. GET /master/query → 查询",
            "3. 主控返回原始数据",
            "4. 交互层格式化展示",
        ],
        # 建议类操作
        "suggest": [
            "1. 交互层收集用户意见",
            "2. POST /master/suggest → 提交建议",
            "3. 主控评估可行性，返回方案",
            "4. 交互层解释方案，和用户讨论",
            "5. 用户确认 → POST /master/suggest/approve → 执行",
        ],
    }
```

---

## 4. 当前系统 vs 目标系统

### 当前系统（混乱）

```
交互层（LightBrainGateway）
  ├── 直接调用 _app_registry.list_entries()
  ├── 直接调用 _lifecycle.get_instance()
  ├── 直接调用 _runtime_host.start()
  ├── 直接调用 _meta_app_orchestrator.create_app_through_meta_app()
  ├── 直接调用 _app_refinement_orchestrator.refine_closure()
  ├── ... 19+ 个直接调用
  └── 完全不知道"主控"是什么
```

### 目标系统（清晰）

```
交互层（UserInteractionLayer）
  ├── 理解意图 → 意图理解（自己处理）
  ├── 管理会话 → 会话管理（自己处理）
  ├── 格式化输出 → 展示结果（自己处理）
  │
  └── 需要操作资源时：
      ├── POST /master/auth/request → 请求授权
      ├── POST /master/execute → 执行操作
      ├── GET /master/query → 查询系统
      └── POST /master/suggest → 提交建议

主控（MasterControl）
  ├── auth.request → 权限审批
  ├── execute → 执行操作（调用从属 Skill）
  ├── query → 系统查询
  ├── suggest → 系统建议评估
  └── log.record → 日志记录
```

---

## 5. 交互层如何发现主控能力

### 5.1 启动时自动获取

```python
class UserInteractionLayer:
    def __init__(self):
        # 启动时自动获取主控能力清单
        self._master_capabilities = self._discover_master()
    
    def _discover_master(self) -> dict:
        """发现主控能力（启动时自动调用）"""
        try:
            response = requests.get("http://localhost:8000/api/v1/system/master/capabilities")
            return response.json()
        except Exception:
            # 如果主控不可用，使用默认能力清单
            return DEFAULT_MASTER_CAPABILITIES
    
    def should_call_master(self, operation: str) -> bool:
        """判断是否需要调用主控"""
        return operation in self._master_capabilities.get("must_call", [])
    
    async def call_master(self, operation: str, params: dict):
        """调用主控 API"""
        capability = self._master_capabilities["capabilities"].get(operation)
        if not capability:
            raise MasterUnavailableError(f"主控不支持操作: {operation}")
        
        # 调用主控 API
        response = requests.post(
            f"http://localhost:8000{capability['endpoint']}",
            json={"user_id": self._user_id, **params}
        )
        return response.json()
```

### 5.2 能力清单缓存

交互层启动时获取一次能力清单，缓存在内存中。如果主控升级了能力清单，交互层下次启动时自动更新。

---

## 6. 总结

**交互层怎么知道要不要调用主控？**

1. **主控对外声明能力清单**（Capability Manifest）
2. **交互层启动时自动获取**能力清单
3. **调用规则写死**：修改类操作必须先请求授权，查询类操作直接调用
4. **能力清单包含**：每个能力的描述、端点、什么时候该调用、示例

**类比操作系统：**
- 主控 = 内核，提供系统调用表（syscall table）
- 交互层 = Shell，通过系统调用表知道内核能做什么
- 用户 = 人，通过 Shell 跟系统交互

**一句话总结：**
> 主控声明"我能做什么"，交互层看到清单就知道"什么时候该调用主控"。
