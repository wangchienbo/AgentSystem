# Standard Install Model Transition - Detailed Task List

## 0. Goal

Convert AgentSystem from repo-coupled runtime into a standard install model with:
- source repo only for development, packaging, install orchestration, and operator entrypoints
- real runtime code separated from source repo
- real runtime assets/data/state/logs separated from source repo
- stronger CLI control plane before the migration
- full real-user baseline regression before and after the migration

---

## 1. Phase 0 - Close existing unfinished task list first

### 1.1 Inventory unfinished current work
Status: [x] first merged unresolved-items pass landed
- inspected current Phase Q / follow-up task docs
- inspected recent commits after Wave 5/6/7 completion notes
- identified items marked complete in docs but still partially implemented or weakly validated
- identified open gaps in change execution summary / acceptance plan / validation map chain
- produced a compact unresolved-items list and merged it into this task list

Current merged unresolved items from older task lists and follow-up waves:
- [ ] close remaining Phase R Wave 5 open slice items:
  - derive changed-file intent from actual repo inspection plus task-list hints more directly
  - reduce reliance on the single-work-item fallback for multi-command acceptance evidence mapping
  - decide whether compact changed-file/result summaries should surface into a lighter operator-facing read model
- [ ] verify there is no remaining HTTP compatibility drift between `/api/chat`, `/api/action`, gateway action payloads, and service-up consumers
- [ ] close any remaining startup path cleanup/output cleanup deltas discovered while stabilizing long-run baseline execution
- [ ] confirm no runnable path still has an implicit repo-root dependency once installed-runtime migration starts
- [ ] explicitly track older closure-upgrade items that were conceptually merged but not yet fully closed:
  - query/read fast-path for cheap count/status/list requests
  - closure scoring split beyond raw response success
  - run isolation metadata for long E2E analysis (`run_id`, `scenario_id`)

### 1.2 Close code-level loose ends
Status: [ ] pending
- finish any partially landed workflow/action/acceptance chain improvements
- close any pending HTTP compatibility deltas
- close any remaining path-cleanup/output-cleanup items discovered during service startup
- verify no repo-root hard dependency remains in runnable code paths

### 1.3 Close validation and docs for old work
Status: [ ] pending
- run focused regression for remaining unfinished old tasks
- update testing docs if any old task lacked evidence
- update development log with final closure notes for these items
- commit and push the old-work closure before starting install-model work

**Exit criteria**
- existing task list has no ambiguous unfinished items
- current workstream is in a clean committed state
- old task closure has explicit validation evidence

---

## 2. Phase 1 - Define and strengthen CLI control plane first

### 2.1 Inventory current CLI / script surfaces
- inspect current shell scripts and python entrypoints
- map existing capabilities for start / stop / status / test / install / bootstrap / asset ops
- identify missing operator actions needed for install-model migration

### 2.2 Define target CLI command surface
- define `agentsystem start`
- define `agentsystem stop`
- define `agentsystem restart`
- define `agentsystem status`
- define `agentsystem install`
- define `agentsystem bootstrap`
- define `agentsystem doctor`
- define `agentsystem assets list`
- define `agentsystem assets discover`
- define `agentsystem assets install <asset_id>`
- define `agentsystem assets install-all`
- define `agentsystem runtime layout`
- define `agentsystem migrate-runtime`

### 2.3 Define CLI behavior contracts
- define output contract for status/doctor commands
- define failure contract for missing config / missing runtime dirs / missing assets
- define dry-run or inspect behavior where useful
- define which commands operate on source repo vs installed runtime

### 2.3 Define CLI behavior contracts
Status: [x] initial contract landed
- `status` / `doctor` now return a compact runtime-layout health contract with directory existence checks
- `status` / `doctor` now surface config-file presence and local service reachability
- not-yet-wired runtime control commands (`start` / `stop` / `restart` / `install` / `bootstrap` / `migrate-runtime`) now return an explicit `not_implemented` contract with exit code `2`
- deeper failure and dry-run semantics remain future work

### 2.4 Implement missing CLI skeletons
Status: [x] initial skeleton landed
- added a python CLI entrypoint (`app.cli`) instead of relying only on repo shell scripts
- wired a planned command surface for top-level runtime/install commands and `assets` subcommands
- current command handlers return explicit planned status details so the control plane contract exists before deeper service binding
- legacy `start_server.sh` / `stop_server.sh` now act as compatibility wrappers that delegate into the Python CLI
- legacy `start_web_server.sh` now also delegates into the same Python CLI start path instead of carrying a separate startup surface

### 2.5 Validate CLI control plane
Status: [x] initial skeleton validation landed
- added focused tests for CLI parsing and command routing
- verified top-level command routing and `assets install <asset_id>` handling
- deeper runtime service binding remains future work

**Exit criteria**
- future install-model migration has a sufficient operator control plane
- key runtime/install/asset commands exist and are documented

---

## 3. Phase 2 - Regenerate and strengthen real-user regression scenarios

### 3.1 Audit current 50x20 scenario suite
Status: [x] initial audit landed
- inspected `tests/e2e/test_50_scenarios_20_turns_user_level.py`
- confirmed the suite still preserves 50 scenarios and includes scenario-end `/api/history/{session_id}` checks
- identified current install-model-sensitive gaps:
  - very light explicit install coverage
  - no explicit asset discover/list/install operator coverage
  - no explicit restart/recovery continuity operator chain
  - no explicit standard-install runtime-layout / migrate-runtime operator flow
- identified the suite as still strong on broad app capability demos, but underweight on operator lifecycle paths needed for install-model baseline

### 3.2 Define stronger scenario coverage goals
Status: [x] initial coverage goals landed
- next scenario refresh should add operator-flavored natural-language chains for install/start/status/doctor/asset actions
- preserve the 50x20 structure for before/after migration comparability
- keep scenario-end history validation as a required baseline expectation

### 3.3 Regenerate or enhance scenario content
Status: [x] first install-model-sensitive scenario refresh landed
- preserved the 50 scenario structure for comparability
- rewrote `S50` into an operator-facing standard-install lifecycle conversation
- rewrote `S41` into a system status and operator-check workflow conversation
- rewrote `S12` into a bulk-app flow with install/register/asset-check operator reasoning
- rewrote `S25` into an exception-recovery and restart-continuity conversation
- rewrote `S36` into a skill-install failure and repair conversation
- added natural-language turns covering status / doctor / runtime-layout / assets / restart / migrate-runtime / baseline-regression reasoning

### 3.4 Add scenario-end expectation checks
Status: [x] already present in harness baseline contract, doc tracking refreshed
- pull `/api/history/{session_id}` after each scenario
- verify user turn count
- verify assistant reply count
- verify session continuity
- verify non-empty final responses
- verify absence of obvious error markers
- add room for scenario-specific expectation extensions later

### 3.5 Improve report output
Status: [x] initial verdict-oriented reporting landed
- per-scenario stdout now includes explicit verdict and compact failure reasons
- JSON report now stores per-scenario verdict, verdict reasons, and history expectation checks/failures
- output is now more suitable for before/after migration diffing without rereading raw turn logs
- explicitly added closure-oriented fields that will support later comparison layering:
  - `verdict`
  - `verdict_reasons`
  - `history_expectation_ok`
  - `history_expectation_failures`
  - `history_expectation_checks`

### 3.6 Validate enhanced harness
Status: [x] initial static validation landed, [!] live subset blocked by service-down state
- verified the refreshed operator-heavy harness still compiles (`python3 -m py_compile ...`)
- verified CLI usage/help still renders with the expected subset/run/output flags
- canonical operator-focused subset for the next live run is now defined as: `S12,S25,S36,S41,S50`
- attempted live subset execution against `http://localhost:80`, but the service was unreachable (`[Errno 111] Connection refused`)
- exact live subset execution now depends on completing Phase 3 service-up preparation or manually starting the service first

**Exit criteria**
- 50x20 suite is realistic enough to serve as migration baseline
- scenario-end history validation is part of the harness

---

## 4. Phase 3 - Run pre-migration baseline and repair failures

### 4.1 Prepare service-up environment for long E2E run
Status: [x] first service-readiness doctor slice landed
- `agentsystem status` / `agentsystem doctor` now explicitly report config-file presence and local `http://localhost:80/api/status` reachability
- the readiness surface now also exposes a canonical `suggested_start_command` for the current repo-coupled runtime path
- validated that the canonical repo-coupled uvicorn start path can boot the service successfully (`application startup complete`, `Uvicorn running on http://0.0.0.0:80`) under a bounded timeout run
- first live operator-subset run surfaced a concrete startup/runtime dependency gap: `python-multipart` is required by `/login` form parsing and was missing from install dependencies
- this gives Phase 3 service-up prep a concrete control-plane check before attempting long live subset or full baseline runs

### 4.2 Execute full pre-migration baseline
- run 50 scenarios × 20 turns with 3s delay
- capture report artifact
- capture service logs if needed
- summarize overall scenario pass/fail picture

### 4.3 Analyze failures
- classify failures by harness issue / model instability / real product bug / session continuity bug / lifecycle bug
- identify highest-value blockers first
- define minimal fixes required for a trustworthy baseline

### 4.4 Repair and re-run until baseline is trustworthy
- fix real product issues surfaced by the baseline
- re-run affected scenarios first
- if needed rerun the full suite once stabilized
- produce final pre-migration baseline report

### 4.5 Freeze baseline evidence
- save report path and summary in testing docs
- update development log
- record baseline as pre-install-model truth set
- commit and push baseline evidence

**Exit criteria**
- there is a credible full baseline before migration
- known failures are either fixed or explicitly documented as accepted pre-existing limitations

---

## 5. Phase 4 - Define standard install model architecture

### 5.1 Define runtime separation model
- define source repo responsibilities
- define installed code responsibilities
- define runtime data responsibilities
- define config/state/log/cache boundaries
- define what is forbidden inside the source repo at runtime

### 5.2 Define target directory layout
- config directory
- data directory
- runtime/state directory
- cache directory
- installed asset directory
- source asset development directory
- build artifact directory
- logs directory

### 5.3 Define environment/config resolution contract
- support `AGENTSYSTEM_HOME`
- support `AGENTSYSTEM_DATA_DIR`
- define defaults using home/XDG-like layout
- eliminate remaining implicit repo-based runtime assumptions

### 5.4 Define asset lifecycle under the new model
- distinguish built-in system assets
- distinguish packaged assets
- distinguish user-installed assets
- distinguish runtime-registered assets
- define discover/build/install/register/invoke/uninstall/rollback boundaries

### 5.5 Define migration plan from current repo-coupled model
- how current `source/`, `build/`, `installed/`, `data/` semantics map to new locations
- how existing runtime state migrates
- how compatibility wrappers behave during transition
- how to preserve existing tests during the transition

### 5.6 Document architecture before code migration
- write a detailed design doc
- write operator-facing install model notes
- update system/testing docs with migration assumptions

**Exit criteria**
- install model architecture is explicit before implementation
- path/data/asset semantics are unambiguous

---

## 6. Phase 5 - Move runtime code execution out of source repo

### 6.1 Package the core Python runtime properly
- ensure project package metadata supports installed execution
- define console_scripts entrypoint(s)
- verify installed-package imports do not depend on repo-relative execution

### 6.2 Remove repo-root assumptions from runtime start path
- startup should resolve installed package location, not repo path
- runtime services should use config/data dirs, not repo dirs
- start/stop/status should target installed runtime

### 6.3 Keep source-repo scripts as operator wrappers only
- repo scripts may call install/start commands
- repo scripts must not directly become the runtime execution root
- clarify compatibility behavior for developers

### 6.4 Validate installed-code execution
- install into venv
- launch from installed command path
- verify service comes up without requiring cwd=repo
- run focused smoke checks

**Exit criteria**
- runtime code executes from installed package context
- source repo is no longer the required runtime code root

---

## 7. Phase 6 - Move assets, build, and runtime state out of source repo

### 7.1 Externalize runtime state directories
- move runtime persistence out of repo
- move context center state out of repo
- move logs out of repo
- move registry/state snapshots out of repo

### 7.2 Externalize installed assets
- define installed asset root outside repo
- ensure runtime uses installed asset root, not repo `installed/`
- migrate asset resolution logic accordingly

### 7.3 Externalize build artifacts
- define build output root outside repo for runtime-relevant artifacts
- keep repo build outputs only for developer convenience if needed
- ensure runtime does not depend on repo build directories

### 7.4 Decide treatment of source assets
- keep dev source assets in repo for editing
- copy/sync/install them into external data area when installing assets
- ensure runtime discover/install operations target externalized source/install roots

### 7.5 Add migration/bootstrap helpers
- add commands to initialize runtime layout
- add commands to migrate old repo-local runtime data if needed
- add checks that warn when runtime is still pointing into repo

### 7.6 Validate runtime/asset separation
- run installed runtime with repo absent from cwd assumptions
- verify assets still discover/install/run correctly
- verify persistence paths now land outside repo

**Exit criteria**
- real runtime assets and state are fully separated from source repo
- repo can be treated as development workspace only

---

## 8. Phase 7 - Implement install flows

### 8.1 Single-asset install flow
- install one asset from development source into external runtime layout
- register/install metadata correctly
- expose operator command for it

### 8.2 Install-all flow
- discover all intended installable assets
- build/install them in controlled order
- report per-asset success/failure
- support re-run behavior safely

### 8.3 Bootstrap flow
- initialize directories
- initialize built-in/core assets
- prepare default runtime metadata
- document idempotent behavior

### 8.4 Doctor/status flow
- verify config exists
- verify runtime directories exist
- verify installed package is healthy
- verify required core assets are available
- verify service readiness basics

### 8.5 Validate install lifecycle
- test clean environment install
- test incremental asset install
- test reinstall/install-all idempotence
- test status/doctor output
- commit install-flow phase

**Exit criteria**
- new environment can be installed and bootstrapped without repo-coupled runtime behavior
- operator flows are clear and repeatable

---

## 9. Phase 8 - Run post-migration baseline and repair regressions

### 9.1 Execute full post-migration 50x20 baseline
- same 50 scenarios
- same 20 turns
- same 3 second delay
- same history validation rules
- produce after-install-model report

### 9.2 Compare before vs after
- compare scenario full-pass count
- compare total turn success rate
- compare session continuity behavior
- compare lifecycle chain behavior
- compare history/record integrity
- compare obvious error markers

### 9.3 Repair migration regressions
- prioritize true install-model regressions
- fix runtime path, asset install, bootstrap, lifecycle, or session issues
- rerun affected scenarios
- rerun full suite if necessary

### 9.4 Freeze post-migration evidence
- save final after report
- update testing docs with before/after summary
- update development log with migration validation evidence
- commit and push final regression closure

**Exit criteria**
- install-model migration does not materially regress the real-user baseline
- any remaining deltas are explicitly documented and accepted

---

## 10. Deliverables

By the end of this workstream, the repo should contain:
- CLI command design and implementation docs
- enhanced 50x20 real-user regression harness
- pre-migration full baseline report
- standard install model design doc
- installed-runtime path migration implementation
- externalized asset/runtime/data/state layout
- single-asset install and install-all flows
- post-migration full baseline report
- updated development/testing documentation
- meaningful commits and remote pushes for each completed phase

---

## 11. Recommended commit boundaries

1. docs: close old task-list residue and define install-model plan
2. feat: strengthen CLI control plane for install-model migration
3. test: enhance 50x20 user-level regression harness with scenario-end history checks
4. test/docs: record pre-migration full baseline and failure analysis
5. docs: define standard install model architecture and runtime layout
6. feat: run core runtime from installed package context
7. feat: externalize assets and runtime state from source repo
8. feat: add single-asset install, install-all, bootstrap, and doctor flows
9. test/docs: record post-migration full baseline and regression closure
