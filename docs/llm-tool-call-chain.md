# LLM Tool Call 完整链路设计

## 核心原则

1. **精确正则直调，模糊走 LLM** — 100% 确定的意图（你好/帮助/系统状态）走正则，其余走 LLM tool call
2. **资产自注册** — 每个资产启动时往自己的表里插入，能被探测到
3. **权限自注册** — 用户权限表同理
4. **LLM tool call 是主链路** — 资产表融入 tool call 验证

## 模糊正则匹配开关

```yaml
interpreter:
  # false（默认）: 只有 100% 精确匹配走正则，其余走 LLM
  # true: 尽可能走正则，减少 LLM 调用
  fuzzy_regex_match: false
```

### 精确匹配定义（永远走正则，不经过 LLM）
- `^(你好|嗨|hi|hello|hey|哈喽)$` — 纯问候
- `^(帮助|help|教教我|怎么用)$` — 纯帮助请求
- `^(系统状态|状态|运行情况)$` — 纯状态查询

### 模糊匹配（默认走 LLM）
- "启动 小说" — 需要查资产表确认"小说"是否存在
- "帮我建一个监控 App" — 需要 LLM 理解需求细节
- "把 XXX 关掉" — 需要查资产表确认 XXX
- 任何包含 App 名称但需要动态查表的

## 完整调用链路

```
用户消息
    ↓
┌──────────────────────────────────────────────┐
│  LightBrainInterpreter                        │
│  1. 精确正则匹配（永远走）→ 直调              │
│  2. 模糊正则匹配（开关控制）                  │
│     - OFF: 跳过 → 走 LLM                      │
│     - ON:  尝试匹配 → 匹配则直调              │
│  3. LLM 意图分析（模糊路径的主入口）           │
│     输入: 用户消息 + 资产概览                   │
│     输出: tool_call 结构                       │
└──────────────┬───────────────────────────────┘
               │
               ├─ 精确匹配 → 直调 handler
               │
               └─ LLM tool_call →
                    ↓
┌──────────────────────────────────────────────┐
│  AssetRegistry.get_visible_assets(caller_id)   │
│  → 过滤出调用者可见的资产                       │
│  → 确认 tool 在可见资产中                       │
└──────────────┬───────────────────────────────┘
               │ 资产存在
               ↓
┌──────────────────────────────────────────────┐
│  PermissionRegistry.check_permission()         │
│  → user role level vs asset owner_role_level   │
│  → 允许 / 拒绝                                 │
└──────────────┬───────────────────────────────┘
               │ 允许
               ↓
┌──────────────────────────────────────────────┐
│  RPC Router                                   │
│  → 路由到对应执行器                            │
│  → 结构化输入输出                              │
│  → 返回结果                                    │
└──────────────────────────────────────────────┘
```

## 资产自注册

### 注册关系表

| 资产类型 | 启动时注册到 | 触发时机 |
|---------|------------|---------|
| App | `system_assets` 或 `user_assets` | lifecycle `start` → `running` |
| Skill | 所属 owner 的资产表 | Skill 实例化时 |
| Tool | `system_assets` | 系统启动时 |
| Path | 所属 App 的资产表 | App 加载 Path 时 |
| 用户 | `permission_registry` | 用户首次访问时 |

### 注册时机

在 `AppLifecycleService.transition()` 中注入钩子：

```python
def transition(self, app_instance_id, event, reason=""):
    result = self._do_transition(app_instance_id, event, reason)
    
    # 启动成功 → 注册资产
    if event == "start" and result.current_status == "running":
        self._on_asset_start(app_instance_id)
    
    # 停止/失败 → 注销资产
    elif event in ("stop", "fail"):
        self._on_asset_stop(app_instance_id)
    
    return result
```

## 用户权限表

```python
class PermissionRegistry:
    """用户权限自注册表"""
    def ensure_user(user_id, default_role="user")   # 首次访问自注册
    def update_role(user_id, new_role)               # 角色升级
    def check_permission(user_id, required_level)    # 权限检查
```

## LLM Tool Call 协议

### 输入给 LLM

```
你是一个意图解析器。用户说了一句话，请解析出他想要调用的工具。

可用资产概览：
- app.小说 (running): 小说创作工具
- app.监控 (stopped): 系统监控工具
- path.create_app: 创建新 App 的固化流程

用户消息："帮我写一本小说"

请以 JSON 格式返回：
{
    "tool": "app.小说",
    "function": "write_chapter",
    "params": {"genre": "武侠"},
    "confidence": 0.9
}
```

### 网关处理 tool_call

```python
async def execute_tool_call(tool_call: dict, user_id: str):
    # 1. 资产表查询
    asset = asset_registry.get_asset(tool_call["tool"])
    
    # 2. 权限校验
    if not permission_registry.check_permission(user_id, asset):
        return "权限不足"
    
    # 3. RPC 路由
    result = await rpc_router.execute(
        asset_id=asset.asset_id,
        function=tool_call["function"],
        inputs=tool_call["params"],
    )
    
    return result
```

## 修改清单

| 文件 | 内容 |
|------|------|
| `light_brain_interpreter.py` | 分层意图识别：精确直调 / 模糊走LLM |
| `light_brain_gateway.py` | tool_call 路由：资产表 → 权限 → RPC |
| `lifecycle.py` | 注入资产注册/注销钩子 |
| `services/permission_registry.py` | 新建：用户权限自注册表 |
