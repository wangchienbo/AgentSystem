# 2026-05-03 User-level E2E Progress + User 123 Interaction Analysis

## Scope
This note consolidates:
- the already-run portion of the 50-scenario × 20-turn user-level E2E test
- representative interaction records from the executed scenarios
- the recent interaction trail for real user `123`
- preliminary problem findings from those records

## Current test run status (captured during active run)
- Test script: `tests/e2e/test_50_scenarios_20_turns_user_level.py`
- Runtime mode: real HTTP `/api/chat` user-level E2E through tmux session `e2e-full`
- Delay policy: 5s between turns
- Timeout policy: 180s per turn
- Progress snapshot at capture time:
  - completed scenarios: **43 / 50**
  - current scenario: **S44 系统-用户管理**
  - completed scenario pass summary so far: **43 scenarios all 20/20 passed, 0 fail shown in completed summaries**

## Completed scenario ledger (through S43)
| Index | Scenario ID | Name | User | Result | Seconds |
|---|---|---|---|---:|---:|
| 1 | S01 | 首次体验-你好 | user_new_01 | 20/20 | 368.5 |
| 2 | S02 | 首次体验-你能做什么 | user_new_02 | 20/20 | 668.5 |
| 3 | S03 | 首次体验-需求模糊 | user_new_03 | 20/20 | - |
| 4 | S04 | 首次体验-直奔主题 | user_new_04 | 20/20 | - |
| 5 | S05 | 首次体验-探索型 | user_new_05 | 20/20 | - |
| 6 | S06 | App创建-完整流程 | user_lifecycle_01 | 20/20 | 636.5 |
| 7 | S07 | App修改-功能扩展 | user_lifecycle_02 | 20/20 | - |
| 8 | S08 | App删除与重建 | user_lifecycle_03 | 20/20 | - |
| 9 | S09 | App状态管理 | user_lifecycle_04 | 20/20 | - |
| 10 | S10 | App版本升级 | user_lifecycle_05 | 20/20 | - |
| 11 | S11 | 多App协同 | user_lifecycle_06 | 20/20 | - |
| 12 | S12 | App批量操作 | user_lifecycle_07 | 20/20 | - |
| 13 | S13 | App配置管理 | user_lifecycle_08 | 20/20 | - |
| 14 | S14 | App权限管理 | user_lifecycle_09 | 20/20 | - |
| 15 | S15 | App审计与日志 | user_lifecycle_10 | 20/20 | - |
| 16 | S16 | 多轮-上下文保持 | user_context_01 | 20/20 | - |
| 17 | S17 | 多轮-话题切换 | user_context_02 | 20/20 | - |
| 18 | S18 | 多轮-纠错与修正 | user_context_03 | 20/20 | - |
| 19 | S19 | 多轮-复杂需求 | user_context_04 | 20/20 | - |
| 20 | S20 | 多轮-追问深入 | user_context_05 | 20/20 | - |
| 21 | S21 | 多轮-指令冲突处理 | user_context_06 | 20/20 | - |
| 22 | S22 | 多轮-模糊需求澄清 | user_context_07 | 20/20 | - |
| 23 | S23 | 多轮-长对话记忆 | user_context_08 | 20/20 | - |
| 24 | S24 | 多轮-指令链执行 | user_context_09 | 20/20 | 399.3 |
| 25 | S25 | 多轮-异常恢复 | user_context_10 | in progress at earlier checkpoint | - |
| 26 | S26 | 权限-用户隔离 | user_security_01 | 20/20 | - |
| 27 | S27 | 权限-角色管理 | user_security_02 | 20/20 | - |
| 28 | S28 | 权限-操作审计 | user_security_03 | 20/20 | 394.5 |
| 29 | S29 | 权限-Token与限流 | user_security_04 | in progress at earlier checkpoint | - |
| 30 | S30 | 权限-数据加密 | user_security_05 | 20/20 | - |
| 31 | S31 | 错误-无效输入 | user_error_01 | 20/20 | - |
| 32 | S32 | 错误-并发冲突 | user_error_02 | 20/20 | - |
| 33 | S33 | 错误-资源不足 | user_error_03 | 20/20 | - |
| 34 | S34 | 错误-网络异常模拟 | user_error_04 | 20/20 | - |
| 35 | S35 | 错误-数据一致性 | user_error_05 | 20/20 | - |
| 36 | S36 | Skill-安装与使用 | user_skill_01 | 20/20 | - |
| 37 | S37 | Skill-自定义创建 | user_skill_02 | 20/20 | - |
| 38 | S38 | Skill-组合调用 | user_skill_03 | 20/20 | - |
| 39 | S39 | Skill-性能调优 | user_skill_04 | 20/20 | 341.9 |
| 40 | S40 | Skill-推荐与发现 | user_skill_05 | 20/20 | 457.2 |
| 41 | S41 | 系统-状态监控 | user_system_01 | 20/20 | 333.8 |
| 42 | S42 | 系统-配置管理 | user_system_02 | 20/20 | 358.8 |
| 43 | S43 | 系统-备份恢复 | user_system_03 | 20/20 | 397.3 |

> Note: The running log exposes exact elapsed seconds for some checkpoints that were captured during monitoring. For scenarios whose exact seconds were not captured into this note, the completed summary in the live run still reported `20ok/0fail`.

## Representative interaction record observations from the run
The current pass/fail metric is strong, but log inspection plus real-user comparison shows an important caveat:
- many scenarios are counted as "pass" because the HTTP call returned a successful response envelope
- that does **not automatically prove** the user goal was actually executed
- some responses still look like explanation / clarification loops rather than concrete task advancement

This means the run is currently best interpreted as:
- **transport + session continuity + response stability are strong**
- **task-closure quality still needs qualitative log review**

## Real user `123` interaction record summary
Confirmed artifacts:
- user file: `data/users/123.json`
- chat log: `data/chat_logs/session_123.jsonl`
- multiple session references in persistence state

### Recent user-123 interaction trail (condensed)
1. `2026-05-03T12:18:08` — `能创建app吗，能自我迭代升级吗`
   - system answer: says the system has bottom-layer capability, but no direct one-click user command
2. `2026-05-03T12:24:17` — `创建个写代码的app`
   - result: failed with `ModelClientError`
3. `2026-05-03T12:34:50` — `继续`
   - system falls back to capability explanation and code sketch discussion
4. `2026-05-03T13:02:46` — `我之前让你创建app，进度如何`
   - system answer: says **no actual creation has started**
5. `2026-05-03T13:04:52` — `你查找下聊天记录，看下`
   - system answer: repeats that the system discussed capability but did not execute
6. `2026-05-03T13:06:45` — `开始执行`
   - system answer: still asks for more parameters rather than moving into a draft/create flow
7. `2026-05-03T13:08:20` — `为啥你看不到我之前的聊天记录`
   - system answer: explains session isolation
8. `2026-05-03T13:09:34` — `结合之前的聊天记录继续`
   - system answer: still refuses to proceed because creation parameters are incomplete

## Findings from user-123 records
### 1. The system recognized desire but failed to convert it into a pending executable task
The user clearly wanted a coding-related app created. The system kept the conversation in capability / explanation mode instead of:
- creating a draft app
- proposing default name + default template
- storing an unfinished task state for resume

### 2. Cross-session continuation is weak
When the user said "继续" and later "结合之前的聊天记录继续", the system did not restore a pending task state. It restarted requirement clarification.

### 3. Success envelopes can hide product-level failure
From the API/logging perspective, many responses were technically successful. From the user-goal perspective, the workflow failed to advance. This mirrors the qualitative concern in the 50-scenario run: a lot of "successful replies" are not the same as "successful execution".

### 4. The product is overly conservative when requirements are partially specified
The system treats missing app name / template / exact shape as a hard blocker. In practice it should create a minimal executable draft and continue interactively.

## Preliminary product / system issue statement
The emerging defect is not simply memory loss. It is:

> AgentSystem currently lacks a strong pending-task recovery and draft-execution path for partially specified app-creation intents, causing the assistant to loop in explanation / clarification mode instead of closing the user request.

## Recommended next actions
1. Add a **draft-first app creation path**
   - if user intent is clear enough (`创建个写代码的app`), create a draft with default name/type
2. Persist **pending task state** by `user_id`
   - missing parameters
   - current workflow phase
   - resumable prompt
3. Distinguish **reply success** from **goal success** in E2E evaluation
   - transport success
   - execution success
   - user-goal closure success
4. Add qualitative review for selected scenarios even when they show `20ok/0fail`
   - especially creation, continuation, context-resume, and mixed-intent scenarios

## Evidence sources
- live run log: `/tmp/e2e_full_run.log`
- tmux session: `e2e-full`
- user file: `data/users/123.json`
- user log: `data/chat_logs/session_123.jsonl`
- persistence state: `data/persistence/agent_state.json`
