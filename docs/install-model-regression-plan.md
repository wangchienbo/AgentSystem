# AgentSystem 安装模型改造前后全量用户级回归方案

## 目标

在标准安装模型改造前后，各执行一轮真实用户端到端回归，验证系统行为没有明显退化。

## 回归范围

- 50 个场景
- 每个场景连续 20 轮对话
- 每轮间隔 3 秒
- 每个场景结束后检查会话历史是否符合基础预期
- 不通过的场景进入修复闭环

## 执行脚本

主脚本：
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`

增强点：
- 保持 3 秒 delay 基线
- 场景结束后调用 `/api/history/{session_id}` 拉取对话记录
- 校验：
  - user turn 数量是否匹配 20
  - assistant reply 数量是否基本完整
  - session 是否漂移
  - 最终回复是否为空
  - 历史中是否出现明显错误标记（如 traceback / internal server error / llm request failed）

## 改造前基线

当前状态：
- [x] 历史上已完成一轮旧版 50×20 全量用户级回归（2026-05-03），结果记录于 `docs/full-50-scenario-user-e2e-result-2026-05-03.md`
- [x] 当前安装模型迁移前基线所需的 operator-sensitive 场景补强已经完成第一批（`S50` / `S41` / `S12` / `S25`）
- [ ] 尚未完成“补强后版本”的正式 pre-migration baseline 全量跑测闭环

执行方式示例：

```bash
python -m tests.e2e.test_50_scenarios_20_turns_user_level \
  --base-url http://localhost:80 \
  --delay 3 \
  --output /tmp/agentsystem_e2e_before_install_model.json
```

输出：
- 场景级通过/失败统计
- 每轮响应摘要
- 每场景结束后的 history 校验结果
- 后续建议补充：
  - `scenario_id`
  - run-level correlation id
  - operator/lifecycle-sensitive failure tags
  - 为后续 richer closure review 预留字段

## 改造后回归

标准安装模型改造完成后，再执行同一套脚本：

```bash
python -m tests.e2e.test_50_scenarios_20_turns_user_level \
  --base-url http://localhost:80 \
  --delay 3 \
  --output /tmp/agentsystem_e2e_after_install_model.json
```

## 对比重点

- 场景全通过数量
- 总轮次成功率
- session continuity
- App 生命周期链路是否退化
- 历史记录完整性是否退化
- 是否新增明显错误标记

## 验收要求

- 改造前必须先产出一份 baseline report
- 改造后必须产出一份对照 report
- 若场景结果退化，必须先修复，再进入下一波改造

## 当前直接执行队列

1. 完成旧 task list 融合后的 unresolved-items 文档收口
2. 跑增强后 operator-sensitive 场景的小规模子集验证
3. 修复如有的 harness / service-up / payload drift 问题
4. 执行补强后 pre-migration 50×20 baseline 全量回归
5. 固化 baseline evidence 到 testing / development-log / task list
