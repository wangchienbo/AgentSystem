# Standard Install Model Architecture

## Goal

Move AgentSystem from a repo-coupled runtime to a standard install model where source code, installed runtime, mutable data, and operator state are clearly separated.

This document defines the target architecture before code migration.

---

## 1. Runtime separation model

### 1.1 Source repo responsibilities
The source repository is only responsible for:
- product development
- tests and fixtures
- packaging and build orchestration
- migration scripts
- developer-facing documentation
- compatibility wrappers during transition

The source repo must not be the default long-term home for live runtime state.

### 1.2 Installed code responsibilities
The installed runtime is responsible for:
- executable Python package/runtime entrypoints
- bundled built-in assets shipped with the product
- versioned migration helpers
- operator CLI entrypoints

Installed code should be replaceable by upgrade/reinstall without risking user state loss.

### 1.3 Runtime data responsibilities
Runtime-managed mutable state lives outside the source repo and outside the installed package tree, including:
- user data
- runtime state
- installed user assets
- logs
- caches
- local config overrides
- uploaded/generated artifacts

### 1.4 Boundary rules
At runtime, the system should treat the following as separate roots:
- code root
- config root
- data root
- state/runtime root
- cache root
- logs root
- installed-assets root

### 1.5 What is forbidden inside the source repo at runtime
The source repo should not become the default location for:
- live writable databases
- mutable runtime registries
- active session state
- logs
- caches
- user-installed assets
- uploaded files
- generated runtime artifacts

Developer-only local runs may still bridge into repo-local paths during transition, but that must be explicit and compatibility-scoped.

---

## 2. Target directory layout

## 2.1 Root selection
Primary root resolution:
1. `AGENTSYSTEM_HOME`
2. platform default under user home

Recommended default:
- `~/.local/share/agentsystem` for durable runtime home semantics on Linux-like systems

Within `AGENTSYSTEM_HOME`, use:
- `config/`
- `data/`
- `state/`
- `cache/`
- `logs/`
- `assets/installed/`
- `artifacts/`

## 2.2 Layout

```text
AGENTSYSTEM_HOME/
  config/
    config.yaml
    profiles/
  data/
    apps/
    users/
    uploads/
    exports/
  state/
    runtime/
    sessions/
    registries/
    pid/
  cache/
    model/
    temp/
    build/
  logs/
    app/
    audit/
    upgrade/
  assets/
    installed/
    runtime/
  artifacts/
    packages/
    reports/
```

## 2.3 Layout semantics
- `config/`: operator-controlled config and overrides
- `data/`: durable business/user data
- `state/`: mutable operational runtime state that can be rebuilt or migrated separately from durable user data
- `cache/`: disposable performance artifacts
- `logs/`: append-only diagnostics/audit evidence
- `assets/installed/`: user-installed packaged assets
- `assets/runtime/`: ephemeral runtime registrations/materializations if needed
- `artifacts/`: generated reports, build outputs, migration evidence

---

## 3. Environment and config resolution contract

## 3.1 Supported environment variables
- `AGENTSYSTEM_HOME`: top-level runtime home
- `AGENTSYSTEM_CONFIG_DIR`: explicit config root override
- `AGENTSYSTEM_DATA_DIR`: explicit durable data root override
- `AGENTSYSTEM_STATE_DIR`: explicit runtime state root override
- `AGENTSYSTEM_CACHE_DIR`: explicit cache root override
- `AGENTSYSTEM_LOG_DIR`: explicit logs root override
- `AGENTSYSTEM_ASSET_DIR`: explicit installed asset root override

## 3.2 Resolution order
For each runtime path:
1. explicit dedicated env var (`AGENTSYSTEM_DATA_DIR`, etc.)
2. derived path under `AGENTSYSTEM_HOME`
3. platform default path
4. temporary compatibility fallback for repo-coupled legacy mode only

## 3.3 Config contract
- main config file lives under `config/config.yaml`
- config may reference relative subpaths, interpreted relative to the resolved config/runtime home, not the source repo
- repo-relative runtime assumptions should be eliminated from production codepaths

## 3.4 Compatibility mode
During migration, the CLI may expose a compatibility mode that reports:
- current repo-coupled layout
- target standard install layout
- migration readiness gaps

---

## 4. Asset lifecycle model

## 4.1 Asset classes
### Built-in system assets
- shipped with the installed package
- versioned with the product release
- not edited in place by normal operators

### Packaged assets
- installable units produced from source/build flow
- versioned artifacts
- may be upgraded, rolled back, or reinstalled

### User-installed assets
- installed by operator action into installed asset storage
- separate from source asset development directories

### Runtime-registered assets
- temporary or dynamically materialized assets registered while the system is live
- should resolve into runtime/state boundaries, not source-repo boundaries

## 4.2 Lifecycle boundaries
- discover: inspect available packaged or built-in assets
- build: source-repo/dev action producing installable artifacts
- install: copy/register packaged asset into installed asset root
- register: make asset visible to runtime registry
- invoke: execute through stable runtime contract
- uninstall: remove installed/runtime presence while preserving policy constraints
- rollback: restore prior installed version or registry pointer

## 4.3 Boundary rules
- build is a development concern
- install/register/invoke/uninstall/rollback are operator/runtime concerns
- source asset directories are not the same thing as installed asset directories

---

## 5. Migration plan from repo-coupled model

## 5.1 Current semantics to remap
Current repo-coupled locations like:
- `source/`
- `build/`
- `installed/`
- `data/`
- repo-local logs/state/helpers

must be mapped into the standard install roots.

## 5.2 Mapping intent
- repo `source/` -> development-only source tree
- repo `build/` -> development build output or package artifact staging
- repo `installed/` -> `AGENTSYSTEM_HOME/assets/installed/`
- repo `data/` -> `AGENTSYSTEM_HOME/data/` and/or `state/` depending on semantics
- repo-local logs -> `AGENTSYSTEM_HOME/logs/`

## 5.3 Transition behavior
During transition:
- existing wrappers continue to work
- CLI reports both active legacy layout and target layout
- migration commands should be idempotent where possible
- tests should be able to run in either compatibility mode or target mode

## 5.4 Runtime state migration
Need explicit migration handling for:
- asset registries
- session/runtime state
- cached/generated files
- config file location changes
- installed asset references pointing at repo-local paths

## 5.5 Test preservation strategy
- keep current bounded user-level baseline as frozen truth set
- preserve existing harness and reports
- compare pre-migration and post-migration runs under the same bounded settings before widening acceptance scope

---

## 6. Operator-facing install model notes

Operators should be able to answer these questions without reading source code:
- where is code installed
- where is config stored
- where is durable data stored
- where are logs written
- where are installed assets stored
- how to inspect current layout
- how to migrate from repo-coupled mode
- how to back up and restore runtime home

The CLI should eventually expose these via commands such as:
- `agentsystem status`
- `agentsystem doctor`
- `agentsystem runtime-layout`
- `agentsystem migrate-runtime`
- `agentsystem assets list/install/uninstall`

---

## 7. Acceptance intent for migration phase

The install-model migration should be considered structurally correct only when:
- runtime no longer depends on repo-local mutable state by default
- operator-facing layout is explicit and inspectable
- installed assets and runtime state are separated from source development trees
- the frozen bounded pre-migration baseline can be rerun after migration for before/after comparison
