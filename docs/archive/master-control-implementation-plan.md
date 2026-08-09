# 主控重构完整方案（统一 Tool 注册 + 递归 Path 架构）

> 设计时间: 2026-04-14
> 状态: 方案定稿，待实施
> 核心: App/Skill/Path 全部注册为 Tool，通过 caller_ids 控制权限

---

## 一、核心概念

### 资产模型

```
所有可调用资产 → 统一注册为 "Tool"

├── App（运行实例）
│     定位: "做好的菜"，有中心 Skill + 从属 Skill
│     状态: 有状态，支持多轮对话
│     示例: app.novel, app.monitor
│
├── Path（固化流程）
│     定位: "菜谱"，YAML 定义的技能链
│     分类:
│       ├── App 内部 Path: 每个 Path 代表 App 的一个功能
│       │     示例: path.novel_write（属于 app.novel）
│       │           path.character_design（属于 app.novel）
│       │
│       └── 系统级 Path: 用户要求的固化流程
│             示例: path.create_app, path.list_apps
│
├── Skill（能力模块）
│     定位: "干活的"，执行具体任务
│     示例: skill.conversation, skill.novel_writer
│
└── Tool（工具函数）
      定位: 内置工具
      示例: tool.create_app, tool.start_app
```

### 关系

```
app.novel（小说 App）
  ├── 中心模块: 小说创作流程配置
  ├── 中心 Skill: NovelControl（决策者）
  ├── 从属 Skill:
  │     ├── skill.conversation
  │     ├── skill.novel_writer
  │     └── skill.character_manager
  │
  └── Path（固化流程 = App 的功能）
        ├── path.novel_write      → 写小说
        ├── path.character_design → 角色设计
        └── path.continue_write   → 续写

path.create_app（系统级固化流程）
  ├── step 1: skill.requirement_analyzer
  ├── step 2: skill.skill_suggester
  ├── step 3: skill.app_assembler
  └── step 4: skill.app_installer
```

---

## 二、统一 Tool 注册模型

### ToolDefinition 结构

```python
class ToolDefinition:
    # ── 身份 ──────────────────────────────
    name: str              # "app.novel" / "path.novel_write" / "skill.conversation"
    description: str       # 能做什么
    
    # ── 参数 ──────────────────────────────
    parameters: list[ToolParameter]
    
    # ── 分类 ──────────────────────────────
    category: str          # "app" / "path" / "skill" / "tool"
    
    # ── 权限（关键！）─────────────────────
    caller_ids: list[str]  # 能被哪些资产 ID 调用
                            # 支持通配符: "app.*" 匹配所有 App
    
    # ── 关联到具体资产 ────────────────────
    app_id: str | None     # 如果是 app category
    path_id: str | None    # 如果是 path category
    skill_id: str | None   # 如果是 skill category
    
    # ── 元信息 ────────────────────────────
    priority: int          # LLM 推荐优先级
    owner_role: str        # 所有者角色（system / admin / user）
```

### 注册示例

```python
# 1. App 注册为 Tool
registry.register(ToolDefinition(
    name="app.novel",
    description="小说 App（帮助用户创作小说，支持多轮对话）",
    category="app",
    app_id="app.novel",
    caller_ids=["app.interaction", "user.*"],  # 交互层和所有用户能调用
    owner_role="user",
))

# 2. App 内部 Path 注册为 Tool（只有所属 App 能调用）
registry.register(ToolDefinition(
    name="path.novel_write",
    description="写小说的固化流程",
    category="path",
    path_id="novel_write",
    app_id="app.novel",  # 属于哪个 App
    caller_ids=["app.novel"],  # 只有小说 App 自己能调用
))

# 3. 系统级 Path 注册为 Tool
registry.register(ToolDefinition(
    name="path.create_app",
    description="创建 App 的固化流程（分析需求 → 推荐 skill → 组装 → 安装）",
    category="path",
    path_id="create_app",
    caller_ids=["app.interaction"],  # 只有交互层能调用
    owner_role="system",
))

# 4. Skill 注册为 Tool
registry.register(ToolDefinition(
    name="skill.conversation",
    description="对话管理（管理用户会话和上下文）",
    category="skill",
    skill_id="skill.conversation",
    caller_ids=["app.novel", "app.customer_service", "app.*"],  # 所有 App 能调用
    owner_role="system",
))
```

---

## 三、权限控制：谁能调用谁

### caller_ids 匹配规则

```python
def can_call(caller_id: str, allowed_callers: list[str]) -> bool:
    for pattern in allowed_callers:
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            if caller_id.startswith(prefix):
                return True
        elif caller_id == pattern:
            return True
    return False
```

### 权限矩阵

```
调用者           →  被调用者                  →  是否允许
─────────────────────────────────────────────────────
app.interaction  →  app.novel                 →  ✅ (caller_ids 包含)
app.interaction  →  app.monitor               →  ✅ (caller_ids 包含)
app.interaction  →  path.create_app           →  ✅ (caller_ids 包含)
app.interaction  →  path.novel_write          →  ❌ (caller_ids 只有 app.novel)
app.interaction  →  system.master.*           →  ❌ (系统内部)

app.novel        →  skill.conversation        →  ✅ (caller_ids 包含 app.*)
app.novel        →  path.novel_write          →  ✅ (caller_ids 包含 app.novel)
app.novel        →  app.monitor               →  ❌ (App 之间不直接调用)
app.novel        →  system.master.*           →  ❌ (App 不能调用主控)

system.master    →  app.*                    →  ✅ (主控可以管理所有 App)
system.master    →  skill.*                  →  ✅ (主控可以调用所有 Skill)
```

---

## 四、LLM Tool Call 流程

### 核心：LLM 只看到自己被允许的 Tool

```
用户: "我想写小说"
  ↓
交互层判断:
  - 简单事情（打招呼、格式化）→ 自己处理
  - 需要外部能力 → 走 Tool Call
  ↓
交互层请求 LLM:
  "用户说'我想写小说'，请选择合适的 Tool"
  
  传给 LLM 的 Tool 列表（过滤后）:
  [
      { name: "app.novel", description: "小说 App", category: "app" },
      { name: "path.write_novel", description: "一次性写小说", category: "path" },
      # 不会传给 LLM:
      # - app.monitor（caller_ids 不匹配交互层）
      # - skill.novel_writer（caller_ids 是 app.novel，不是交互层）
      # - path.create_app（caller_ids 是 admin+，当前用户不是）
  ]
  ↓
LLM 返回:
  { tool: "app.novel", params: { "user_id": "user_123" } }
  ↓
交互层执行:
  1. 检查权限: caller_id="app.interaction" 是否在 app.novel 的 caller_ids 中 → ✅
  2. 调用主控: POST /master/execute { tool: "app.novel", ... }
  3. 主控路由: category="app" → 执行 app.novel
```

### App 内部 Tool Call（递归）

```
app.novel 的中心 Skill (NovelControl) 收到请求:
  "用户想写一本小说"
  ↓
NovelControl 请求 LLM:
  "需要执行写小说流程，请选择 Tool"
  
  传给 LLM 的 Tool 列表（过滤后）:
  [
      { name: "path.novel_write", description: "写小说的固化流程" },
      { name: "skill.conversation", description: "对话管理" },
      { name: "skill.novel_writer", description: "小说生成" },
      # 不会传给 LLM:
      # - app.novel（自己不能调用自己）
      # - system.master.*（App 不能调用主控）
  ]
  ↓
LLM 返回:
  { tool: "path.novel_write", params: { "genre": "武侠" } }
  ↓
NovelControl 执行:
  1. 检查权限: caller_id="app.novel" 是否在 path.novel_write 的 caller_ids 中 → ✅
  2. 加载 Path YAML: data/paths/novel_write.yaml
  3. 按 steps 执行 skill 链
```

---

## 五、统一调用入口

### MasterControl.execute

```python
class MasterControl:
    async def execute(self, tool_name: str, params: dict, caller_id: str) -> dict:
        """统一执行入口"""
        
        # 1. 获取 Tool 定义
        tool = registry.get_tool(tool_name)
        if not tool:
            raise ToolNotFoundError(tool_name)
        
        # 2. 检查 caller 是否有权限
        if not can_call(caller_id, tool.caller_ids):
            raise PermissionDenied(f"{caller_id} 不能调用 {tool_name}")
        
        # 3. 根据 category 路由到不同执行器
        if tool.category == "app":
            return await self._execute_app(tool.app_id, params)
        elif tool.category == "path":
            return await self._execute_path(tool.path_id, params)
        elif tool.category == "skill":
            return await self._execute_skill(tool.skill_id, params)
        elif tool.category == "tool":
            return await self._execute_native_tool(tool_name, params)
```

---

## 六、交互层流程

### handle_user_message

```python
class UserInteractionLayer:
    async def handle_user_message(self, message: str, user_id: str):
        # 1. 先自己处理简单事情
        if self._can_handle_locally(message):
            return self._handle_locally(message)
        
        # 2. 获取 caller_id 被允许的 Tool 列表
        caller_id = "app.interaction"
        available_tools = registry.get_tools_for_caller(caller_id)
        
        # 3. LLM 选择 Tool
        result = self._llm.select_tool(message, available_tools)
        
        # 4. 执行 Tool（通过主控）
        return await master.execute(
            tool_name=result["tool"],
            params=result["params"],
            caller_id=caller_id
        )
```

---

## 七、完整调用链路示例

### 场景 1：用户创建 App

```
用户: "帮我创建一个小说 App"
  ↓
交互层 LLM 选择: path.create_app
  ↓
master.execute("path.create_app", { app_type: "小说" }, "app.interaction")
  ↓
主控加载 path.create_app YAML:
  step 1: skill.requirement_analyzer → 分析需求
  step 2: skill.skill_suggester → 推荐 skill
  step 3: skill.app_assembler → 组装 blueprint
  step 4: skill.app_installer → 安装 App
  ↓
返回: app.novel 创建完成
```

### 场景 2：用户使用 App

```
用户: "我想写小说"
  ↓
交互层 LLM 选择: app.novel
  ↓
master.execute("app.novel", { action: "open" }, "app.interaction")
  ↓
app.novel 的中心 Skill (NovelControl) 收到请求:
  "用户想写小说"
  ↓
NovelControl LLM 选择: path.novel_write
  ↓
加载 path.novel_write YAML:
  step 1: skill.conversation → 初始化对话
  step 2: skill.novel_writer → 生成内容
  step 3: skill.memory → 保存上下文
  ↓
返回: 小说内容
```

### 场景 3：App 内部调用 Skill

```
path.novel_write 执行中:
  step 2 需要调用 skill.novel_writer
  ↓
skill.novel_writer 需要 LLM 生成内容:
  ↓
skill.novel_writer LLM 选择: system.router.call_model
  ↓
system.router.call_model → 调用远程模型 API
  ↓
返回: 生成的内容
```

**每一层都遵循：发现 → 分析 → 匹配 → 调用**

---

## 八、修改清单

### 需要新建的文件

| 文件 | 说明 |
|------|------|
| `app/models/system_master.py` | 主控身份声明 |
| `app/api/system_master.py` | 主控 API 端点 |
| `app/services/workers/app_management_worker.py` | App 管理 Worker |
| `app/services/workers/user_manager.py` | 用户管理 Worker |
| `app/services/workers/skill_manager.py` | Skill 管理 Worker |
| `app/services/workers/refinement_worker.py` | 精炼 Worker |
| `app/services/workers/file_worker.py` | 文件管理 Worker |
| `app/services/suggestion_worker.py` | 系统建议 Worker |
| `app/models/master_capability.py` | 能力清单数据结构 |
| `app/models/app_creation_declaration.py` | App 创建完整声明 |

### 需要修改的文件

| 文件 | 改动说明 |
|------|---------|
| `app/services/tool_registry.py` | 增加 caller_ids 字段，支持权限过滤 |
| `app/bootstrap/runtime.py` | 注册主控 Blueprint，实例化 Worker，注册 Path 为 Tool |
| `app/services/light_brain_gateway.py` | 改为调用 /master/* API，不再直接调用服务 |
| `app/models/skill_blueprint.py` | 添加 owner_role 字段 |
| `app/services/skill_control.py` | 权限检查逻辑 |
| `app/services/app_installer.py` | 创建时验证完整性，注册 App 为 Tool |
| `app/services/path_store.py` | Path 加载时自动注册为 Tool |
| `app/services/app_orchestrator.py` | Path 执行时检查权限 |

---

## 九、一句话总结

> **所有可调用资产（App/Skill/Path）统一注册为 Tool，声明"谁能调用我"。LLM 需要 Tool Call 时，只看到自己被允许的 Tool 列表。每一层都遵循"发现 → 分析 → 匹配 → 调用"的递归循环。**
