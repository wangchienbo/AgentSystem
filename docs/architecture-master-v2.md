# AgentSystem 架构总方案 v2.0

> 整合时间：2026-04-16
> 状态：方案设计，包含已完成改造点标注

---

## 一、核心架构原则

### 1.1 分层结构

```
┌─────────────────────────────────────────┐
│           交互层（Gateway）               │  ← 接收请求、意图路由
│  ┌───────────────────────────────────┐  │
│  │  MasterControl Handler            │  │  ← master_execute 统一入口
│  │  轻量级 LLM 意图分类               │  │
│  └───────────────────────────────────┘  │
└────────────────┬────────────────────────┘
                 │ operation + params
                 ▼
┌─────────────────────────────────────────┐
│          主控层（MasterControl）          │  ← 唯一系统操作入口
│  ┌───────────────────────────────────┐  │
│  │  统一 Tool 注册（caller_ids 过滤）   │  │
│  │  权限校验（owner_role）             │  │
│  │  审计日志 + 建议生成                │  │
│  │  6 个 Workers 调度                 │  │
│  └───────────────────────────────────┘  │
└────────────────┬────────────────────────┘
                 │ worker 执行
                 ▼
┌─────────────────────────────────────────┐
│         资产层（Asset + Runtime）        │
│  ┌────────────┐    ┌────────────────┐  │
│  │ AssetCenter│    │ RuntimeCenter   │  │
│  │ 静态位置    │    │ 动态运行状态    │  │
│  │ build/install   │ register/     │  │
│  │ rollback    │    │ heartbeat     │  │
│  └────────────┘    └────────────────┘  │
│  ┌────────────┐    ┌────────────────┐  │
│  │SystemCatalog│   │ PackageManager  │  │
│  │ 可见性过滤  │    │ 7-Tool 包管理  │  │
│  └────────────┘    └────────────────┘  │
└────────────────┬────────────────────────┘
                 │ 进程启动
                 ▼
┌─────────────────────────────────────────┐
│         进程层（进程自注册模型）          │
│  每个 App = 独立进程（未来）            │
│  启动时自注册，退出时自注销              │
└─────────────────────────────────────────┘
```

### 1.2 核心原则

1. **调用权收口**：Tool Call 层统一调用，Skill 不直连 LLM
2. **进程自注册**：每个 App 独立完整包，启动自注册，退出自注销
3. **版本号驱动变更**：source/ → build/ → installed/，版本唯一信号
4. **system 强约束**：system 包不可卸载，升级需特殊权限
5. **权限分层**：进程 token < user < admin < root

---

## 二、完整改造清单

### 2.1 已完成 ✅

| # | 改造点 | 文件 | 验证 |
|---|--------|------|------|
| 1 | MasterControl 入口 + 权限 + 审计 | `master_control.py` | ✅ |
| 2 | 6 Workers 实现 | `workers/` 下 6 个文件 | ✅ |
| 3 | PackageManager 7-Tool | `package_manager.py` | ✅ |
| 4 | ToolRegistry caller_ids 权限过滤 | `tool_registry.py` | ✅ |
| 5 | SkillBlueprint owner_role 字段 | `skill_blueprint.py` | ✅ |
| 6 | AssetCenter build/install/rollback/uninstall | `asset_center.py` | ✅ |
| 7 | SystemCatalog 资产自注册 + 可见性过滤 | `system_catalog.py` | ✅ |
| 8 | Gateway master_execute Handler | `light_brain_gateway.py` | ✅ |
| 9 | MasterControl 注入 Gateway + Runtime | `runtime.py` | ✅ |
| 10 | MetaAppOrchestrator 链路改造 | `meta_app/orchestrator.py` | ✅ |
| 11 | AppManagementWorker 完整 10 operation | `workers/app_management_worker.py` | ✅ |
| 12 | SystemCatalog lifecycle hooks | `runtime.py` | ✅ |
| 13 | AppBlueprint source_path 字段 | `app_blueprint.py` | ✅ |

### 2.2 未完成 ❌

| # | 改造点 | 优先级 | 依赖 |
|---|--------|--------|------|
| 1 | **RuntimeCenter**（进程运行态） | P0 | — |
| 2 | **start_asset / stop_asset / health Tool** | P0 | RuntimeCenter |
| 3 | **App 升级流程**（version+1 → build → 资产中心 → 启动） | P0 | Tool 1+2 |
| 4 | **App 卸载流程**（stop → unregister → uninstall） | P0 | Tool 1+2 |
| 5 | **App 进程隔离**（每个 App 独立子进程） | P1 | Tool 1 |
| 6 | **App 入口自注册注入**（启动时调用 register） | P1 | Tool 5 |
| 7 | **Skill 包独立打包** | P2 | AssetCenter |
| 8 | **Shared 包多版本隔离** | P2 | AssetCenter |
| 9 | **权限细化**（进程只写自己信息） | P2 | Tool 1 |
| 10 | **build 时依赖解析** | P2 | Tool 7 |

---

## 三、RuntimeCenter 设计

### 3.1 数据模型

```python
@dataclass
class RuntimeEntry:
    asset_id: str
    version: str
    pid: int
    endpoint: str
    status: str  # running | stopped | crashed | unknown
    started_at: str  # ISO timestamp
    last_heartbeat: str  # ISO timestamp
    owner: str

@dataclass
class RuntimeCenter:
    _entries: dict[str, RuntimeEntry]  # key = asset_id
```

### 3.2 接口

```python
class RuntimeCenter:
    def register(self, asset_id, version, pid, endpoint, owner) -> RuntimeEntry
    def heartbeat(self, asset_id) -> bool  # pid 匹配才更新
    def unregister(self, asset_id) -> bool
    def get(self, asset_id) -> RuntimeEntry | None
    def list_running(self) -> list[RuntimeEntry]
    def list_all(self) -> list[RuntimeEntry]
    def mark_crashed(self, asset_id) -> None  # 心跳超时检测
    def get_uptime(self, asset_id) -> str  # human readable
```

### 3.3 心跳超时机制

```
进程注册 → started_at = now
主循环每 30s 检查：
  if now - last_heartbeat > 90s:
      mark_crashed(asset_id)
      → MasterControl 收到状态变化 → 处理（重启或标记）
```

---

## 四、start_asset / stop_asset Tool 设计

### 4.1 Tool 定义

```python
START_ASSET_TOOL = ToolDefinition(
    name="start_asset",
    description="启动一个已安装的 App 资产",
    parameters=[
        Param(name="asset_id", type="string", required=True),
        Param(name="version", type="string", required=False),  # None = 最新
    ],
    returns={"status": "running", "endpoint": "", "pid": 0},
    caller_ids=[],  # admin+ 可调用
)

STOP_ASSET_TOOL = ToolDefinition(
    name="stop_asset",
    description="停止一个运行中的 App 进程",
    parameters=[
        Param(name="asset_id", type="string", required=True),
    ],
    returns={"status": "stopped"},
    caller_ids=[],  # admin+ 可调用
)

HEALTH_CHECK_TOOL = ToolDefinition(
    name="health_check_asset",
    description="查询 App 进程健康状态",
    parameters=[
        Param(name="asset_id", type="string", required=True),
    ],
    returns={"status": "ok|running|stopped|error|crashed", "uptime": "", "pid": 0},
)
```

### 4.2 执行逻辑

```
start_asset(asset_id, version=None):
  1. 查 RuntimeCenter — 如果已 running，直接返回
  2. 查 AssetCenter — 定位 installed/{asset_id}/{version}/ 或最新
  3. 查 manifest.json — 获取 entry + 命令
  4. subprocess.Popen — 启动进程
  5. 等待进程就绪（ping endpoint）
  6. RuntimeCenter.register — 注册到运行资源中心
  7. 返回 {status: running, endpoint, pid}

stop_asset(asset_id):
  1. 查 RuntimeCenter — 获取 pid
  2. os.kill(pid, SIGTERM) — 发送停止信号
  3. 等待退出（超时 10s 则 SIGKILL）
  4. RuntimeCenter.unregister — 从运行资源中心移除
  5. 返回 {status: stopped}
```

### 4.3 system 包硬约束

```python
def _check_system_forbidden(asset_id: str) -> None:
    if asset_id.startswith("system.") or asset_id == "system":
        raise PermissionError("system 包禁止 start/stop")
```

---

## 五、App 完整生命周期

### 5.1 新建 App（用户触发）

```
用户: "创建一个小说 App"
  │
  ├─ MetaAppOrchestrator
  │    1. LLM 设计 → AppControlSkillResult
  │    2. 创建 subordinate skills
  │    3. 组装 AppBlueprint
  │    4. 写入 source/app.novel/manifest.json
  │    5. AssetCenter.build(app.novel)
  │    6. AssetCenter.install(app.novel)
  │    7. SystemCatalog.register(entry)
  │
  ├─ MasterControl.start_asset("app.novel")
  │    → subprocess.Popen → 启动进程
  │    → 进程自注册 RuntimeCenter.register
  │
  └─ 完成：app.novel 运行中
```

### 5.2 升级 App

```
用户: "升级小说 App 到 v1.2.0"
  │
  ├─ AssetCenter.build("app.novel")     → build/app.novel/v1.2.0/
  ├─ AssetCenter.install("app.novel")   → installed/app.novel/v1.2.0/
  ├─ AssetCenter.update_version          → 写入资产中心
  │
  ├─ MasterControl.stop_asset("app.novel")
  │    → 停止旧实例（RuntimeCenter.unregister）
  │
  ├─ MasterControl.start_asset("app.novel", version="v1.2.0")
  │    → 启动新实例（RuntimeCenter.register）
  │
  └─ 完成：旧实例已停止，新实例运行中
```

### 5.3 回退 App

```
用户: "回退小说 App 到 v1.1.0"
  │
  ├─ MasterControl.stop_asset("app.novel")
  ├─ MasterControl.start_asset("app.novel", version="v1.1.0")
  └─ 完成
```

### 5.4 卸载 App

```
用户: "卸载小说 App"
  │
  ├─ MasterControl.stop_asset("app.novel")
  ├─ RuntimeCenter.unregister
  ├─ AssetCenter.uninstall("app.novel")
  ├─ 删除 installed/app.novel/（所有版本）
  ├─ SystemCatalog.unregister("app.novel")
  └─ 完成
```

---

## 六、进程隔离（未来扩展）

**当前**：所有 App 运行在主进程内（单进程共享）
**目标**：每个 App = 独立子进程

```
主进程（Master/Gateway）
  ├─ App NOVEL     subprocess.Popen  → PID 12345
  ├─ App QA        subprocess.Popen  → PID 12346
  └─ App SEARCH    subprocess.Popen  → PID 12347
```

**启动隔离时需注入的代码**：
- 进程入口加入 `RuntimeCenter.register` 调用
- 进程退出时 `atexit.register(RuntimeCenter.unregister)`
- 心跳线程定期 `RuntimeCenter.heartbeat`

---

## 七、实现顺序

```
Phase 1: RuntimeCenter                    ← 基础设施（新建文件）
Phase 2: start_asset/stop_asset/health Tool  ← Worker 新增 operation
Phase 3: runtime.py 注入 RuntimeCenter    ← MasterControl 调用新 Tool
Phase 4: App 入口自注册                    ← 进程启动时 register
Phase 5: App 升级流程端到端                ← 串联全链路
Phase 6: App 卸载流程端到端
Phase 7: 权限细化
Phase 8: 进程隔离（可选，未来）
```

---

## 八、数据存储

```
data/
  asset_registry.json     ← AssetCenter（静态位置）
  runtime_center.json     ← RuntimeCenter（动态运行态）  ← 新建
  system_catalog.json     ← SystemCatalog（资产可见性）
  build_history.json      ← AssetCenter build 记录
```

---

## 九、关键约束

| 约束 | 说明 |
|------|------|
| system.* 包禁止 start/stop | 硬编码校验 |
| 进程只能写自己信息 | caller_ids + pid 双重校验 |
| 版本号唯一 | 同一 asset_id + version 不重复 build |
| 升级不覆盖旧实例 | 每个版本独立 installed/ 目录 |
| 心跳超时 90s | 超时标记 crashed，MasterControl 处理 |
