# Phase 6 Asset and Control-Plane Separation Plan

## Goal

Turn the remaining repo-anchored runtime boundaries into explicit migration work for Phase 6, instead of leaving them as implicit behavior.

This document narrows the next implementation seam after Slice B cleanup.

---

## 1. What is already separated

After Slice A and Slice B:
- most mutable runtime state defaults resolve through `app/runtime_paths.py`
- CLI/runtime-layout and config loading understand install-model roots
- many persistence and helper defaults no longer assume repo-local `data/...`

What remains is not generic mutable-state cleanup. It is the asset/control-plane boundary.

---

## 2. Remaining intentional repo-anchored seams

## 2.1 Repo-authored path-definition assets
Current bootstrap intentionally pins:
- `PathStore(paths_dir=os.path.join(_project_root, "data", "paths"))`

Why it still exists:
- current path YAML files are treated as repo-authored control-plane assets
- they are versioned like code and loaded as authored definitions, not mutable runtime state

Migration question:
- should path definitions remain bundled built-in assets
- or become installed assets copied into runtime-controlled storage

## 2.2 AssetCenter installed/build roots
Current bootstrap still uses repo-local:
- `installed/`
- `build/`
- repo `source/`

Why it still exists:
- asset lifecycle semantics are still tied to the source-repo development model
- startup and system-asset assumptions still expect these roots

Migration question:
- how built-in system assets, dev source assets, packaged install artifacts, and installed runtime assets should diverge physically

## 2.3 RuntimeCenter bootstrap persistence seam
Bootstrap still keeps runtime-center persistence on the current repo-backed file contract.

Why it still exists:
- startup registration and required system-asset checks depend on existing semantics
- moving it casually causes startup regressions before asset/runtime registration flow is reworked deliberately

Migration question:
- what is the durable source of truth for runtime-visible asset registration under the install model

## 2.4 Legacy compatibility in skill asset path normalization
`skill_asset_service.py` still recognizes legacy `data/...` references during transition.

Why it still exists:
- backward compatibility for previously recorded metadata/index entries

Migration question:
- when and how to migrate old metadata/index references to resolved install-model roots

---

## 3. Phase 6 work packages

## WP1 - Classify asset roots by responsibility
Define and implement separate physical roots for:
- source-authored assets in repo
- built/package artifacts
- installed runtime assets
- built-in packaged system assets
- runtime-generated or runtime-registered asset metadata

Deliverable:
- a concrete root map for `source/`, `build/`, installed assets, and runtime registry state

## WP2 - Decide control-plane asset treatment
For repo-authored path definitions and similar control-plane assets, choose one of:
- remain bundled built-in assets loaded from installed package/resources
- get copied into runtime-controlled storage during bootstrap/install
- hybrid model with read-only built-ins + operator overlay

Recommendation:
- treat them as built-in packaged assets first, with optional runtime overlay later

Why:
- preserves authored/versioned semantics
- avoids pretending they are mutable runtime state when they are not
- aligns with install-model packaging better than leaving them cwd-repo-bound

## WP3 - Externalize installed asset root
Move runtime-installed asset resolution from repo `installed/` to resolved install-model asset root.

Constraints:
- do not break required system asset startup checks
- preserve current source asset editing flow in repo during transition

Expected work:
- adjust bootstrap wiring
- adjust asset discovery/install/list behavior
- adapt tests that assume repo-installed roots

## WP4 - Externalize runtime registry persistence
Move bootstrap/runtime registry persistence off repo-backed files only after system-asset registration semantics are redefined.

Constraints:
- startup required-asset checks must still pass
- runtime-visible asset truth source must be explicit

Expected work:
- define registry bootstrap order
- define built-in asset re-registration behavior at startup
- define persisted runtime-added asset behavior across restarts

## WP5 - Migrate legacy metadata/path references
Replace compatibility-only `data/...` path normalization with explicit migration of old metadata/index records.

Expected work:
- detect legacy records
- rewrite to resolved runtime roots where appropriate
- keep bounded compatibility during migration window

---

## 4. Recommended execution order

1. **WP2 Decide control-plane asset treatment**
2. **WP1 Classify asset roots by responsibility**
3. **WP3 Externalize installed asset root**
4. **WP4 Externalize runtime registry persistence**
5. **WP5 Migrate legacy metadata/path references**

Reason:
- root classification and control-plane policy must come before moving actual asset paths
- runtime registry persistence depends on the post-classification asset lifecycle model
- legacy metadata migration should happen after the new roots are real, not before

---

## 5. Immediate next implementation recommendation

The next implementation slice should start with:

### Phase 6 Slice C1 - control-plane asset treatment decision + root map

Concrete outcome:
- decide that repo-authored path definitions are packaged built-in assets under the install model
- document the exact physical root map for source/build/installed/runtime-registry data
- update bootstrap/runtime docs to reflect that boundary before changing live asset roots

This is the cleanest next move because it converts the remaining repo-anchored behavior from accidental structure into an explicit asset/control-plane policy.
