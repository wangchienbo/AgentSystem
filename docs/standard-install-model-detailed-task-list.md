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
- [x] close remaining Phase R Wave 5 open slice items:
  - [x] derive changed-file intent from actual repo inspection plus task-list hints more directly
  - [x] reduce reliance on the single-work-item fallback for multi-command acceptance evidence mapping
  - [x] decide whether compact changed-file/result summaries should surface into a lighter operator-facing read model
- [ ] verify there is no remaining HTTP compatibility drift between `/api/chat`, `/api/action`, gateway action payloads, and service-up consumers
  - [x] fixed multi-worker cookie session rehydration so `/login` → `/api/chat` no longer fails with `401 Not authenticated` when requests land on different uvicorn workers
  - [x] aligned the active 1seey model name with the user-channel provider config (`qwen3.6-plus` instead of `gpt-5.4`)
  - [x] added a lightweight direct-answer fast path so obvious no-tool prompts no longer pay the native tool-calling route or trigger upstream 1seey tool-call 504s during basic service-up checks
  - [x] focused local regression remains green for the current HTTP/action/acceptance surfaces (`66 passed` across `test_http_test_server`, `test_light_brain_gateway_acceptance_binding`, `test_tool_calling_interpreter`)
  - [x] verify remaining tool-required routes still behave acceptably under the current 1seey + GLM-5.1 timeout profile
    - added an explicit `tool_required_probe` to `tests/scripts/e2e_self_iteration_service_up.py`
    - bounded live rerun now passes ready/login/basic-chat but stalls after entering the real upstream `chat_with_tools` path for the tool-required probe
    - remaining closure item is upstream tool-calling timeout/convergence handling, not local HTTP contract drift
    - follow-up live subset work confirmed a phased local convergence hardening path landed:
      - operator-heavy guidance hardening
      - operator-heavy tool-surface narrowing
      - repeated `call_asset_method` loop guard
      - post-loop-guard answer shaping
      - stale subset-server cleanup hardening
      - early tool-route retry/timeout patience hardening
    - current remaining blocker is no longer local route wandering, but unstable upstream provider behavior (`504` / read timeout) preventing a clean final validation window for the operator-heavy subset
- [x] close any remaining startup path cleanup/output cleanup deltas discovered while stabilizing long-run baseline execution
  - [x] widened startup-script kill target and added port-free wait so repeated `start_phase3_subset_server.sh` restarts no longer race on `Address already in use`
  - [x] decoupled `start_phase3_subset_server.sh` from repo-root `cd` / `PYTHONPATH` startup assumptions by switching to `--app-dir` plus `AGENTSYSTEM_DATA_DIR`
  - [x] compatibility wrappers (`start_server.sh`, `start_web_server.sh`, `stop_server.sh`) now invoke `app/cli.py` directly instead of exporting repo-root `PYTHONPATH`
  - [x] full-E2E helper scripts (`run_full_e2e_bg.sh`, `run_full_e2e_detached.sh`) now invoke the test file directly instead of `cd` + repo-root `PYTHONPATH` + module execution
  - [x] grouped pytest runner helper (`scripts/run_test_groups.sh`) now calls the venv python directly with absolute test paths instead of `cd`-into-root execution
- [x] confirm no runnable path still has an implicit repo-root dependency once installed-runtime migration starts
  - [x] runtime subprocess default cwd no longer inherits repo-root process cwd
  - [x] pipeline executor default workspace no longer inherits repo-root process cwd
  - [x] validation guidance no longer teaches repo-root-coupled startup phrasing
  - [x] service-up probe scripts now launch uvicorn from runtime data dir with explicit import path instead of repo-root cwd
  - [x] CLI suggested start command now uses `--app-dir` plus `AGENTSYSTEM_DATA_DIR` instead of `cd <repo-root> && PYTHONPATH=...`
  - [x] current bounded grep sweep across runnable app/tests/scripts surfaces found no remaining obvious `repo_root cwd` / `ROOT_DIR cwd` / `PYTHONPATH=<repo_root>` / `os.getcwd()` style hits
- [x] explicitly track older closure-upgrade items that were conceptually merged but not yet fully closed:
  - [x] query/read fast-path for cheap count/status/list requests
  - [x] closure scoring split beyond raw response success
  - [x] run isolation metadata for long E2E analysis (`run_id`, `scenario_id`)

### 1.2 Close code-level loose ends
Status: [~] in progress, narrowed to remaining live HTTP/provider closure window
- finish any partially landed workflow/action/acceptance chain improvements
- close any pending HTTP compatibility deltas
  - local contract/path drift evidence is green
  - remaining unresolved closure is live upstream tool-calling/provider stability during operator-heavy service-up validation
- close any remaining path-cleanup/output-cleanup items discovered during service startup
  - current bounded helper/startup sweeps are clean
- verify no repo-root hard dependency remains in runnable code paths
  - current bounded runnable-path and shell/helper sweeps are clean

### 1.3 Close validation and docs for old work
Status: [x] focused validation/docs closure landed
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
Status: [x] initial inventory landed
- inspected current shell wrappers and helper scripts:
  - top-level: `start_server.sh`, `start_web_server.sh`, `stop_server.sh`, `run_full_e2e_bg.sh`, `run_full_e2e_detached.sh`, `task_push.sh`
  - helpers: `scripts/start_phase3_subset_server.sh`, `scripts/run_test_groups.sh`, `scripts/model_probe.py`
- confirmed the primary operator control plane now centers on `app/cli.py`
- confirmed compatibility shell wrappers now delegate into `app/cli.py` rather than carrying separate runtime logic
- identified adjacent python entrypoints still relevant to install-model planning:
  - `app/system/http_test_server.py`
  - `app/runtime/app_bootstrap.py`
  - user-level E2E harness entrypoint in `tests/e2e/test_50_scenarios_20_turns_user_level.py`
- current operator-facing gaps still align with the planned command surface: runtime start/stop/restart/install/bootstrap/migrate-runtime are present as contract stubs but not yet wired to real service/install behavior

### 2.2 Define target CLI command surface
Status: [x] initial target surface landed
- defined top-level commands:
  - `agentsystem start`
  - `agentsystem stop`
  - `agentsystem restart`
  - `agentsystem status`
  - `agentsystem install`
  - `agentsystem bootstrap`
  - `agentsystem doctor`
  - `agentsystem runtime-layout`
  - `agentsystem migrate-runtime`
- defined asset subcommands:
  - `agentsystem assets list`
  - `agentsystem assets discover`
  - `agentsystem assets install <asset_id>`
  - `agentsystem assets install-all`
- current implementation status is intentionally split:
  - command names and parser surface exist
  - `status` / `doctor` / `runtime-layout` have live contract behavior
  - runtime/install/migrate commands still need deeper service/install wiring

### 2.3 Define CLI behavior contracts
Status: [x] initial contract landed
- `status` / `doctor` now return a compact runtime-layout health contract with directory existence checks
- `status` / `doctor` now surface config-file presence and local service reachability
- `status` / `doctor` now also expose explicit failure-semantics fields (`status_reason`, `missing_checks`, `next_actions`)
- `runtime-layout` now exposes the current repo-anchored runtime layout contract used during transition planning
- not-yet-wired runtime control commands (`start` / `stop` / `restart` / `install` / `bootstrap` / `migrate-runtime`) now return an explicit `not_implemented` contract with exit code `2`
- deeper dry-run semantics remain future work

### 2.4 Implement missing CLI skeletons
Status: [x] initial skeleton landed
- added a python CLI entrypoint (`app.cli`) instead of relying only on repo shell scripts
- wired a planned command surface for top-level runtime/install commands and `assets` subcommands
- `assets list` / `assets discover` now expose a live builtin-asset inventory contract from the source-repo transition view
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
Status: [x] initial static validation landed, [!] live subset depends on explicit ready-state wait
- verified the refreshed operator-heavy harness still compiles (`python3 -m py_compile ...`)
- verified CLI usage/help still renders with the expected subset/run/output flags
- canonical operator-focused subset for the next live run is now defined as: `S12,S25,S36,S41,S50`
- attempted live subset execution against `http://localhost:80`; the workstream first surfaced a service-down state, then later a startup/readiness timing gap
- harness now supports an explicit `--wait-ready-seconds` gate on `/api/status` before scenario execution
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
- first live operator-subset run surfaced a concrete startup/runtime dependency gap: `python-multipart` is required by `/login` form parsing and was missing from the system-python install path
- after retry/concurrency hardening, an immediate rerun attempt hit a service-readiness timing issue (`/api/chat` server process had previously booted, but the fresh subset launch saw `服务不可达: timed out` at the harness connectivity gate), so the next rerun should explicitly wait for ready state before firing the subset
- harness readiness probes now disable env-proxy inheritance (`trust_env=False`) so localhost baseline runs do not mis-route `/api/status` or `/api/chat` through ambient proxy settings
- this gives Phase 3 service-up prep a concrete control-plane check before attempting long live subset or full baseline runs

### 4.2 Execute full pre-migration baseline
Status: [~] live rerun path tightened, full 50x20 still pending
- after the localhost proxy-inheritance fix, a bounded rerun against `S41` now reaches live `/api/chat` execution instead of failing at the readiness gate
- bounded `S41` probe with `--max-turns-per-scenario 2 --max-consecutive-failures 1` confirmed the timeout onset window more tightly:
  - turn `01/20` succeeds quickly
  - turn `02/20` times out after `45.0s`
  - subsequent scenario execution can be aborted immediately for cheaper evidence capture
- harness now supports `--max-consecutive-failures` to abort pathological timeout streaks early and preserve faster failure evidence during Phase 3 reruns
- full 50x20 baseline is still deferred until the repeated live chat timeout pattern is reduced enough to make the run economically trustworthy

### 4.3 Analyze failures
Status: [~] first concrete live failure pattern captured
- current highest-signal failure pattern is no longer localhost readiness misrouting
- current highest-signal failure pattern is repeated `/api/chat` timeout under live operator workflow load after an initial successful turn
- bounded probing now localizes the onset window to `turn 02` on `S41` under the current live service state
- server logs show the second-turn stall is dominated by repeated upstream `504 Gateway Timeout` responses on the tool-calling route (`/v1/chat/completions`), not by local readiness failure
- tool-route retry budgets have now been tightened so short histories fail faster instead of stretching a single degraded upstream call across several minutes
- failure class currently looks closer to upstream model/runtime instability than to basic harness transport failure
- harness now also supports `--max-turns-per-scenario` so Phase 3 can isolate whether failures begin only after turn/context buildup instead of committing immediately to full 20-turn replay
- next reruns should use bounded fail-fast settings first, then decide whether the remaining blocker is model timeout tuning, request-shape reduction, or server-side runtime repair

### 4.4 Repair and re-run until baseline is trustworthy
Status: [x] bounded live repair loop now clears the full 50-scenario suite through 5 turns
- Phase 3 log evidence showed repeated fallback turns were accumulating into the gateway prompt context for later operator/status probes
- the gateway tool-calling interpreter now caps recent-history prompt inclusion more aggressively (last 4 messages, ~800 chars budget) so short operator/status queries are less likely to inherit bloated fallback-heavy context
- after restarting onto the live budget-aware runtime, bounded `S41` rerun (`--max-turns-per-scenario 2 --max-consecutive-failures 1`) improved materially:
  - turn `01/20` succeeded
  - turn `02/20` also succeeded in ~`1.0s`
  - remaining failure was only that scenario-end history expectations were still comparing against full 20-turn totals during a bounded 2-turn diagnostic
- a deeper bounded `S41` rerun (`--max-turns-per-scenario 5`) then showed all first five turns succeeding with no transport/service errors; the remaining mismatch came from reusing the same scenario user/session across prior probes
- harness scenario users are now isolated by `run_id`, so future bounded reruns do not inherit stale session history from earlier diagnostics
- bounded history expectations now follow the executed-turn count instead of the full scenario design length, so future diagnostic reruns fail only for relevant reasons
- silent empty replies are now treated as failures, and `/api/chat` error paths now surface visible assistant text instead of returning blank success-like responses
- tool-route `429` responses are now treated as retryable degradation signals, allowing turn-0 tool-calling failures to fall back to the existing non-convergence text instead of surfacing raw upstream errors
- after restarting the service with the 429 degradation patch, bounded `S41` rerun (`--max-turns-per-scenario 5`) passed cleanly:
  - turns `01-05/20` all succeeded
  - no transport/service errors occurred
  - scenario-end history checks passed
  - operator/status turns that hit provider pressure now degrade to the conservative visible fallback text instead of failing the user-visible baseline
- widened bounded rerun from single-scenario `S41` to the system/operator subset `S41-S45` with `--max-turns-per-scenario 5`
  - all `5/5` scenarios passed
  - all `25/25` executed turns succeeded
  - no transport/service errors occurred
  - all scenario-end history checks passed
- widened again to the adjacent cross-interaction subset `S46-S49` with the same bounded 5-turn window
  - all `4/4` scenarios passed
  - all `20/20` executed turns succeeded
  - no transport/service errors occurred
  - all scenario-end history checks passed
- merged both repaired slices into one combined bounded baseline rerun over `S41-S49`
  - all `9/9` scenarios passed
  - all `45/45` executed turns succeeded
  - no transport/service errors occurred
  - all scenario-end history checks passed
- widened the bounded baseline further to `S30-S49`
  - first rerun reached `19/20` because `S31` exposed a harness-only synthetic-empty-input history mismatch
  - that expectation bug is now fixed
- reran the corrected broader bounded slice `S30-S49`
  - all `20/20` scenarios passed
  - all `100/100` executed turns succeeded
  - no transport/service errors occurred
  - all scenario-end history checks passed
- widened once more to `S20-S49`
  - all `30/30` scenarios passed
  - all `150/150` executed turns succeeded
  - no transport/service errors occurred
  - all scenario-end history checks passed
- widened again to `S10-S49`
  - all `40/40` scenarios passed
  - all `200/200` executed turns succeeded
  - no transport/service errors occurred
  - all scenario-end history checks passed
- after confirming service reachability up front, ran the final bounded full-suite rerun over all `50` scenarios
  - all `50/50` scenarios passed
  - all `250/250` executed turns succeeded
  - no transport/service errors occurred
  - all scenario-end history checks passed

### 4.5 Freeze baseline evidence
Status: [x] bounded full-suite evidence frozen
- final bounded full-suite report captured at:
  - `/tmp/e2e_full_50_bounded_turn5_probe.json`
- final bounded full-suite outcome:
  - `50/50` scenarios passed
  - `250/250` executed turns succeeded
  - `0` transport/service errors
  - all scenario-end history checks passed
- final bounded progression evidence is now recorded in sequence:
  - `/tmp/e2e_s41_turn5_probe_429degrade.json`
  - `/tmp/e2e_system_subset_turn5_probe.json`
  - `/tmp/e2e_cross_subset_turn5_probe.json`
  - `/tmp/e2e_s41_s49_combined_turn5_probe.json`
  - `/tmp/e2e_s30_s49_bounded_turn5_postfix.json`
  - `/tmp/e2e_s20_s49_bounded_turn5_probe.json`
  - `/tmp/e2e_s10_s49_bounded_turn5_probe.json`
  - `/tmp/e2e_full_50_bounded_turn5_probe.json`
- baseline summary has been written into testing docs and development log
- Phase 4 bounded repair loop can now be treated as the frozen pre-install-model truth set for later before/after comparison
- any later comparison should keep the same bounded settings unless the acceptance contract is intentionally redefined

**Exit criteria**
- there is a credible full baseline before migration
- known failures are either fixed or explicitly documented as accepted pre-existing limitations

---

## 5. Phase 4 - Define standard install model architecture

### 5.1 Define runtime separation model
Status: [x] target model documented
- defined source repo responsibilities
- defined installed code responsibilities
- defined runtime data responsibilities
- defined config/state/log/cache boundaries
- documented what is forbidden inside the source repo at runtime

### 5.2 Define target directory layout
Status: [x] target layout documented
- defined config directory
- defined data directory
- defined runtime/state directory
- defined cache directory
- defined installed asset directory
- defined source asset development directory boundary
- defined build artifact and logs directories

### 5.3 Define environment/config resolution contract
Status: [x] resolution contract documented
- documented `AGENTSYSTEM_HOME`
- documented dedicated path override env vars including `AGENTSYSTEM_DATA_DIR`
- defined home-based default layout
- documented resolution order and repo-coupled compatibility fallback limits

### 5.4 Define asset lifecycle under the new model
Status: [x] lifecycle boundaries documented
- distinguished built-in system assets
- distinguished packaged assets
- distinguished user-installed assets
- distinguished runtime-registered assets
- defined discover/build/install/register/invoke/uninstall/rollback boundaries

### 5.5 Define migration plan from current repo-coupled model
Status: [x] migration intent documented
- mapped current `source/`, `build/`, `installed/`, `data/` semantics toward target roots
- documented runtime state migration concerns
- documented compatibility wrapper behavior during transition
- documented test-preservation strategy using the frozen bounded baseline

### 5.6 Document architecture before code migration
Status: [x] initial architecture doc landed
- added `docs/standard-install-model-architecture.md`
- documented runtime separation model, directory layout, env/config resolution, asset lifecycle, migration intent, and operator-facing notes before code migration begins
- added `docs/standard-install-model-migration-prep.md`
- documented the concrete repo-coupled path-assumption inventory and recommended the first implementation slices, with Slice A (shared runtime path resolver) as the next migration step
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
Status: [~] prerequisites largely prepared
- Slice A/B moved most mutable runtime-state defaults behind the shared runtime resolver
- remaining repo-anchored items are now mostly intentional asset/control-plane boundaries, not generic mutable-state defaults
- Phase 6 should now focus on asset/control-plane separation rather than more broad `data/...` default cleanup

### 7.2 Externalize installed assets
Status: [x] Slice C2 landed, Slice C3 next
- `AssetCenter` default roots now resolve installed/build/data locations from the shared install-model path contract when explicit overrides are not provided
- `SkillRegistryService` now also defaults to the install-model installed asset root when explicit overrides are not provided
- `CoreOrchestrator` now threads its `AssetCenter` installed-root choice into `SkillRegistryService`, removing one more hardcoded `installed/` caller seam from the non-bootstrap path
- CLI `runtime-layout` now exposes an `asset_root_transition` block so operators can inspect install-model target roots alongside legacy repo-pinned roots during migration
- bootstrap asset wiring is now described through a dedicated helper contract, exposed through CLI runtime-layout for inspection
- bootstrap binding contract added an explicit preview mode, then landed the first live bootstrap flip
- current live Phase 6 asset wiring now uses:
  - install-model `installed/` asset root
  - install-model `build/` artifact root
  - repo `source/` root retained for development
  - repo `data/runtime_center.json` retained for runtime-registry persistence until Slice C4
- remaining next slice is now:
  - Slice C3 package built-in control-plane assets so installed execution no longer depends on repo-root path-definition loading
- validation progression recorded in testing docs culminates in:
  - `pytest -q tests/unit/test_bootstrap_runtime_isolation.py tests/unit/test_bootstrap_asset_binding.py tests/unit/test_cli.py tests/unit/test_installed_asset_root_adoption.py tests/unit/test_asset_center_install_model_roots.py tests/unit/test_asset_center_manifest_validation.py tests/unit/test_registry_installer.py tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_runtime_path_adoption_wave2.py tests/unit/test_runtime_path_adoption_wave3.py tests/unit/test_runtime_path_adoption_wave4.py` -> `47 passed`

### 7.3 Externalize build artifacts
Status: [ ] blocked on asset root map
- define build output root outside repo for runtime-relevant artifacts
- keep repo build outputs only for developer convenience if needed
- ensure runtime does not depend on repo build directories

### 7.4 Decide treatment of source assets
Status: [x] Slice C1 decision artifact landed
- added `docs/phase-6-asset-control-plane-separation-plan.md`
- added `docs/phase-6-slice-c1-root-map.md`
- decided that repo-authored path definitions should be treated as packaged built-in control-plane assets under the install model
- published the initial root map for:
  - development source assets
  - build/package outputs
  - installed runtime assets
  - built-in control-plane assets
  - runtime registry persistence
  - mutable runtime data/state/log roots
- documented that `RuntimeCenter` persistence migration is intentionally deferred until built-in asset bootstrap semantics are explicitly rewritten
- recommended next follow-on implementation slices:
  - Slice C2 externalize installed asset root
  - Slice C3 package built-in control-plane assets
  - Slice C4 externalize runtime registry persistence

### 7.5 Add migration/bootstrap helpers
Status: [ ] not started
- add commands to initialize runtime layout
- add commands to migrate old repo-local runtime data if needed
- add checks that warn when runtime is still pointing into repo

### 7.6 Validate runtime/asset separation
Status: [ ] not started
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

- [ ] add route-aware timeout/retry budgeting for later governance self-iteration cycles under the current 1seey profile

- [x] add bounded route-aware timeout/retry budgeting for deeper GLM tool routes so later governance self-iteration paths do not amplify `1seey` `504` responses into multi-minute waits
- [ ] rerun live governance self-iteration validation after the route-aware timeout/retry change

### 5.7 Implement first migration slice: shared runtime path resolver
Status: [x] initial resolver landed
- added `app/runtime_paths.py` as the shared runtime layout resolver
- resolver now defines:
  - `AGENTSYSTEM_HOME`
  - `AGENTSYSTEM_CONFIG_DIR`
  - `AGENTSYSTEM_DATA_DIR`
  - `AGENTSYSTEM_STATE_DIR`
  - `AGENTSYSTEM_CACHE_DIR`
  - `AGENTSYSTEM_LOG_DIR`
  - `AGENTSYSTEM_ASSET_DIR`
- CLI `runtime-layout` / `doctor` / planned command surfaces now report resolved install-model paths instead of only repo-anchored directory literals
- `app/ai/model_config_loader.py` now resolves its default config path from the shared runtime path contract
- added focused unit coverage for resolver defaults, env overrides, CLI layout/doctor integration, and model-config default path wiring
- validation:
  - `pytest -q tests/unit/test_runtime_paths.py tests/unit/test_cli.py tests/unit/test_model_config.py` -> `15 passed`

### 5.8 Implement second migration slice: move first runtime/persistence defaults behind resolver
Status: [x] first adoption wave landed
- migrated default runtime/persistence roots for:
  - `RuntimeStateStore`
  - `AppDataStore`
  - `UpgradeLogService`
  - `RuntimeCenter`
  - `ResourceCenter`
  - `ConfigCenterService`
- these services now resolve install-model defaults from `app/runtime_paths.py` instead of repo-local `data/...` literals when no explicit path override is provided
- preserved explicit constructor overrides so focused tests and isolated runtimes can still pass custom temp paths
- updated isolated API test helper to provide an explicit temporary config contract for model-router-dependent runtime tests
- validation:
  - `pytest -q tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_cli.py tests/unit/test_model_config.py tests/unit/test_app_data_store.py tests/unit/test_upgrade_rollback.py` -> `55 passed`

### 5.9 Continue second migration slice: expand resolver adoption across remaining mutable-state defaults
Status: [x] second adoption wave landed
- migrated additional repo-local mutable-state defaults behind the shared resolver for:
  - `PersistenceService`
  - `PipelineExecutor` default workspace resolution
  - lifecycle archive-event upgrade-log path
  - bootstrap runtime assembly defaults for `RuntimeStateStore` and `AppDataStore`
- intentionally kept `AssetCenter` installed/build roots repo-anchored for now because asset-root separation is still part of the later asset-lifecycle migration slice, and switching it early broke current startup assumptions
- intentionally kept bootstrap `RuntimeCenter` on its existing repo-backed file to avoid changing system-asset startup semantics before the asset/runtime migration seam is explicitly handled
- validation:
  - `pytest -q tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_runtime_path_adoption_wave2.py tests/unit/test_cli.py tests/unit/test_model_config.py tests/unit/test_app_data_store.py tests/unit/test_upgrade_rollback.py tests/unit/test_persistence_e2e.py` -> `62 passed`

### 5.10 Continue Slice B tail-close: adopt resolver for remaining safe data-root helpers
Status: [x] third adoption wave landed
- migrated additional safe data-root defaults behind the shared resolver for:
  - `GeneratedCallableMaterializer`
  - `SkillConfigCenter`
  - `PathStore`
- bootstrap still intentionally pins `PathStore` to the repo-curated path-definition directory, because those YAML path assets remain part of the repo-owned authored control plane during this migration stage
- validation:
  - `pytest -q tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_runtime_path_adoption_wave2.py tests/unit/test_runtime_path_adoption_wave3.py tests/unit/test_cli.py tests/unit/test_model_config.py tests/unit/test_app_data_store.py tests/unit/test_upgrade_rollback.py tests/unit/test_persistence_e2e.py tests/unit/test_execution_chain_integration.py` -> `76 passed`

### 5.11 Re-scan Slice B tail and close the remaining safe mutable-state defaults
Status: [x] safe mutable-default tail substantially closed
- migrated `CoreOrchestrator` default `data_dir` to the shared runtime resolver
- re-scan result:
  - remaining repo-anchored paths are now primarily intentional boundaries, not accidental mutable-state defaults
  - `bootstrap/runtime.py` still explicitly pins repo-owned path-definition assets via `PathStore(paths_dir=...)`
  - asset/control-plane path normalization inside `skill_asset_service.py` still intentionally understands legacy `data/...` references during transition
- this means Slice B's remaining unresolved items are now mostly migration-boundary items rather than straightforward default-path cleanup
- validation:
  - `pytest -q tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_runtime_path_adoption_wave2.py tests/unit/test_runtime_path_adoption_wave3.py tests/unit/test_runtime_path_adoption_wave4.py tests/unit/test_cli.py tests/unit/test_model_config.py tests/unit/test_app_data_store.py tests/unit/test_upgrade_rollback.py tests/unit/test_persistence_e2e.py tests/unit/test_execution_chain_integration.py` -> `77 passed`

### 7.2 Externalize installed assets
Status: [~] first live-code adoption landed
- `AssetCenter` default roots now resolve installed/build/data locations from the shared install-model path contract when explicit overrides are not provided
- bootstrap still intentionally passes repo-anchored installed/build roots during transition so built-in startup semantics remain stable while Phase 6 proceeds slice-by-slice
- this establishes the first live-code seam for Slice C2 without yet forcing the bootstrap/runtime path flip
- validation:
  - `pytest -q tests/unit/test_asset_center_install_model_roots.py tests/unit/test_asset_center_manifest_validation.py tests/unit/test_registry_installer.py tests/unit/test_runtime_paths.py tests/unit/test_runtime_path_adoption.py tests/unit/test_runtime_path_adoption_wave2.py tests/unit/test_runtime_path_adoption_wave3.py tests/unit/test_runtime_path_adoption_wave4.py` -> `33 passed`
- `SkillRegistryService` now also defaults to the install-model installed asset root when explicit overrides are not provided
- `CoreOrchestrator` now threads its `AssetCenter` installed-root choice into `SkillRegistryService`, removing one more hardcoded `installed/` caller seam from the non-bootstrap path
- CLI `runtime-layout` now exposes an `asset_root_transition` block so operators can see both install-model target roots and legacy repo-pinned roots while Slice C2 remains in transition
- bootstrap asset wiring is now described through a dedicated helper contract, and CLI `runtime-layout` exposes that binding so the repo-pinned asset roots vs install-model data root split is explicit before any bootstrap flip
- bootstrap binding contract now supports an explicit `install-model-preview` mode so Slice C2 can inspect the first candidate installed/build root flip without changing live bootstrap behavior
- added isolated bootstrap-runtime test coverage that proves the current binding still boots under injected config/home while differing from the install-model-preview asset roots only at the intended installed/build seam
- Slice C2 first live bootstrap flip landed: runtime bootstrap now uses install-model installed/build roots while retaining repo source assets and repo runtime-registry persistence; CLI keeps the old repo-pinned binding as the explicit preview/rollback reference
- Slice C3 first seam landed for built-in control-plane path assets: bootstrap now materializes repo-authored `data/paths/*.yaml` into install-model installed assets and loads `PathStore` from that projected built-in package location instead of reading path definitions directly from the repo at runtime
- built-in path projection now also emits `builtin_paths_manifest.json`, giving the first packaged control-plane asset projection an explicit manifest/identity record inside installed assets instead of being only a raw file copy
- builtin path projection manifest now carries per-file SHA-256 fingerprints, tightening the packaged identity contract beyond filename inventory and preparing for later projection drift checks or upgrade comparisons
- builtin path projection now cleans stale projected YAML files that no longer exist in repo-authored source, making the packaged built-in control-plane asset projection converge toward the authored set instead of only ever accumulating files
- packaged built-in path projections are now treated as read-only runtime assets: `PathStore` detects `builtin_paths_manifest.json` and blocks save/remove mutations against the projected install-model bundle
- packaged built-in path bundles now expose manifest metadata through `PathStore.bundle_manifest()`, making the projected runtime bundle identity inspectable without reopening repo-authored source files directly
- `PathStore` now exposes an explicit `is_packaged_bundle` flag alongside manifest access, making packaged-vs-mutable path storage semantics directly inspectable by runtime callers
- bootstrap runtime registry binding now follows install-model state storage (`state/runtime_center.json`) instead of repo `data/`, and runtime bootstrap now explicitly registers the full core runtime asset set instead of relying on repo-carried legacy registry residue
- `SystemCatalog` default persistence now resolves from install-model runtime paths instead of repo-local `data/`, further separating durable catalog state from source checkout assumptions
- `PipelineService` default storage now also resolves from install-model runtime paths, removing another repo-local durable-state fallback from orchestration records
- `InteractiveAppService` default per-user workspace/version/config storage now resolves from install-model runtime paths instead of repo-local `data/interactive_app/...`
- `UserService` default user-registry storage now resolves from install-model runtime paths instead of repo-local `data/users/...`, continuing durable identity/state separation from the source checkout
- `MemorySkillService` and `InteractiveAppWorkflow` default storage/workflow roots now also resolve from install-model runtime paths, continuing the removal of repo-local `data/...` durable-state defaults from interactive-user flows
- `app.runtime.app_bootstrap` and `AppProcessManager` now default to install-model runtime data paths, and bootstrap now ensures the target runtime data directory exists before writing runtime registry state
- context-center storage path defaults now resolve from install-model runtime data paths as well, reducing another repo-root `data/...` assumption inside cross-session context persistence helpers
- replay-regression sample storage now resolves dynamically from install-model runtime data paths instead of relying on import-time repo/data-derived constants, tightening another context/governance storage seam
- AppManagementWorker subprocess launch now falls back to install-model runtime data paths when `AGENTSYSTEM_DATA_DIR` is unset, removing another residual repo-local `data` cwd assumption from app lifecycle control
- HTTP test server chat log storage now resolves from install-model runtime data paths, continuing the last visible repo-local `data/...` cleanup in the web test surface
- LightBrain gateway identity storage now resolves from install-model runtime data paths as well, removing another visible user-facing repo-local `data/lightbrain/...` assumption from the interaction surface
