# Generated Executable Skill Closure Plan

## Purpose

This plan extends the now-working generated/executable skill substrate into a full product path.

The target is not only to generate and run executable skills in isolation, but to make them participate in:
- refinement closure
- blueprint materialization
- app assembly / install / run
- persistence / reload
- governance / operator visibility
- template expansion

Execution should proceed in order, with each package ending in tests, docs, commit, and push.

---

## Package 1 — Closure integration (P0)

### Goal
Connect generated executable skills into the main refinement/materialization/assembly path.

### Tasks
1. refinement closure supports adapter selection policy
   - default to callable
   - allow executable when deterministic local generation is appropriate
   - preserve governance-driven fallback/block behavior
2. blueprint materialization exposes executable generation path
   - materialization response includes requested adapter, selected adapter, governance adjustment state, and reason
3. app assembly / install / run works end-to-end for generated executable skills created through the main path
4. diagnostics remain structured across materialize -> assemble -> install -> execute

### Acceptance
- suggestion/blueprint path can materialize a generated executable skill
- generated executable skill can be assembled into an app and executed
- policy pressure can block or downgrade unsafe materialization
- focused end-to-end tests pass

---

## Package 2 — Durability + consistency (P0)

### Goal
Make generated executable skills durable after reload and internally consistent across manifest/asset/registry/schema state.

### Tasks
1. reload path restores generated executable skills fully
2. schema registry re-registers generated input/output/error schemas on reload
3. asset metadata, manifest contract refs, and on-disk files stay aligned
4. add explicit consistency check coverage for generated executable assets

### Acceptance
- runtime rebuild preserves generated executable execution
- schema refs remain resolvable after reload
- consistency tests cover manifest/asset/schema alignment

---

## Package 3 — Governance + operator visibility (P1)

### Goal
Make generated/executable skill behavior inspectable and explainable from control-plane surfaces.

### Tasks
1. add generated/executable skill summary read model
2. surface origin / adapter / template / risk / contract refs / entrypoint / timeout
3. expose structured diagnostics for adapter failures and policy blocks
4. expose governance adjustment metadata from materialization/closure flows

### Acceptance
- operator/API consumers can inspect generated executable skill state without raw file reads
- policy decisions and adapter failures are visible in structured summaries

---

## Package 4 — Template expansion (P1)

### Goal
Expand generated executable scaffolding from a minimal set of templates to a practical set.

### Suggested templates
- bullet_list
- markdown_summary
- json_passthrough
- structured_extract
- field_mapper

### Acceptance
- each template has input/output/error contracts
- each template has smoke-test coverage
- scaffold docs/examples stay aligned

---

## Recommended execution order

1. Package 1 — closure integration
2. Package 2 — durability + consistency
3. Package 3 — governance + visibility
4. Package 4 — template expansion

---

## Delivery rule

Each package should end with:
- implementation
- focused tests
- docs updates
- development-log entry
- commit
- push
