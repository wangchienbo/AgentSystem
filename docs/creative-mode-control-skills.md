# 创作模式稳定执行三件套接入说明

## 目标

把以下三类控制型 skill 纳入系统资产，并在创作模式下默认可用：

- `skill.task-list-executor`
- `skill.design-review-orchestrator`
- `skill.skill-discovery-review`

## 接入原则

1. 创作模式不直接进入发散式自由生成。
2. 默认先形成任务清单，再持续推进执行。
3. 关键方案分叉先评审，再继续实现。
4. 新建能力前先查复用，降低不必要发明。
5. 稳定性优先于频繁改路。

## 当前接入内容

### 1. 资产化
已在 `source/` 中登记三件套：
- `source/skill.task-list-executor/manifest.json`
- `source/skill.design-review-orchestrator/manifest.json`
- `source/skill.skill-discovery-review/manifest.json`

### 2. 创作模式识别
在 Gateway `create_app` 链路中，当 `app_type` 属于：
- `novel`
- `diary`
- `blog`
- `music`
- `drawing`

或名称包含：
- 小说
- 创作
- 写作
- 博客
- 日记
- 绘图
- 音乐

则判定为 `creative_mode=True`。

### 3. 创作模式下默认注入约束
创作模式创建 App 时，会把以下约束传入创建链路：
- 创作模式默认启用 `task-list-executor`
- 关键方案分叉调用 `design-review-orchestrator`
- 新能力创建前先调用 `skill-discovery-review`
- 保证稳定性优先，避免频繁切换实现路径

## 预期效果

创作类 App 在进入实施时，默认遵循：

1. 列清单
2. 自动推进
3. 分叉评审
4. 先查复用
5. 稳定收口

而不是每一步都重新发散。

## 后续待补

1. 将三件套真正注册进运行时 `SystemCatalog / ToolRegistry`
2. 在 App 创建后绑定为可见控制 skill
3. 增加创作模式端到端验收测试
4. 统一与 caller_ids / service discovery 的可见性边界
