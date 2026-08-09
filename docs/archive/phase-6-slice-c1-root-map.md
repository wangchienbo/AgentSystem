# Phase 6 Slice C1 - Control-Plane Asset Treatment and Root Map

## Goal

Make the remaining repo-anchored asset/control-plane behavior explicit before moving live asset roots.

This document is the decision artifact for the first Phase 6 implementation slice.

---

## 1. Decision summary

### Decision A - repo-authored path definitions are packaged built-in control-plane assets
Current repo-owned path definitions under the project path store should be treated as:
- authored assets
- versioned with the codebase
- packaged with the installed runtime as built-in control-plane assets

They should **not** be treated as ordinary mutable runtime state.

Implications:
- bootstrap may continue loading them from a repo-owned location during transition
- the install model target is to load them from installed-package resources or a packaged built-in asset location
- optional runtime overlays can be introduced later, but the base layer remains built-in and versioned

### Decision B - source/build/installed/runtime-registry roots must be physically distinct
The install model must separate:
- development source assets
- build/package outputs
- installed runtime assets
- runtime-visible registry state

These are different concerns and should not share the same default root.

### Decision C - runtime registry persistence moves only after built-in asset bootstrap semantics are explicit
`RuntimeCenter` persistence cannot move safely until the system explains:
- which built-in assets are re-registered at startup
- which runtime-added assets persist across restarts
- what the durable truth source is for startup-required system assets

Therefore, runtime-registry persistence migration is a later slice, not part of Slice C1.

---

## 2. Root map

## 2.1 Development source root
Purpose:
- human-authored editable asset sources
- development-time manifests, blueprints, and source-side asset definitions

Root:
- repo `source/`

Status:
- remains repo-owned during development
- not the runtime-installed asset root

## 2.2 Build/package output root
Purpose:
- packaged artifacts produced from development source
- intermediate or final installable outputs

Target root:
- `AGENTSYSTEM_HOME/artifacts/build/`

Transition note:
- repo-local `build/` may remain as a developer convenience surface temporarily
- runtime should not depend on repo `build/` long term

## 2.3 Installed runtime asset root
Purpose:
- operator-installed assets used by the live runtime
- physically separate from editable development source

Target root:
- `AGENTSYSTEM_HOME/assets/installed/`

Transition note:
- repo `installed/` remains a temporary compatibility surface until Phase 6 installed-asset externalization lands

## 2.4 Built-in control-plane asset root
Purpose:
- packaged, versioned, read-mostly built-in assets that ship with AgentSystem
- includes path-definition assets and similar repo-authored control-plane resources

Target root:
- installed package resources, or a packaged built-in asset projection managed by the install/runtime layer

Transition note:
- bootstrap may still read repo-owned path definitions during transition
- final target is installed-package-owned loading, not cwd/repo-root dependency

## 2.5 Runtime registry persistence root
Purpose:
- runtime-visible asset registration state
- persisted knowledge about runtime-added or runtime-materialized assets when applicable

Target root:
- resolved state root under `AGENTSYSTEM_HOME/state/`

Transition note:
- migration intentionally deferred until built-in asset bootstrap semantics are rewritten explicitly

## 2.6 Mutable runtime data/state/log roots
Purpose:
- persistence, namespaces, caches, logs, generated callables, skill config registry, and similar runtime-managed mutable data

Target roots:
- `AGENTSYSTEM_HOME/data/`
- `AGENTSYSTEM_HOME/state/`
- `AGENTSYSTEM_HOME/cache/`
- `AGENTSYSTEM_HOME/logs/`

Status:
- largely adopted already through Slice A/B

---

## 3. Treatment rules by asset class

## Built-in control-plane assets
Examples:
- path definition YAMLs
- built-in policy/control assets shipped with the product

Rules:
- versioned with code/package
- loaded as packaged built-ins
- not treated as ordinary user-installed mutable assets
- may support overlay later, but built-in base remains authoritative

## Development source assets
Examples:
- editable repo `source/` assets under active development

Rules:
- remain in repo during authoring
- build/install flow copies or packages them into non-repo runtime locations
- runtime execution should not require direct dependence on repo source tree

## Installed runtime assets
Examples:
- assets installed by operator command or install flow

Rules:
- live under install-model installed asset root
- discover/list/run behavior should target the external installed root
- uninstall/rollback operate on this root, not repo authoring roots

## Runtime-registered assets
Examples:
- assets materialized dynamically during runtime

Rules:
- runtime visibility tracked in runtime registry layer
- persistence semantics defined separately from installed asset storage
- startup replay/persistence rules must be explicit before migration

---

## 4. What Slice C1 does not change yet

Slice C1 does **not** yet:
- move `AssetCenter` installed/build roots in live code
- migrate bootstrap path-definition loading away from repo-owned files
- migrate `RuntimeCenter` bootstrap persistence semantics
- remove legacy metadata/path compatibility behavior in `skill_asset_service.py`

Those require follow-on implementation slices after this decision artifact is accepted.

---

## 5. Immediate next implementation slice after C1

## Slice C2 - externalize installed asset root without changing built-in bootstrap semantics
Target:
- keep repo `source/` for development
- keep built-in control-plane assets bootstrapped as they are for now
- move operator-installed runtime asset root from repo `installed/` toward resolved install-model asset root

Why next:
- it is the narrowest meaningful live asset move after the root map is explicit
- it does not require solving the full built-in asset bootstrap and runtime-registry persistence problem at the same time

## Slice C3 - package built-in control-plane assets
Target:
- stop requiring repo-root path-definition loading during installed execution
- load built-in control-plane assets from installed-package resources or an equivalent packaged projection

## Slice C4 - externalize runtime registry persistence
Target:
- redefine startup re-registration rules and persist runtime-visible registry state under resolved state roots

---

## 6. Acceptance signal for Slice C1

Slice C1 is complete when:
- the control-plane asset treatment decision is written down
- the root map is explicit and referenced by the task list
- later Phase 6 implementation slices can proceed without re-debating root semantics
