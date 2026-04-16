# Phase N.2：代码物理解耦（按进程/域划分）

> 设计时间：2026-04-16
> 状态：方案设计，待实施

---

## 一、目标

把 `app/services/` 下 100+ 个文件，按**职责域**重排到第二层目录。
不改变任何代码，只做**物理移动 + import 路径更新**。

**原则：**
- 一个职责域 = 一个文件夹
- 文件夹内文件数尽量均衡（10-30 个）
- 避免循环依赖（先画依赖图，再决定边界）
- 迁移后所有 import 路径自动批量替换

---

## 二、目标结构

```
app/
├── __init__.py
│
├── system/                         # system 包 = 主进程
│   ├── __init__.py
│   │
│   ├── master/                     # 主控核心
│   │   ├── __init__.py
│   │   ├── master_control.py       # MasterControl 入口
│   │   ├── tool_registry.py        # Tool 注册 + caller_ids
│   │   ├── package_manager.py      # 7-Tool 包管理
│   │   ├── execution_monitor.py
│   │   └── intent_router.py
│   │
│   ├── workers/                    # 6 个 Workers
│   │   ├── __init__.py
│   │   ├── app_mgmt.py             # AppManagementWorker
│   │   ├── user_mgr.py             # UserManager
│   │   ├── skill_mgr.py            # SkillManager
│   │   ├── refinement.py           # RefinementWorker
│   │   ├── file.py                 # FileWorker
│   │   └── suggestion.py           # SuggestionWorker
│   │
│   ├── runtime/                    # 运行时协调
│   │   ├── __init__.py
│   │   ├── lifecycle.py            # AppLifecycleService
│   │   ├── scheduler.py            # SchedulerService
│   │   ├── runtime_host.py         # AppRuntimeHostService
│   │   ├── app_registry.py         # AppRegistryService
│   │   ├── app_context_store.py
│   │   ├── app_data_store.py
│   │   ├── app_config_service.py
│   │   ├── app_catalog.py
│   │   └── config_center.py        # ConfigCenterService
│   │
│   ├── catalog/                    # 资产层（Phase N 核心）
│   │   ├── __init__.py
│   │   ├── asset_center.py         # build/install/rollback
│   │   ├── runtime_center.py       # register/heartbeat/unregister  ← 新建
│   │   ├── system_catalog.py       # 可见性过滤
│   │   ├── asset_registry.py
│   │   ├── resource_center.py
│   │   └── app_profile_resolver.py
│   │
│   ├── gateway/                    # 交互层
│   │   ├── __init__.py
│   │   ├── light_brain_gateway.py  # 入口 handler
│   │   ├── light_brain_interpreter.py
│   │   ├── llm_responder.py
│   │   ├── interaction_gateway.py
│   │   └── context_retrieval_service.py
│   │
│   └── bootstrap/
│       ├── __init__.py
│       ├── runtime.py              # 主入口（入口文件，不动）
│       ├── catalog.py
│       └── skills.py
│
├── orchestration/                  # 编排层
│   ├── __init__.py
│   ├── app_orchestrator.py
│   ├── core_orchestrator.py
│   ├── meta_app/                   # MetaAppCreationOrchestrator
│   │   ├── __init__.py
│   │   ├── bootstrap.py
│   │   └── orchestrator.py        # 升级后含 Step 4-7
│   ├── app_designer/              # Path B
│   │   ├── __init__.py
│   │   ├── architect.py
│   │   ├── intent_analyzer.py
│   │   └── orchestrator.py
│   ├── dynamic_path/              # 动态路径组合
│   │   ├── __init__.py
│   │   └── dynamic_path_composer.py
│   ├── pipeline_executor.py
│   ├── workflow_executor.py
│   ├── app_refinement.py
│   └── requirement_router.py
│
├── skills/                         # 系统 Skills
│   ├── __init__.py
│   ├── system_skills/             # system.* 内置 skills
│   │   ├── __init__.py
│   │   ├── maoxuan/
│   │   ├── context.py
│   │   ├── memory.py
│   │   ├── permission.py
│   │   ├── state_audit.py
│   │   ├── app_config.py
│   │   └── maoxuan.py
│   ├── universal_skill.py
│   ├── skill_factory.py
│   ├── skill_control.py
│   ├── skill_registry_service.py
│   ├── skill_installer.py
│   ├── skill_packager.py
│   ├── skill_asset_service.py
│   ├── skill_suggestion.py
│   ├── skill_authoring.py
│   ├── skill_validation.py
│   ├── skill_manifest_validator.py
│   ├── skill_config_center.py
│   ├── skill_meta_service.py
│   ├── skill_rpc.py
│   ├── skill_runtime.py
│   ├── executable_skill_adapter.py
│   ├── generated_skill_assets.py
│   ├── generated_skill_asset_store.py
│   ├── generated_callable_materializer.py
│   ├── skill_diagnostics.py
│   ├── skill_risk_policy.py
│   ├── skill_retry_advisor.py
│   ├── schema_registry.py
│   └── system_skill_service.py
│
├── ai/                             # AI/LLM 能力层
│   ├── __init__.py
│   ├── model_router.py
│   ├── internal_model_router.py
│   ├── model_client.py
│   ├── model_config_loader.py
│   ├── model_preference_inferrer.py
│   ├── model_self_refiner.py
│   ├── model_skill_suggester.py
│   ├── tool_call_executor.py
│   ├── tool_calling_engine.py
│   ├── core_skill_toolchain.py
│   ├── supervisor.py
│   ├── multi_action_llm_worker.py
│   └── skill_invoker.py
│
├── persistence/                   # 持久化层
│   ├── __init__.py
│   ├── persistence_service.py
│   ├── context_compaction.py
│   ├── experience_store.py
│   ├── context_skill_service.py
│   ├── context_retrieval_service.py
│   ├── memory_skill.py
│   ├── upgrade_service.py
│   ├── rollback_service.py
│   ├── upgrade_log_service.py
│   ├── persistence_health_service.py
│   ├── app_binding.py
│   ├── runtime_state_store.py
│   └── command_queue.py
│
├── governance/                    # 治理/审计层
│   ├── __init__.py
│   ├── log_center.py
│   ├── log_evidence_service.py
│   ├── telemetry_service.py
│   ├── policy_authority.py
│   ├── policy_guard.py
│   ├── permission_registry.py
│   ├── collection_policy_service.py
│   ├── auth_service.py
│   ├── log_evidence.py
│   ├── evaluation_summary_service.py
│   ├── practice_review.py
│   ├── proposal_review.py
│   ├── priority_analysis.py
│   ├── risk_governance_skill.py
│   ├── event_bus.py
│   └── demonstration_extractor.py
│
├── refinement/                   # 精炼层
│   ├── __init__.py
│   ├── refinement_loop.py
│   ├── refinement_memory.py
│   ├── refinement_rollout.py
│   ├── refinement_failure_analysis.py
│   ├── self_refinement.py
│   ├── requirement_blueprint_builder.py
│   ├── requirement_clarifier.py
│   ├── app_refinement_orchestrator.py
│   ├── blueprint_compare.py
│   ├── blueprint_validation.py
│   └── refinement_loop.py
│
├── core/                          # G.1/G.2 基础设施（不变）
│   ├── __init__.py
│   ├── message_bus.py
│   ├── worker_manager.py
│   ├── simple_worker.py
│   ├── skill_worker.py
│   ├── protocol_adapter.py
│   ├── gateway_integration.py
│   ├── gateway_orchestrator_bridge.py
│   ├── json_store.py
│   ├── trace.py
│   ├── model_health.py
│   └── errors.py
│
├── models/                        # 数据模型（不变）
│   └── [所有 *.py 文件，保持原位]
│
└── api/                           # HTTP 层（不变）
    └── [所有 *.py 文件，保持原位]
```

---

## 三、迁移顺序（按依赖倒序）

**原则：被依赖多的先迁移**

```
Step 1:  core/              ← 最底层，先固化
Step 2:  models/            ← 数据结构，不依赖任何服务
Step 3:  system/catalog/    ← AssetCenter, RuntimeCenter（被最多模块引用）
Step 4:  system/runtime/    ← lifecycle, config_center, app_registry
Step 5:  system/master/     ← MasterControl, tool_registry
Step 6:  system/workers/    ← 6 个 Workers（依赖 master + runtime）
Step 7:  system/gateway/    ← 交互层
Step 8:  skills/            ← skill 相关
Step 9:  ai/                ← model 相关
Step 10: orchestration/     ← orchestrator（依赖最多）
Step 11: persistence/       ← 持久化
Step 12: governance/         ← 审计/日志
Step 13: refinement/        ← 精炼
Step 14: api/               ← HTTP 层
Step 15: system/bootstrap/  ← runtime.py 最后迁入
```

---

## 四、迁移脚本设计

每个 Step 执行：

```bash
# 1. 移动文件（物理重排）
mv app/services/asset_center.py app/system/catalog/asset_center.py

# 2. 批量替换 import（所有引用该文件的模块）
grep -rl "from app.services.asset_center import" --include="*.py" \
  | xargs sed -i 's|from app\.services\.asset_center import|from app.system.catalog.asset_center import|g'

# 3. 验证编译
python3 -c "from app.system.catalog.asset_center import AssetCenter; print('OK')"

# 4. 运行测试
python3 -m pytest tests/ -x -q
```

---

## 五、__init__.py 暴露设计

每个模块的 `__init__.py` 暴露公共接口，内部模块名不暴露：

```python
# app/system/catalog/__init__.py
from app.system.catalog.asset_center import AssetCenter
from app.system.catalog.runtime_center import RuntimeCenter  # 新建后暴露
from app.system.catalog.system_catalog import SystemCatalog

__all__ = ["AssetCenter", "RuntimeCenter", "SystemCatalog"]
```

引用方使用：
```python
from app.system.catalog import AssetCenter, RuntimeCenter  # ✅ 推荐
from app.system.catalog.asset_center import AssetCenter   # ✅ 也可
```

---

## 六、迁移后效果

| 改造前 | 改造后 |
|--------|--------|
| `app/services/` 100+ 文件平铺 | 按域划分的 14 个子包 |
| import 路径 `from app.services.lifecycle import` | `from app.system.runtime.lifecycle import` |
| 找不到哪个文件属于哪个域 | 一眼看出模块归属 |
| 改一个文件要翻很久 | 修改前先看包名就知道改哪里 |
| 难以拆出独立进程 | 包边界 = 进程边界 |

---

## 七、风险控制

- **风险 1**：循环依赖 → 解法：画依赖图后决定边界，允许部分模块跨包 import
- **风险 2**：import 路径批量替换出错 → 解法：每个 Step 移动后立即编译验证
- **风险 3**：git history 丢失 → 解法：使用 `git mv` 而非 `mv`，保留 history
- **风险 4**：迁移期间系统不可用 → 解法：切换到分支开发，合入前 E2E 测试

---

## 八、开始迁移

```bash
# Step 1: core/ 迁移（最快，确认流程）
git mv app/services/skill_worker.py app/core/skill_worker.py
# ... 14 个文件

# 验证
python3 -c "from app.core.skill_worker import SkillWorker; print('OK')"
```

要从 `app/core/` 开始吗？我可以先跑通整个迁移流程，然后逐域完成。
