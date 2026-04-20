# Phase H E2E Test Results

## Record Template
- 场景:
- 输入:
- 主链路:
- 预期:
- 实际结果:
- 失配分类:
- 修复动作:
- 当前结论:
- 遗留问题:

---

## H2 Discovery Slice Checkpoint
- 场景: 运行态核心资产注册与发现工具接线
- 输入: Runtime bootstrap loads core services, Gateway exposes runtime asset tools
- 主链路: `build_runtime -> RuntimeCenter register core assets -> ToolRegistry expose list/query/call asset tools -> LightBrainGateway handle runtime asset tool intents`
- 预期:
  - 核心服务注册为运行态资产
  - Gateway 能承接 `list_assets / query_asset_info / call_asset_method`
  - AssetToolExecutor 基于 RuntimeCenter 返回运行态信息
- 实际结果:
  - 已注册 `master_control / config_center / runtime_center / model_router / tool_calling_engine / light_brain_gateway`
  - Gateway 已挂接运行态资产工具处理器
  - AssetToolExecutor 已从 system catalog 切换为 RuntimeCenter
  - `call_asset_method` 已可真实映射到 `model_router.resolve_model / config_center.get_config / gateway.list_assets`
  - 兼容加载旧 runtime data，旧 `running` 状态与缺失字段可转为新契约
- 失配分类:
  - 部分旧资产查询仍保留 static catalog 回退语义
  - interpreter 对 runtime asset intent 仍是基础 regex 级别
- 修复动作:
  - 增加正式 runtime asset tools
  - 在 Gateway 默认工具表中暴露 runtime asset intents
  - RuntimeCenter 增加 method mapping 与 legacy runtime entry 迁移加载
  - 统一 `query_asset_detail` 优先走 runtime contract
- 当前结论:
  - H2.2/H2.3 已从设计态进入可调用骨架态，并完成首批真实方法映射
  - 运行态资产发现, 查询, 调用三段链路已打通
- 遗留问题:
  - `call_asset_method` 仍只覆盖首批核心服务映射，尚未扩展到更广 worker/app 面
  - runtime asset intent 的解释策略仍较粗，需要后续做更稳的 tool-aware 解析
  - 还缺少正式测试文件覆盖本轮 Phase H 新链路
