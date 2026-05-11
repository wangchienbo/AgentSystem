# Standard Install Model Migration Prep Inventory

## Goal

Identify concrete repo-coupled runtime assumptions that must be changed before the standard install model migration can be implemented safely.

This is the bridge between the frozen pre-migration baseline and the first code-migration slices.

---

## 1. High-signal repo-coupled path assumptions

## 1.1 Source / build / installed asset paths
Observed in:
- `app/system/catalog/asset_center.py`
- `app/system/master/package_manager.py`
- `app/app_installer.py`
- `app/orchestration/meta_app/orchestrator.py`
- `app/system/assets/scaffold.py`
- tests asserting `source/...` values

Current coupling:
- development and runtime asset paths are expressed directly as repo-relative `source/`, `build/`, and `installed/`
- manifests and orchestration flows assume repo-root semantics

Migration implication:
- introduce a path/layout resolver so development roots and installed/runtime roots are derived from runtime config rather than string literals
- preserve manifest meaning while making runtime-installed locations independent of repo checkout

## 1.2 Data and runtime state paths
Observed in:
- `app/bootstrap/runtime.py`
- `app/persistence/runtime_state_store.py`
- `app/persistence/path_store.py`
- `app/persistence/persistence_service.py`
- `app/system/runtime/config_center.py`
- `app/system/runtime/lifecycle.py`
- `app/system/catalog/runtime_center.py`
- `app/system/catalog/system_catalog.py`
- `app/system/catalog/resource_center.py`
- `app/system/runtime/app_data_store.py`
- `app/interactive_app.py`
- `app/orchestration/pipeline_service.py`
- several tests using `data/...`

Current coupling:
- many runtime stores default directly to `data/...` repo-relative paths
- runtime, persistence, app namespaces, logs, and catalogs are scattered across literal repo paths

Migration implication:
- centralize runtime root resolution
- split durable data, mutable state, cache, and logs
- remove direct repo-relative defaults from production codepaths

## 1.3 Config resolution assumptions
Observed in:
- `app/ai/model_config_loader.py`
- CLI/runtime readiness checks

Current coupling:
- partial support already exists for `AGENTSYSTEM_HOME`, but not the wider directory family
- other runtime subsystems still default to repo-local `data/...` paths rather than using a shared resolver

Migration implication:
- extend current config-home logic into a full runtime layout resolver shared by persistence, assets, runtime state, and logs

## 1.4 Runtime-layout and doctor output
Observed in:
- `app/cli.py`
- docs and operator help text

Current coupling:
- CLI explains current repo-coupled layout but is still mostly descriptive
- runtime-layout should become the canonical user-facing projection of the new resolver

Migration implication:
- use runtime-layout/doctor as the first externally visible contract for the install model
- add tests asserting resolved roots and compatibility mode output

---

## 2. Proposed first migration implementation slices

## Slice A - Introduce shared runtime path resolver
Target:
- one module that resolves code/config/data/state/cache/log/asset roots from env vars and defaults

Why first:
- all later migration changes depend on a shared source of truth
- minimizes scattered ad hoc path rewrites

Expected touchpoints:
- bootstrap/runtime wiring
- persistence stores
- asset center defaults
- CLI runtime-layout output

## Slice B - Move runtime/persistence defaults behind resolver
Target:
- replace direct `data/...` defaults in runtime stores, catalogs, persistence services, and logs with resolved runtime roots

Why second:
- highest volume of repo-coupled runtime writes live here
- creates immediate separation between mutable runtime state and source tree assumptions

## Slice C - Split development asset roots from installed asset roots
Target:
- keep `source/` for dev/build semantics
- move installed/runtime asset defaults behind resolved install roots

Why third:
- asset lifecycle is central to the install model
- this is where repo-coupled architecture is most explicit and most user-visible

## Slice D - Align CLI/operator surfaces with the real resolver
Target:
- `runtime-layout`, `status`, `doctor`, and migration commands report actual resolved locations

Why fourth:
- operator confidence depends on inspectability
- useful checkpoint before deeper migration state transfer logic

---

## 3. Test strategy for migration implementation phase

Keep using the frozen bounded truth set from:
- `/tmp/e2e_full_50_bounded_turn5_probe.json`

During migration implementation:
- preserve existing bounded settings unless intentionally redefining acceptance
- add focused unit tests for path resolution and CLI reporting first
- only rerun larger bounded slices after a migration slice is internally stable

---

## 4. Immediate implementation recommendation

Start with **Slice A: shared runtime path resolver**.

Reason:
- it is the narrowest architectural seam with the widest downstream leverage
- it lets later code migration replace path literals incrementally instead of mixing layout design with subsystem behavior changes
- it creates a single contract that docs, CLI, runtime, persistence, and migration code can all converge on
