# Full 50-Scenario User-level E2E Result (2026-05-03)

## Scope
This document records the completed full run of:
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`
- target: real HTTP `/api/chat`
- mode: user-level E2E
- size: **50 scenarios × 20 turns = 1000 turns**

## Final headline result
- total scenarios: **50**
- scenarios fully passed: **48**
- scenarios with failure: **2**
- total turns: **1000**
- successful turns: **998**
- failed turns: **2**
- network/service errors: **2**
- pass rate: **99.8%**
- total runtime: **21873.4s** (~6.08h)
- average turn latency: **21.9s**

## Final conclusion
This run is operationally strong and almost fully green, but it is **not** a clean 100% pass. The remaining two failures are both long-tail timeout failures rather than broad workflow collapse.

## Failed scenarios
### 1. S05 首次体验-探索型
- user: `user_new_05`
- result: **19 ok / 1 fail**
- failed turn: **Turn 4**
- message: `做一个计算器App吧`
- error: `Timeout after 180.0s`
- interpretation:
  - creation-oriented requests still occasionally block long enough to exhaust the per-turn timeout
  - this is consistent with the broader interaction analysis showing that creation flows can drift into heavy clarification / reasoning / tool routing before closure

### 2. S15 App审计与日志
- user: `user_lifecycle_10`
- result: **19 ok / 1 fail**
- failed turn: **Turn 6**
- message: `有多少次请求记录？`
- error: `Timeout after 180.0s`
- interpretation:
  - query-style follow-up on logs/audit state can still trigger an expensive path
  - likely falls into slow retrieval / summarization / tool-selection latency rather than a deterministic read model response

## What the failures imply
The failures do **not** suggest that the whole user-level architecture is unstable. Instead, they point to two specific risk zones:

1. **creation-path latency spikes**
   - app creation / first-definition flows can take too long
   - should move faster via draft-first defaults and more bounded orchestration

2. **audit/query-path latency spikes**
   - observational/log-count questions should hit a cheap read model
   - should not depend on a slow high-latency reasoning path

## Relationship to the interaction-record analysis
This full-run result matches the earlier qualitative findings:
- session continuity and transport are strong
- raw response stability is strong
- but some flows still overthink or overroute instead of taking the shortest executable path
- success metrics are high, yet tail-latency and task-closure issues still exist in specific categories

## Recommended next fixes
### P0
1. Add targeted timeout regression cases for:
   - app creation draft path
   - audit/log-count query path
2. Add a fast-path for simple operational read queries
3. Reduce orchestration depth for partially specified creation intents

### P1
4. Add per-intent latency buckets to the report
5. Mark timeout failures separately from semantic failures in docs/testing dashboards
6. Re-run S05 and S15 individually after fixes

## Evidence
- final report: `/tmp/agentsystem_e2e_user_level_report.json`
- run log: `/tmp/e2e_full_run.log`
- test script: `tests/e2e/test_50_scenarios_20_turns_user_level.py`

## Suggested follow-up
After implementing the latency fixes, the next clean validation step should be:
1. rerun S05 alone
2. rerun S15 alone
3. rerun the full 50-scenario suite
4. compare pass rate + timeout count + average latency
