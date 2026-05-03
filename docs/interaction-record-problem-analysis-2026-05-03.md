# Interaction Record Problem Analysis (2026-05-03)

## Final run status sync
This analysis was produced during the same testing cycle that later completed the full 50-scenario run.

### Final user-level E2E outcome
- total scenarios: **50**
- fully passed: **48**
- failed scenarios: **2**
- total turns: **1000**
- successful turns: **998**
- failed turns: **2**
- both failures were timeout failures (`S05`, `S15`)

This strengthens the core thesis of this document: the platform is broadly stable at transport/session level, but still shows tail-risk in execution closure and latency-sensitive flows.

## Scope
This document analyzes the exported interaction records from:
- `docs/user-123-full-interaction-2026-05-03.md`
- `docs/e2e-user-interaction-records-2026-05-03.md`

The goal is to identify recurring interaction-quality problems, quantify them where possible, and convert the findings into concrete product/system issues.

## Data basis
### E2E test-user corpus
- source files: `data/chat_logs/session_user_*.jsonl`
- session log files analyzed: **47**
- raw interaction records analyzed: **1247**
- explicit `success=false` records: **19**
- records with null/empty response: **19**

### Real-user corpus
- source file: `data/chat_logs/session_123.jsonl`
- raw interaction records analyzed: **108**
- tagged problematic records in current heuristic pass: **48**

## Statistical summary
### E2E interaction-pattern hit counts
Using response-pattern tagging over the exported test-user corpus, the following recurring patterns were observed:

| Problem tag | Count | Meaning |
|---|---:|---|
| clarification_or_capability_loop | 673 | The reply stays in explanation / need-more-info / capability narration instead of advancing the task |
| false_positive_success | 1168 | The reply is technically successful but often not user-goal-completing |
| model_or_tool_error | 46 | Tool/model/runtime errors, max-turns stops, or response-generation failures |
| context_continuation_failure | 3 | Explicit failure to continue/recover context across turns or sessions |
| execution_not_started | 0 in E2E corpus tagging | Not strongly surfaced in test-user corpus wording, but clearly present in real-user 123 record |

### E2E logs with most interaction-quality hits
Top affected session logs by aggregate pattern hits:
- `session_user_new_02.jsonl`
- `session_user_new_01.jsonl`
- `session_user_lifecycle_01.jsonl`
- `session_user_new_03.jsonl`
- `session_user_new_04.jsonl`
- `session_user_context_01.jsonl`
- `session_user_system_04.jsonl`

### E2E logs with explicit failures
Top files by `success=false` records:
- `session_user_context_04.jsonl` — 2 failures
- `session_user_lifecycle_01.jsonl` — 2 failures
- `session_user_new_05.jsonl` — 2 failures
- `session_user_security_02.jsonl` — 2 failures
- multiple additional files with 1 failure each

## Core problem categories

## 1. False-positive success: “answered” is being treated like “completed”
### Evidence
The strongest statistical signal is `false_positive_success` with **1168** hits across the test-user corpus.

Typical response shape:
- the system returns a well-formed answer
- `success=true`
- the answer contains explanation, fallback guidance, or conclusion scaffolding
- but the user goal is not actually completed

### Why this matters
Current user-level E2E scoring is too close to “HTTP/response success” and too far from “task closure success”. This inflates pass signals.

### Product impact
- test reports can look green while user intent is still unmet
- operators may believe the system is stable while real users feel nothing happened

### Required fix
Introduce separate evaluation dimensions:
1. transport success
2. response success
3. execution success
4. user-goal closure success

## 2. Clarification / capability loops dominate too many interactions
### Evidence
`clarification_or_capability_loop` appeared **673** times in the test-user corpus.

Common traits:
- the system explains what it can do
- asks for more fields even when user intent is already actionable
- delays execution in favor of more requirements elicitation

### Typical failure mode
A user asks for an app/action. The system responds with:
- architecture explanation
- capability boundaries
- missing-parameter lists
- next-step suggestions

But it does **not** create a draft, take a default path, or execute the smallest viable action.

### Product impact
- exploratory users get stuck in endless discussion
- the system feels intelligent but inert
- “start now / continue” intents do not convert into workflow progress

### Required fix
Implement draft-first execution for partially specified requests:
- infer a default app name
- infer a default template/category
- create a pending draft
- ask for refinement after execution starts

## 3. Real user 123 exposes a concrete task-closure failure chain
### Evidence from user 123
Recent messages show a clean failure storyline:
1. user asks whether app creation is possible
2. user asks to create a coding-related app
3. a runtime/model error happens once
4. after recovery, the system falls into explanation mode
5. user says “继续” / “开始执行” / “结合之前的聊天记录继续”
6. system still refuses to proceed because parameters are incomplete

### Observed symptoms
- desire is understood
- capability is acknowledged
- task is never entered into a recoverable pending state
- continuation command is treated as another clarification round

### Root cause
The system lacks a **pending task recovery model** for partially specified creation requests.

### Product impact
This is the clearest example that current interaction logic does not preserve unfinished user goals strongly enough.

## 4. Continuation and session-resume behavior is underpowered
### Evidence
The explicit `context_continuation_failure` heuristic only hit **3** times in the E2E corpus, but this is misleadingly low because the pattern is often hidden inside “successful” explanatory responses instead of explicit error wording.

In real-user `123` records, continuation failure is obvious:
- “继续” does not resume a latent task
- “结合之前的聊天记录继续” does not restore unfinished work
- the system explains session isolation instead of reconstructing user intent from available records/state

### Product impact
- multi-session trust collapses
- users feel the system is forgetful even when logs exist
- task continuity depends too much on perfect one-session completion

### Required fix
Persist resumable task state keyed by `user_id` / `session family`:
- intent class
- workflow phase
- collected parameters
- missing parameters
- next executable step

## 5. Runtime/model/tool reliability issues are present but not the main story
### Evidence
`model_or_tool_error` hit **46** times in the E2E corpus.
Examples include:
- `ModelClientError`
- 504 upstream failures
- missing tool wiring
- `[Reached max turns (6)]`

### Interpretation
These are real issues, but they are not the dominant product failure. Even after successful recovery from errors, the system often drops back into explanation rather than closing the task.

### Product impact
- reliability noise contributes to friction
- but fixing only reliability will not solve the deeper interaction-closure problem

## 6. Some test-user session logs appear to span repeated runs / reused sessions
### Evidence
Certain log files have more than 20 records, for example:
- `session_user_lifecycle_01.jsonl` has 60 records
- `session_user_new_05.jsonl` has 24 records
- several others exceed the single-scenario 20-turn expectation

### Interpretation
The system is likely appending multiple runs into the same test-user session log. This is useful for continuity testing, but it complicates one-run-one-scenario analysis.

### Product/testing impact
- makes scenario-by-scenario forensic review harder
- can hide when a later run inherits contamination from an earlier run

### Required fix
For rigorous E2E evaluation, either:
- rotate log/session ids per run, or
- add a run identifier in each log record

## Consolidated issue list
### Issue A. Pass criteria are too weak
The current notion of “success” often means “a reply was produced”, not “the user goal was completed”.

### Issue B. Draft-first execution is missing
The system asks for more detail too often instead of initiating a smallest-viable executable draft.

### Issue C. Pending task recovery is missing or weak
The system does not preserve enough structured task state to resume user goals across turns/sessions.

### Issue D. Explanation mode outruns execution mode
When under uncertainty, the assistant defaults to explanation rather than forward movement.

### Issue E. Logs are good enough to diagnose, but test evidence still needs run-level segmentation
Repeated runs merging into the same user-session log make analysis noisier than it should be.

## Recommended fixes (priority order)
### P0
1. Add `goal_closure` evaluation to user-level E2E
2. Add pending-task persistence for partially specified creation flows
3. Add draft-first app creation path

### P1
4. Add run identifiers to chat log records
5. Distinguish “explain” vs “execute” intents when user says `继续`, `开始执行`, `就做吧`
6. Add recovery logic that converts known prior user intent into the next executable step

### P2
7. Reduce overuse of “当前结论建议做轻量验证” style scaffolding for user-facing execution requests
8. Add qualitative regression review for representative scenarios even when they show `20ok/0fail`

## Final conclusion
The exported interaction documents show that AgentSystem is already fairly stable at the transport/session layer, but it still has a serious closure problem at the product-interaction layer.

In plain terms:
- the system often **responds successfully**
- but too often fails to **advance or close the user’s real task**

The user-123 record is the clearest real-world proof of this gap. The current architecture needs stronger draft execution, pending-task recovery, and goal-based evaluation before green E2E numbers can be treated as true product success.
