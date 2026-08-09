# Phase III Planning - Documentation Mapping, Risk Guards, and Mismatch Closure

## Goal
在北星目标 v2 收尾完成后，进入 Phase III，重点不再是单个链路补洞，而是把已有能力沉淀成可维护、可审计、可持续迭代的工程基线。

本阶段聚焦三件事：
1. 补文档映射，确保设计、实现、测试三者一致
2. 收敛风险护栏，形成明确的运行时约束与治理边界
3. 产出主链路失配清单 v1，作为后续 Phase III/IV 的统一问题入口

---

## Scope

### 1. Documentation Mapping
目标：把已经完成的 Phase H ~ Iteration 12 能力，明确映射到以下文档：
- `docs/system-relationship-map.md`
- `docs/testing.md`
- `docs/testing-detail.md`
- `docs/e2e-test-results.md`
- `docs/development-log.md`

输出要求：
- 标出每条主链路对应的模块、契约、测试文件
- 补齐 v2 场景的测试记录
- 让文档能回答“这条链路在哪里实现、怎么验证、当前状态如何”

### 2. Risk Guards Closure
目标：把当前已经实现或部分实现的风险护栏，整理成统一口径。

重点包括：
- query 上限
- tool loop 上限
- budget / quota
- observability
- contract lint
- clarification / pending context 的边界
- 长任务执行与外部中断的回归验证策略

输出要求：
- 明确哪些风险护栏已经落地
- 哪些只是设计存在、实现未闭环
- 哪些需要进入下一轮工程任务

### 3. Mismatch List v1
目标：形成一份“主链路失配清单 v1”，不再零散记录。

分类维度：
- 控制流失配
- 状态模型失配
- 模块边界失配
- 接口契约失配
- 持久化失配
- 权限失配
- 降级失配
- 可观测性失配

要求：
- 每项失配要说明：现状、影响、建议收敛方向、优先级
- 已解决问题与未解决问题分开
- 为后续 Phase III 子迭代提供统一 backlog 入口

---

## Proposed Iteration Breakdown

### Iteration 13 - Documentation Mapping Closure
- 更新 system relationship map
- 更新 testing/testing-detail/e2e-test-results
- 补 development log 中 Iteration 10~12 的记录

### Iteration 14 - Risk Guards Inventory and Gap Review
- 盘点已实现风险护栏
- 补齐缺失映射
- 输出风险护栏差距清单

### Iteration 15 - Main Path Mismatch List v1
- 汇总 Phase H ~ Iteration 12 的主链路失配项
- 结构化输出 mismatch list v1
- 给出下一阶段优先级建议

---

## Exit Criteria
Phase III 规划完成的标准：
- [ ] 有独立文档描述 Phase III 目标与分解
- [ ] task list 中新增 Iteration 13~15 入口
- [ ] 文档映射任务有明确目标文档与验收标准
- [ ] 风险护栏任务有清晰盘点维度
- [ ] 主链路失配清单任务有固定模板与输出格式

---

## Notes
- Phase III 以“收敛与沉淀”为主，不优先做新的功能扩张
- 若在文档映射或 mismatch review 中发现高优先级缺陷，可插入修复型迭代
- Iteration 9 中关于多意图拆解、并发控制、GC 机制的遗留问题，后续应并入 mismatch list，而不是继续散落在 task notes 中
