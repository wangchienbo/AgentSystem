# 外模型评审层（External Model Review Layer）

## 目标

不替换系统主模型，而是在统一调用边界内新增一个受控外模型层，用于：

- 方案评审
- 代码 review
- 风险扫描
- 对抗式审查

## 原则

1. 业务层不直接乱调外模型
2. Gateway / Skill / App 通过统一层请求评审
3. 外模型只提供评审信号，不直接夺取主控决策权
4. 模型选择仍走 `ModelRouter`

## 当前最小实现

已新增：
- `app/services/external_model_review.py`

提供：
- `ExternalModelReviewService.review(action, prompt, context, model_preference)`

并在 `runtime.py` 中注入：
- `external_model_review`

## 当前路由

在 `ModelRouter` 默认 caller routes 中新增：
- `external_review -> balanced`
- `external_review_strong -> strong`

后续若把 qwen3.6-plus 接入 model pool，可直接把：
- `external_review`
- `external_review_strong`

改指向 qwen 路由，而不影响主模型。

## 与三件套的关系

- `task-list-executor` 负责持续推进
- `design-review-orchestrator` 负责决定何时做评审
- `skill-discovery-review` 负责先查复用
- `external_model_review` 负责真正调用外模型做评审

## 后续待补

1. 将 `external_model_review` 暴露为系统 tool / worker
2. 让 `design-review-orchestrator` 在关键分叉时自动调用该层
3. 加入 qwen3.6-plus 到 model pool
4. 增加方案评审 / code review 的端到端验证

## 当前接入状态

当前最小接入闭环已打通：

- `runtime.py` 已注册 `external_review_plan` / `external_review_code` ToolDefinition
- `MasterControl` 已可将上述 operation 路由到 `external_review` worker
- `ExternalModelReviewWorker` 已按主控调用约定返回 `status/message/data` 结构

这意味着系统现在已经具备“通过主控统一入口触发方案评审和代码评审”的执行基础。后续要做的是把它接进更高层的自动流程编排，而不是再单独造一套评审执行机制。
