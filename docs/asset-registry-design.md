# 动态资产表架构设计

> 2026-04-14 · 替代"统一 Tool 注册"方案

## 核心理念

**不把 App/Skill/Path 封装成 Tool**。维护一张**动态资产表**，每个资产有自己的可见范围、功能列表和详情。调模型时组装资产功能概览，提供专用 Tool 查询详细使用说明（输入输出、注意事项），通过 Tool Call 让模型决定调用。

---

## 1. 只有运行起来的才算资产

| 实体 | 静态定义 | 运行实例 |
|------|---------|---------|
| App | ❌ 不算资产 | ✅ 注册为用户资产 |
| Skill | ❌ 不算资产 | ✅ 注册到拥有者资产表 |
| Path | ❌ 不算资产 | 由中心 Skill 加载，提供执行接口 |

**静态的不算，分开存储系统和本用户的资产。**

---

## 2. 两层存储

```
AssetRegistry
├── system_assets: dict[str, Asset]    # 系统级：能看到所有用户的全部资产 + 共有资产
└── user_assets: dict[str, dict]       # 用户级：user_id → {asset_id: Asset}
```

- **系统**可以看到所有用户的所有资产 + 共有资产
- **App**只能看到自己绑定的运行 Skill
- **用户**可以看到自己的全部资产 + 共有资产

---

## 3. 注册时机

### 3.1 系统启动

```
系统启动 → 检查并初始化 → 加载已有用户资产
```

### 3.2 App 启动

```
App 启动 → 注册到用户资产表
  → 如果该用户的资产表不存在 → 创建一个
```

### 3.3 Skill 启动

```
Skill 启动 → 注册进自己拥有者的资产表
  → 拥有者可能是 user 或 app
  → 没有就创建一个
```

---

## 4. 可见性规则

### 4.1 调用时根据名字填充可用资产

```python
def get_visible_assets(caller_name: str) -> list[Asset]:
    if caller_name == "system":
        return 所有用户资产 + 共有资产
    elif caller_name.startswith("user."):
        return 该用户的全部资产 + 共有资产
    elif caller_name.startswith("app."):
        return 该 App 绑定的运行 Skill + 共有资产
```

---

## 5. LLM 交互方式

### 5.1 资产概览注入 Prompt

```
你可用的资产：
- app.novel: [写小说, 生成章节, 修改设定]
- skill.generic_writer: [生成文本, 续写]

如需了解某个资产的详细使用说明，请调用 query_asset_detail(asset_id)。
```

### 5.2 专用查询 Tool

```python
ToolDefinition(
    name="query_asset_detail",
    description="查询某个资产的详细使用说明，包括输入输出格式和注意事项",
    parameters=[
        ToolParameter("asset_id", "string", "资产ID", required=True),
    ],
)
```

模型选择资产后，交互层根据 asset_id 路由到实际执行器。

---

## 6. 固化流程（Path）

### 6.1 由中心 Skill 加载

Path 还是由中心 Skill 创建时加载，中心 Skill 提供：
- `create_execution_graph(path_key)` — 根据 key 创建执行图
- `execute_by_key(path_key, inputs)` — 按 key 执行

### 6.2 两个配套 Tool

提供给交互层调用：

```python
# Tool 1: 固化流程
solidify_workflow(app_id, path_key, steps)

# Tool 2: 按 key 调用中心 Skill
execute_path_by_key(app_id, path_key, inputs)
```

---

## 7. 完整调用链路

```
用户："帮我写一本小说"
  ↓
交互层：
  1. get_visible_assets("user.alice")
     → [app.novel, skill.generic_writer, ...]
  2. 组装资产概览注入 prompt
  3. 调模型
  ↓
模型：选择 app.novel
  ↓
交互层：
  1. query_asset_detail("app.novel") 获取详情
  2. 路由到 app.novel 的 Orchestrator
  ↓
Orchestrator (中心 Skill)：
  1. 加载的 Path → create_execution_graph(key)
  2. execute_by_key → 调用绑定 Skill
  3. 返回结果
```

---

## 8. 实施步骤

### Phase 1: 资产表核心
- `Asset` 数据模型
- `AssetRegistry` 服务（两层存储）
- `get_visible_assets(caller_name)` 可见性查询
- `register_asset()` / `unregister_asset()` 接口

### Phase 2: 启动注册
- 系统启动时检查并初始化
- App 启动时自动注册到用户资产表
- Skill 启动时注册到拥有者资产表

### Phase 3: LLM 集成
- `query_asset_detail` Tool
- Prompt 注入逻辑（资产概览）
- 交互层路由到实际执行器

### Phase 4: 固化流程
- `solidify_workflow` Tool
- `execute_path_by_key` Tool
- 中心 Skill 的 Path 加载/执行接口

### Phase 5: E2E 测试
- 几十个复杂测试覆盖全链路
- 用户交互 → App 创建 → 修改 → 执行 → 固化 → 执行
- 如有问题修复，打通链路

---

## 9. 与之前方案的区别

| 维度 | 之前（Tool 注册） | 现在（动态资产表） |
|------|------------------|-------------------|
| 注册方式 | 静态注册所有 Tool | 运行时动态注册 |
| 状态要求 | 定义即注册 | **只有运行起来才算** |
| 存储结构 | 单一注册表 | 系统/用户分开存储 |
| 可见性 | caller_ids 过滤 | 按 caller 名字查询 |
| Path 处理 | 也注册为 Tool | 由中心 Skill 管理 |
| LLM 调用 | 直接 function calling | 概览 → 查详情 → 调用 |
