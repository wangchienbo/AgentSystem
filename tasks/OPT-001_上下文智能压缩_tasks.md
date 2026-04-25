# Task List: OPT-001 - 上下文智能压缩
**状态**: 🟡 等待执行 (阻塞于 max turns 限制)
**优先级**: P1
**目标**: Token -35%, 响应 -20%

## Phase 1: 设计 (Design)
- [x] T1.1: 分析当前上下文构建逻辑 (`build_session_context`)
- [ ] T1.2: 设计压缩策略 (关键信息识别 + 摘要算法)
- [ ] T1.3: 定义配置接口 (压缩档位 + 标记语法)

## Phase 2: 实现 (Implement)
- [ ] T2.1: 创建 `context-compressor` Skill (使用 `skill-creator`)
- [ ] T2.2: 集成到 `ToolCallingEngine` (对话前自动压缩)
- [ ] T2.3: 添加 `/api/config/compression` 接口

## Phase 3: 测试 (Test)
- [ ] T3.1: 单元测试 (关键信息 100% 保留验证)
- [ ] T3.2: 集成测试 (`/api/chat` 端到端)
- [ ] T3.3: 性能测试 (Token 减少比例 + 响应时间对比)

## Phase 4: 验收 (Accept)
- [ ] T4.1: 运行 `e2e_test.py --scenario=OPT-001`
- [ ] T4.2: 人工评估 (10 轮对话后回答质量评分 ≥4/5)
- [ ] T4.3: 归档任务列表 + 生成下一个需求
