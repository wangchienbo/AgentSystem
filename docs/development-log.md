# Development Log

## 2026-03-24

### Module: refinement observability API helper alignment

Aligned self-refinement operator endpoints with the workflow observability pattern by centralizing API-side filter construction for queue/stats/dashboard surfaces instead of hand-assembling filters inline.

#### Added
- `app/api/refinement_observability.py`
  - shared `build_refinement_filter(...)` helper for refinement queue/stats/dashboard endpoint parsing
- `tests/unit/test_refinement_observability_api.py`
  - verifies supported refinement query dimensions map into one shared filter contract

#### Updated
- `app/api/main.py`
  - routes refinement queue-page, failed-hypotheses-page, stats, and governance-dashboard endpoints through the shared filter helper
- `tests/unit/test_api_golden_path.py`
  - extends API golden-path coverage toward the refinement governance flow (not yet part of the validated fast slice because the broader file remains slower / timeout-sensitive)
- `docs/requirements.md`
  - records centralized refinement operator filter construction expectation
- `docs/design.md`
  - documents parity with workflow observability filter-builder structure
- `docs/testing.md`
  - records the focused helper-coverage strategy and notes the slower golden-path slice boundary

#### Validation
- fast refinement slice passes
- result: `6 passed`
- command: `./.venv/bin/pytest -q tests/unit/test_refinement_observability_api.py tests/unit/test_refinement_governance_dashboard.py tests/unit/test_refinement_filters_and_stats.py`
- note: `tests/unit/test_api_golden_path.py` was re-run separately but the broader file was interrupted by external `SIGTERM`, so that expanded golden-path assertion remained follow-up work

### Module: skill risk governance stats and dashboard

Extended the risk governance subsystem with operator-facing stats and dashboard views so reviewers and future self-iteration loops can inspect risky-skill handling through structured summaries instead of raw decision/event scans.

#### Updated
- `app/models/skill_risk_policy.py`
  - adds `SkillRiskEventPage`, `SkillRiskStatsSummary`, and `SkillRiskDashboard`
- `app/services/skill_risk_policy.py`
  - adds event-page reads, aggregated stats summary, and dashboard composition
- `app/api/main.py`
  - exposes `/skill-risk/stats` and `/skill-risk/dashboard`
- `tests/unit/test_skill_risk_dashboard.py`
  - verifies service/API risk stats and dashboard surfaces
- `docs/requirements.md`
  - records operator-facing risk stats/dashboard requirement
- `docs/design.md`
  - documents overview/stats/recent-events risk dashboard shape
- `docs/testing.md`
  - records risk governance stats/dashboard coverage
- `docs/generated-skill-roadmap.md`
  - notes dashboard reads as part of the future self-iteration substrate
- `docs/system-relationship-map.md`
  - adds risk dashboard coverage into the generated-skill relationship graph

#### Validation
- `./.venv/bin/pytest -q tests/unit/test_skill_risk_dashboard.py tests/unit/test_skill_risk_policy.py tests/unit/test_skill_risk_override_api.py`
- result: `4 passed`

### Module: skill risk governance event trail

Added a lightweight governance event trail for risky generated skills so the system now records not only the latest override decision, but also the sequence of blocks and approval/revocation actions behind it.

#### Updated
- `app/models/skill_risk_policy.py`
  - adds `SkillRiskGovernanceEvent` and explicit governance event types
- `app/services/skill_risk_policy.py`
  - persists governance events alongside decision state
  - records override approval/revocation events automatically
  - exposes governance event listing
- `app/services/skill_factory.py`
  - records `policy_blocked` governance events before raising assembly diagnostics
- `app/api/main.py`
  - exposes `/skill-risk/events` for governance event inspection
- `tests/unit/test_skill_risk_policy.py`
  - verifies governance events persist/reload with decision state
- `tests/unit/test_skill_risk_override_api.py`
  - verifies blocked and approved override events are queryable via API
- `docs/requirements.md`
  - records queryable governance event trail requirement
- `docs/design.md`
  - documents decision-state plus event-trail split
- `docs/testing.md`
  - records governance event trail coverage
- `docs/generated-skill-roadmap.md`
  - extends Phase 7 with queryable governance events for future dashboards
- `docs/system-relationship-map.md`
  - highlights policy state + event trail as a cross-cutting governance surface

#### Validation
- `./.venv/bin/pytest -q tests/unit/test_skill_risk_policy.py tests/unit/test_skill_risk_override_api.py tests/unit/test_skill_factory_risk_gating.py`
- result: `4 passed`

### Module: reviewer-managed skill risk overrides

Completed the next governance step for Phase 7 by adding persisted reviewer-managed override decisions that can intentionally unblock risky generated-skill assembly when a human (or future policy layer) approves it.

#### Added
- `app/models/skill_risk_policy.py`
  - defines persisted skill risk decision records with scope, reviewer, reason, and optional expiry
- `app/services/skill_risk_policy.py`
  - persists and reloads skill risk decisions through the runtime state store
- `tests/unit/test_skill_risk_policy.py`
  - verifies approve/list/revoke/reload behavior for persisted risk decisions
- `tests/unit/test_skill_risk_override_api.py`
  - verifies reviewer-managed API overrides can unblock generated app assembly and later be revoked

#### Updated
- `app/bootstrap/runtime.py`
  - wires `SkillRiskPolicyService` into runtime
- `app/services/skill_factory.py`
  - generated app assembly now consults active risk overrides before enforcing default deny gates
- `app/api/main.py`
  - exposes risk decision list / approve / revoke endpoints under `/skill-risk/*`
- `docs/requirements.md`
  - records reviewer-managed override requirements
- `docs/design.md`
  - documents persisted policy store + override-aware gating behavior
- `docs/testing.md`
  - records approval/override coverage expectations
- `docs/generated-skill-roadmap.md`
  - extends Phase 7 with auditable reviewer-managed unblocking
- `docs/system-relationship-map.md`
  - adds risk policy and override API tests into the generated-skill relationship map

#### Validation
- `./.venv/bin/pytest -q tests/unit/test_skill_risk_policy.py tests/unit/test_skill_risk_override_api.py tests/unit/test_skill_policy_diagnostics_api.py tests/unit/test_skill_factory_risk_gating.py`
- result: `5 passed`

### Module: structured policy diagnostics for risk-gated generated skills

Upgraded generated-skill risk gating from plain assembly errors into structured policy diagnostics so future approval or policy-override layers can reason over blocked skills programmatically.

#### Updated
- `app/models/skill_diagnostics.py`
  - adds `policy_blocked` diagnostic kind
- `app/services/skill_factory.py`
  - risk-gated generated app assembly now raises structured `SkillDiagnosticError`
  - emits stage=`assemble`, kind=`policy_blocked`, plus machine-readable `policy_reasons`
- `tests/unit/test_skill_factory_risk_gating.py`
  - now verifies service-level policy-blocked diagnostics
- `tests/unit/test_skill_policy_diagnostics_api.py`
  - verifies `/apps/from-skills` returns structured policy diagnostics for blocked risky skills
- `docs/requirements.md`
  - records structured policy diagnostic requirement for generated-skill risk gates
- `docs/design.md`
  - documents stage/kind/details shape for policy-blocked assembly diagnostics
- `docs/testing.md`
  - records policy-diagnostic coverage for generated-skill gating
- `docs/generated-skill-roadmap.md`
  - extends Phase 7 with structured blocked-path diagnostics for future approval layers
- `docs/system-relationship-map.md`
  - adds policy-diagnostic API coverage to the generated-skill relationship map

#### Validation
- `./.venv/bin/pytest -q tests/unit/test_skill_policy_diagnostics_api.py tests/unit/test_skill_factory_risk_gating.py tests/unit/test_skill_diagnostics_api.py`
- result: `9 passed`

### Module: generated app assembly risk gating

Extended Phase 7 security boundaries into the generated app assembly path so risky skills are now blocked from `/apps/from-skills` and `/apps/from-skills/install-run` by default.

#### Updated
- `app/services/skill_factory.py`
  - adds baseline generated-app risk gating before blueprint assembly
  - blocks skills whose manifest risk is high-risk or explicitly allows shell/network/filesystem-write behavior
- `tests/unit/test_skill_factory_risk_gating.py`
  - verifies safe skills still assemble into generated apps
  - verifies risky skills are rejected from generated app assembly by default
- `docs/requirements.md`
  - records default gating for risky generated app assembly/install-run paths
- `docs/design.md`
  - documents generated-app default deny behavior for risky manifests
- `docs/testing.md`
  - records generated-skill security gating coverage
- `docs/generated-skill-roadmap.md`
  - strengthens Phase 7 acceptance criteria around generated app assembly rejection
- `docs/system-relationship-map.md`
  - adds generated-skill risk-gating test coverage into the relationship map

#### Validation
- `./.venv/bin/pytest -q tests/unit/test_skill_factory_risk_gating.py tests/unit/test_skill_factory_api.py tests/unit/test_generated_callable_skill.py tests/unit/test_generated_skill_persistence.py`
- result: `13 passed`

### Module: baseline skill-manifest risk metadata and script restrictions

Started Phase 7 security groundwork by adding machine-readable manifest risk metadata and validator-enforced baseline script command restrictions for generated/runtime skills.

#### Updated
- `app/models/skill_manifest.py`
  - adds `SkillManifestRisk` with risk level plus network/filesystem/shell allowance flags
- `app/services/skill_manifest_validator.py`
  - adds allowlisted script command prefixes
  - rejects empty script commands
  - requires explicit `risk.allow_shell=true` for shell-based script adapters
  - rejects inconsistent shell-risk declarations
- `tests/unit/test_skill_manifest_validator.py`
  - adds coverage for disallowed command prefixes and shell-risk opt-in semantics
- `docs/requirements.md`
  - records manifest-level risk metadata and baseline script restriction requirements
- `docs/design.md`
  - documents risk metadata plus script command-prefix policy direction
- `docs/testing.md`
  - records skill-manifest security coverage expectations
- `docs/generated-skill-roadmap.md`
  - strengthens Phase 7 scope with explicit manifest-risk metadata as the baseline substrate
- `docs/system-relationship-map.md`
  - adds cross-cutting security note for manifest risk / script restriction changes

#### Validation
- `./.venv/bin/pytest -q tests/unit/test_skill_manifest_validator.py tests/unit/test_skill_manifest.py`
- result: `8 passed`

### Module: self-iteration docs now require relationship-map maintenance

Extended the relationship-map maintenance rule into the self-iteration and core-skill guidance docs so future generated-skill / self-evolution work treats the system map as part of the iteration substrate rather than optional documentation.

#### Updated
- `docs/generated-skill-roadmap.md`
  - adds an explicit self-iteration maintenance rule requiring `docs/system-relationship-map.md` updates in the same change set
  - adds relationship-map update status to the per-phase progress tracking checklist
- `docs/skill-design-principles.md`
  - links core-skill/runtime/self-iteration changes to mandatory `docs/system-relationship-map.md` maintenance

#### Notes
- this makes the rule visible from the documents most likely to be consulted during future self-evolution work, not only from general development docs

### Module: system-wide relationship map for modules / features / tests

Added a dedicated relationship-map document to help future change planning and self-iteration track module coupling, feature coverage, and test impact as a graph instead of relying on ad-hoc repo memory.

#### Added
- `docs/system-relationship-map.md`
  - system-wide graph covering module domains, feature-to-module-to-test mappings, operator contract relationships, and change-impact checklists

#### Updated
- `docs/code-structure.md`
  - links to the relationship map for cross-cutting dependency lookup
- `docs/testing.md`
  - points readers to the relationship map before cross-domain edits

#### Notes
- graph edges intentionally represent not only direct imports, but also runtime wiring, API exposure, shared contracts, test coverage, and “should-check-together” coupling
- this document is meant to be updated proactively whenever a new module, shared contract, or high-value test path is added
- from this point forward, `docs/system-relationship-map.md` should be treated as a required co-maintained file for structural/system changes, including future self-iteration work

### Module: centralized operator API filter builders

Centralized workflow and refinement API-side filter construction into a shared helper module so operator endpoint query semantics now evolve from one place instead of drifting across separate per-domain helper files.

#### Added
- `app/api/operator_filters.py`
  - shared workflow/refinement API filter builders with common query-dimension support
- `tests/unit/test_operator_api_filters.py`
  - verifies centralized builders preserve shared and domain-specific query semantics

#### Updated
- `app/api/main.py`
  - imports workflow/refinement filter builders from the shared operator helper module
- `app/api/workflow_observability.py`
  - now acts as a thin compatibility re-export
- `app/api/refinement_observability.py`
  - now acts as a thin compatibility re-export
- `docs/requirements.md`
  - records centralized API-filter builder direction for operator surfaces
- `docs/design.md`
  - documents shared operator filter helper organization plus temporary compatibility wrappers
- `docs/testing.md`
  - records centralized API-filter builder coverage

#### Validation
- `./.venv/bin/pytest -q tests/unit/test_operator_api_filters.py tests/unit/test_refinement_observability_api.py tests/unit/test_operator_filter_params.py tests/unit/test_workflow_observability.py`
- result: `13 passed`

### Module: shared operator dashboard core contract

Introduced a common dashboard core model for operator-facing surfaces so workflow observability and refinement governance now share the same overview/stats aggregate backbone while keeping domain-specific recent activity sections separate.

#### Added
- `app/models/operator_dashboards.py`
  - defines `OperatorDashboardCore` as the shared overview/stats aggregate contract for operator dashboards
- `tests/unit/test_operator_dashboard_core.py`
  - verifies workflow and refinement dashboard models inherit the shared core without losing their domain-specific recent sections

#### Updated
- `app/models/workflow_observability.py`
  - `WorkflowDashboardSummary` now extends `OperatorDashboardCore`
- `app/models/refinement_loop.py`
  - `RefinementGovernanceDashboard` now extends `OperatorDashboardCore`
- `docs/requirements.md`
  - records the shared dashboard-core requirement
- `docs/design.md`
  - documents the shared overview/stats backbone plus domain-specific recent sections
- `docs/testing.md`
  - records shared dashboard-core coverage

#### Validation
- `./.venv/bin/pytest -q tests/unit/test_operator_dashboard_core.py tests/unit/test_operator_filter_params.py tests/unit/test_operator_page_meta.py tests/unit/test_refinement_governance_dashboard.py tests/unit/test_workflow_observability.py`
- result: `17 passed`

### Module: shared operator filter parameter contract

Introduced a common base filter model for operator-facing surfaces so workflow observability and refinement governance now share one definition for app scope, limit, since, and cursor semantics.

#### Added
- `app/models/operator_filters.py`
  - defines `OperatorFilterParams` as the shared base query/filter contract for operator surfaces
- `tests/unit/test_operator_filter_params.py`
  - verifies workflow and refinement filters inherit the shared base semantics while keeping their domain-specific selectors

#### Updated
- `app/models/workflow_observability.py`
  - `WorkflowObservabilityFilter` now extends `OperatorFilterParams`
- `app/models/refinement_loop.py`
  - `RefinementFilter` now extends `OperatorFilterParams`
- `docs/requirements.md`
  - records shared operator filter parameter alignment
- `docs/design.md`
  - documents common filter semantics plus domain-specific selectors
- `docs/testing.md`
  - records shared operator filter coverage

#### Validation
- `./.venv/bin/pytest -q tests/unit/test_operator_filter_params.py tests/unit/test_operator_page_meta.py tests/unit/test_refinement_observability_api.py tests/unit/test_workflow_observability.py`
- result: `14 passed`

### Module: shared operator paging metadata contract

Introduced a common operator paging metadata model so workflow observability and refinement governance now share one base contract for counts/cursor state while still allowing domain-specific extensions.

#### Added
- `app/models/operator_contracts.py`
  - defines `OperatorPageMeta` as the shared operator-facing pagination metadata contract
- `tests/unit/test_operator_page_meta.py`
  - verifies both workflow and refinement page meta models extend the shared base shape

#### Updated
- `app/models/workflow_observability.py`
  - `WorkflowPageMeta` now extends `OperatorPageMeta`
- `app/models/refinement_loop.py`
  - `RefinementPageMeta` now extends `OperatorPageMeta`
- `docs/requirements.md`
  - records the shared paging metadata requirement for operator surfaces
- `docs/design.md`
  - documents common pagination semantics plus domain-specific extensions
- `docs/testing.md`
  - records shared operator page-meta coverage

#### Validation
- `./.venv/bin/pytest -q tests/unit/test_operator_page_meta.py tests/unit/test_refinement_filters_and_stats.py tests/unit/test_refinement_governance_dashboard.py tests/unit/test_workflow_observability.py`
- result: `16 passed`

### Module: refinement paging meta contract alignment

Aligned refinement governance page responses with the workflow observability contract by moving count/state fields into a structured `meta` object for queue-page and failed-hypothesis page payloads.

#### Updated
- `app/models/refinement_loop.py`
  - adds `RefinementPageMeta`; `RefinementQueuePage` and `FailedHypothesisPage` now expose `meta` instead of top-level count fields
- `app/services/refinement_memory.py`
  - now populates `returned_count`, `total_count`, `filtered_count`, and `has_more` inside `meta`
- `tests/unit/test_refinement_filters_and_stats.py`
  - verifies structured `meta` payloads on service/API reads
- `tests/unit/test_refinement_governance_dashboard.py`
  - verifies dashboard recent queue/failed slices expose structured page metadata
- `docs/requirements.md`
  - records page-meta alignment expectation between refinement governance and workflow observability
- `docs/design.md`
  - documents nested `meta` shape as the preferred operator paging contract
- `docs/testing.md`
  - records structured refinement page-meta coverage

#### Validation
- `./.venv/bin/pytest -q tests/unit/test_refinement_filters_and_stats.py tests/unit/test_refinement_governance_dashboard.py tests/unit/test_refinement_overview.py`
- result: `7 passed`

### Module: explicit runtime opt-in for model self-refiner

Shifted model-backed self-refinement from opportunistic auto-wiring to explicit runtime opt-in so normal API and regression paths stay deterministic unless model proposal synthesis is deliberately enabled.

#### Added
- `tests/unit/test_runtime_model_refiner_toggle.py`
  - verifies runtime wiring leaves the model self-refiner off by default and enables it only when `AGENTSYSTEM_ENABLE_MODEL_REFINER=1`

#### Updated
- `app/bootstrap/runtime.py`
  - now wires `ModelSelfRefiner` only when `AGENTSYSTEM_ENABLE_MODEL_REFINER=1`
- `tests/unit/test_api_refinement_governance_path.py`
  - no longer needs a disable-model flag; it simply ensures the explicit enable flag is absent while still disabling grouped regression for deterministic API coverage
- `docs/requirements.md`
  - records explicit enablement requirement for model-backed self-refinement
- `docs/design.md`
  - documents default-off / explicit-opt-in runtime wiring for the model self-refiner
- `docs/testing.md`
  - updates regression guidance to treat model-backed refinement as a separate opt-in slice

#### Validation
- `./.venv/bin/pytest -q tests/unit/test_runtime_model_refiner_toggle.py tests/unit/test_api_refinement_governance_path.py tests/unit/test_refinement_observability_api.py`
- result: `4 passed`

### Module: deterministic refinement API-path test controls

Eliminated the major performance traps in the dedicated refinement API path test by adding test-only runtime toggles that prevent accidental model-backed proposal generation and recursive grouped-regression execution during contract-focused API coverage.

#### Updated
- `app/bootstrap/runtime.py`
  - honors `AGENTSYSTEM_DISABLE_MODEL_REFINER=1` to skip wiring `ModelSelfRefiner` into runtime-built self-refinement flows
- `app/services/refinement_loop.py`
  - honors `AGENTSYSTEM_DISABLE_REFINEMENT_GROUPED_REGRESSION=1` to force checklist validation instead of invoking `scripts/run_test_groups.sh`
- `tests/unit/test_api_refinement_governance_path.py`
  - sets both test-only toggles so the refinement API path remains deterministic and fast
- `tests/unit/test_refinement_governance_dashboard.py`
  - explicitly clears grouped-regression disable state so failure-path semantics still exercise the intended stubbed regression branch
- `tests/unit/test_refinement_filters_and_stats.py`
  - explicitly clears grouped-regression disable state for the same reason
- `docs/requirements.md`
  - records deterministic test-control expectations for refinement API coverage
- `docs/design.md`
  - documents test-only opt-outs for model/refinement verification wiring
- `docs/testing.md`
  - records how refinement API-path tests should disable remote/full-suite paths when validating contracts

#### Validation
- dedicated refinement API path passes quickly after toggles are applied
- focused slice A: `./.venv/bin/pytest -q tests/unit/test_api_refinement_governance_path.py tests/unit/test_refinement_observability_api.py`
  - result: `2 passed`
- focused slice B: `./.venv/bin/pytest -q tests/unit/test_refinement_governance_dashboard.py tests/unit/test_refinement_filters_and_stats.py`
  - result: `5 passed`
- diagnostic finding during investigation:
  - `/self-refinement/propose` had been slowed by model-refiner availability/probe logic
  - `/self-refinement/loop` had been slowed by auto-invocation of grouped regression via `scripts/run_test_groups.sh`

### Module: refinement API governance path test split

Split the slower refinement API end-to-end path out of the main golden-path file so the common workflow golden-path regression stays compact while the refinement governance path can be validated independently.

#### Added
- `tests/unit/test_api_refinement_governance_path.py`
  - dedicated refinement API path from review/propose/loop into stats and governance dashboard

#### Updated
- `tests/unit/test_api_golden_path.py`
  - restored to the workflow-observability golden path only
- `docs/testing.md`
  - records the fast-slice vs slower dedicated API-path split
- `docs/design.md`
  - notes the dedicated slower refinement integration slice pattern

#### Validation
- structural split completed; dedicated API path remains a slower test slice and was not included in the fast validated subset yet

### Module: self-refinement governance dashboard summary

Added a higher-level governance dashboard read model for self-refinement so operator-facing surfaces can fetch one composed payload instead of manually joining overview, stats, queue pages, and failed-hypothesis pages.

#### Added
- `tests/unit/test_refinement_governance_dashboard.py`
  - verifies governance dashboard aggregation and API response shape

#### Updated
- `app/models/refinement_loop.py`
  - adds `RefinementGovernanceDashboard`
- `app/services/refinement_memory.py`
  - adds governance dashboard aggregation built from overview, stats, recent queue, and recent failed-hypothesis slices
- `app/api/main.py`
  - exposes `/self-refinement/governance-dashboard`
- `docs/requirements.md`
  - records dashboard-style refinement governance read model expectation
- `docs/design.md`
  - documents governance dashboard composition
- `docs/testing.md`
  - records combined dashboard coverage expectations

#### Validation
- focused refinement governance/dashboard regression slice passes
- result: `11 passed`
- command: `./.venv/bin/pytest -q tests/unit/test_refinement_governance_dashboard.py tests/unit/test_refinement_filters_and_stats.py tests/unit/test_refinement_rollout.py tests/unit/test_refinement_dashboard.py tests/unit/test_refinement_overview.py`

### Module: self-refinement governance filter/stat read models

Extended the refinement governance layer with filtered read models and aggregate stats so operator-facing surfaces can inspect rollout state and failed-learning history without scanning raw full lists.

#### Added
- `tests/unit/test_refinement_filters_and_stats.py`
  - verifies queue-page filtering, failed-hypothesis archive paging, and aggregate stats summaries across service/API paths

#### Updated
- `app/models/refinement_loop.py`
  - adds `RefinementFilter`, `RefinementStatsSummary`, `RefinementQueuePage`, and `FailedHypothesisPage`
- `app/services/refinement_memory.py`
  - adds filtered queue-page reads, failed-hypothesis page reads, aggregate stats summaries, and shared internal filter helpers
- `app/api/main.py`
  - exposes `/self-refinement/rollout-queue-page`, `/self-refinement/failed-hypotheses-page`, and `/self-refinement/stats`
- `docs/requirements.md`
  - records refinement-governance filtered page/stats requirement direction
- `docs/design.md`
  - documents refinement-governance operator read models
- `docs/testing.md`
  - records coverage expectations for refinement filtering/stats surfaces

#### Validation
- focused refinement governance regression slice passes
- result: `9 passed`
- command: `./.venv/bin/pytest -q tests/unit/test_refinement_filters_and_stats.py tests/unit/test_refinement_rollout.py tests/unit/test_refinement_dashboard.py tests/unit/test_refinement_overview.py`

## 2026-03-23

### Module: failure-aware refinement gating

Connected negative learning history back into the refinement decision process. The system now analyzes previously failed hypotheses before forming a new hypothesis, marks repeated attempts with repeat-risk metadata, and prevents naive promotion when a strategy resembles a disproven path.

#### Added
- `app/services/refinement_failure_analysis.py`
  - scores failure similarity and produces repeat-risk / gating metadata
- `tests/unit/test_refinement_failure_awareness.py`
  - verifies failed-hypothesis history raises repeat risk and blocks promotion on repeated strategies

#### Updated
- `app/models/refinement_loop.py`
  - adds repeat-risk / related-failure metadata on hypotheses and gating metadata on verification results
- `app/services/refinement_loop.py`
  - consults failed-hypothesis history before forming hypotheses and gates promotion when repeat risk is not low
- `tests/unit/test_refinement_dashboard.py`
  - validates repeat-risk visibility in dashboard history
- `docs/design.md`
  - documents failure-aware refinement gating
- `docs/testing.md`
  - records repeated-hypothesis gating coverage

#### Validation
- failure-awareness, dashboard, and refinement-loop regression slice passes
- result: `5 passed`

### Module: refinement dashboard history and failed-hypothesis archive

Added the next learning-layer read model on top of refinement governance. The system now preserves failed hypotheses as first-class records and exposes dashboard/history views so recent learning activity is readable, not just stored as disconnected lists.

#### Added
- `tests/unit/test_refinement_dashboard.py`
  - verifies failed-hypothesis archival and dashboard/history aggregation

#### Updated
- `app/models/refinement_loop.py`
  - adds `FailedHypothesisRecord` and `RefinementDashboard`
- `app/services/refinement_memory.py`
  - persists failed hypotheses, builds dashboard/history views, and extends overview counts with negative-learning state
- `app/services/refinement_loop.py`
  - archives failed hypotheses when verification fails
- `app/api/main.py`
  - exposes refinement dashboard and failed-hypotheses endpoints
- `docs/design.md`
  - documents failed-hypothesis preservation and dashboard visibility expectations
- `docs/testing.md`
  - records dashboard/history regression coverage

#### Validation
- refinement overview, dashboard, and rollout regression slice passes
- result: `6 passed`

### Module: refinement rollout queue lifecycle

Extended the rollout queue skeleton into a governed lifecycle. Queue items can now transition through approve/apply/reject/rollback operations, and the rollout service provides an explicit operational layer above the raw queue store.

#### Added
- `app/services/refinement_rollout.py`
  - manages rollout queue lifecycle transitions and delegates apply actions through proposal review
- `tests/unit/test_refinement_rollout.py`
  - verifies queue lifecycle transitions and rollout queue API availability

#### Updated
- `app/bootstrap/runtime.py`
  - wires the refinement rollout service into runtime
- `app/api/main.py`
  - exposes rollout queue transition endpoints
- `tests/unit/test_refinement_overview.py`
  - covers overview API surface
- `docs/design.md`
  - records explicit rollout lifecycle expectations
- `docs/testing.md`
  - records rollout lifecycle regression coverage

#### Validation
- refinement loop, overview, and rollout regression slice passes
- result: `6 passed`

### Module: refinement rollout queue and overview read model

Added the first governance layer on top of the refinement loop. Rollout is now represented as a queue item instead of only an ephemeral decision, and refinement state can be summarized into an overview read model for operational visibility.

#### Added
- `tests/unit/test_refinement_overview.py`
  - verifies queue state and latest learning-loop artifacts are aggregated into the overview read model

#### Updated
- `app/models/refinement_loop.py`
  - adds `RolloutQueueItem`, `RefinementOverview`, and queue attachment on loop results
- `app/services/refinement_memory.py`
  - persists rollout queue items and builds per-app overview summaries
- `app/services/refinement_loop.py`
  - emits rollout queue items during loop execution and marks auto-applied promotions accordingly
- `app/api/main.py`
  - exposes rollout queue and refinement overview endpoints
- `tests/unit/test_refinement_loop.py`
  - validates queue emission and queue/list API coverage
- `docs/design.md`
  - documents rollout governance and overview visibility expectations
- `docs/testing.md`
  - records refinement overview/dashboard coverage

#### Validation
- refinement loop, persistence, and overview regression slice passes
- result: `4 passed`

### Module: pluggable refinement verification execution

Resolved the timeout trap introduced by wiring refinement verification to the grouped regression runner. Verification execution is now injectable, so runtime paths can still call the real grouped runner while unit tests use a bounded stub executor and remain deterministic.

#### Updated
- `app/services/refinement_loop.py`
  - adds injectable `verification_executor`
  - keeps grouped regression as the runtime-capable default path
  - preserves auto-apply rollout behavior for low-risk promoted proposals
- `tests/unit/test_refinement_loop.py`
  - uses a stub verification executor for fast deterministic unit coverage
  - narrows API coverage to query/list surfaces while service-level tests continue to exercise the full loop
- `tests/unit/test_refinement_loop_persistence.py`
  - uses a stub verification executor during persistence coverage
- `docs/design.md`
  - documents pluggable verification execution as a design rule
- `docs/testing.md`
  - records the bounded-executor testing strategy for refinement verification

#### Validation
- refinement-loop, persistence, and proposal-review regression slice passes
- result: `5 passed`

### Module: refinement loop persistence and query surfaces

Extended the refinement learning loop from a transient skeleton into a visible, queryable runtime layer. Refinement hypotheses, experiments, verifications, and rollout decisions now persist through the runtime store and can be listed back through dedicated API endpoints.

#### Added
- `tests/unit/test_refinement_loop_persistence.py`
  - verifies refinement-loop artifacts survive runtime rebuild and remain queryable

#### Updated
- `app/services/refinement_memory.py`
  - persists and reloads hypotheses / experiments / verifications / decisions through `RuntimeStateStore`
- `app/bootstrap/runtime.py`
  - wires refinement memory against the runtime store
- `app/api/main.py`
  - exposes list endpoints for hypotheses, experiments, verifications, and rollout decisions
- `tests/unit/test_refinement_loop.py`
  - validates the new query endpoints after loop execution
- `docs/design.md`
  - records persistence/query expectations for refinement-loop artifacts
- `docs/testing.md`
  - records persistence/query regression coverage for the refinement loop

#### Validation
- refinement-loop, persistence, self-refinement, and priority-analysis regression slice passes
- result: `9 passed`

### Module: refinement learning loop skeleton

Added the first explicit domain layer for turning runtime contradiction analysis into inspectable improvement actions. The system can now convert prioritized refinement proposals into hypothesis, experiment, verification, and rollout objects through a dedicated service/API path.

#### Added
- `app/models/refinement_loop.py`
  - defines `RefinementHypothesis`, `RefinementExperiment`, `VerificationResult`, `RolloutDecision`, and the loop request/result contracts
- `app/services/refinement_memory.py`
  - in-memory store for refinement loop objects
- `app/services/refinement_loop.py`
  - converts prioritized proposals into bounded refinement loop artifacts and rollout recommendations
- `tests/unit/test_refinement_loop.py`
  - covers both service-level and API-level refinement loop flow

#### Updated
- `app/bootstrap/runtime.py`
  - wires refinement memory + refinement loop service into the runtime
- `app/api/main.py`
  - exposes `/self-refinement/loop`
- `docs/design.md`
  - documents hypothesis/experiment/verification/rollout as first-class refinement objects
- `docs/testing.md`
  - records refinement-loop coverage

#### Validation
- refinement-loop, self-refinement, and priority-analysis regression slice passes
- result: `8 passed`

### Module: generated-app durability and grouped regression runner

Added the next layer of system-level guardrails: generated apps now have an explicit runtime-rebuild durability regression, and the project now has a stable grouped regression runner so full validation does not depend on a single long-lived pytest process.

#### Added
- `tests/unit/test_generated_app_durability.py`
  - verifies a generated app blueprint remains executable after runtime rebuild when generated skills are reloaded, the blueprint is re-registered, and app namespaces are reprovisioned
- `scripts/run_test_groups.sh`
  - runs the test suite in stable grouped slices (`core`, `runtime`, `context_data`, `workflows`, `intelligence`, `generated`, `operator_paths`) to avoid environment timeout issues during monolithic suite runs

#### Updated
- `docs/requirements.md`
  - documents a disciplined observation -> synthesis -> experiment -> verification improvement loop for practical system intelligence
- `docs/design.md`
  - reframes evolution from practice as an evidence-bound investigate -> hypothesize -> test -> rollout loop
- `docs/testing.md`
  - records generated-app durability coverage and grouped regression execution strategy

#### Validation
- focused durability/operator regression slice passes
- result: `6 passed`
- grouped regression runner passes all groups:
  - `core`: 24 passed
  - `runtime`: 31 passed
  - `context_data`: 18 passed
  - `workflows`: 30 passed
  - `intelligence`: 15 passed
  - `generated`: 28 passed
  - `operator_paths`: 11 passed

### Module: API golden path and generated-skill durability guardrails

Added the next layer of regression guardrails above the earlier service/bootstrap coverage: one test now exercises the main operator flow strictly through the public API surface, and another verifies generated script skills remain durable across runtime rebuilds.

#### Added
- `tests/unit/test_api_golden_path.py`
  - verifies registry -> install -> execute -> retry -> diagnostics -> overview -> dashboard through FastAPI endpoints
- `tests/unit/test_generated_skill_durability.py`
  - verifies persisted generated script skills reload after runtime rebuild and still execute successfully

#### Updated
- `docs/testing.md`
  - records API-level golden-path coverage and generated-skill durability smoke coverage

#### Validation
- targeted regression slice passes for the new API/durability tests plus prior bootstrap/golden-path coverage
- result: `5 passed`
- note: full-suite reruns in this environment were interrupted by external SIGTERM timeout rather than assertion failures

### Module: bootstrap smoke and golden-path integration guardrails

Added regression guardrails for the two most important framework-level paths: fresh-runtime bootstrap/demo installability and the main operator golden path through interaction, workflow execution, retry, and observability.

#### Added
- `tests/unit/test_bootstrap_smoke.py`
  - verifies built-in skill registration and demo catalog registration in a fresh runtime
  - verifies default workspace/pipeline demo blueprints remain installable after bootstrap
- `tests/unit/test_golden_path_integration.py`
  - exercises registry/catalog wiring, interaction-driven app open, workflow execution, retry, diagnostics, overview, and dashboard summary flow in one integrated test

#### Updated
- `docs/testing.md`
  - records bootstrap smoke coverage and golden-path operator coverage as regression guardrails

#### Validation
- targeted new regressions pass
- full local suite passes
- result: `158 passed`

### Module: workflow observability closure and install-time validation split

Closed the main workflow observability integration loop by reconciling retry semantics, timeline compatibility, demo blueprint installability, and strict-vs-relaxed blueprint validation behavior.

#### Updated
- `app/bootstrap/catalog.py`
  - made demo catalog blueprints self-consistent under current bootstrap assumptions by providing minimal roles and removing optional undeclared required-skill dependencies from the default workspace/pipeline blueprints
- `app/services/blueprint_validation.py`
  - split validation behavior into strict operator-facing validation and relaxed install-time validation
  - strict `/blueprints/validate` still reports missing `roles` and undeclared runtime skills
  - install-time validation now enforces declared dependencies/contracts without blocking intentionally partial runtime workflows that reference undeclared step skills
- `app/services/workflow_executor.py`
  - retry now targets the latest `partial` execution rather than only executions surfaced through the recent-failure helper
- `app/models/workflow_observability.py`
  - timeline page model now preserves list-like compatibility (`len`, iteration, indexing) while retaining paginated page metadata
- `app/services/skill_factory.py`
  - clarified invalid step-mapping diagnostics so client-visible error text matches retry-guidance expectations
- `docs/design.md`
  - documented the strict-vs-relaxed validation split, partial-as-retry-target semantics, and timeline compatibility expectations
- `docs/testing.md`
  - recorded regression coverage for the validation split, partial retry semantics, and timeline page compatibility

#### Validation
- focused regressions pass for blueprint validation, observability APIs, and workflow executor flows
- full local suite passes
- result: `155 passed`

## 2026-03-21

### Module: auto-applied high-confidence generated mappings

Extended generated app assembly so high-confidence adjacent-step mapping suggestions are compiled into workflow inputs automatically when no explicit user wiring already occupies the target.

#### Updated
- `app/services/skill_factory.py`
  - auto-applies high-confidence suggested mappings into compiled step inputs before explicit mappings are layered on top
  - preserves explicit `step_mappings` and hand-authored `step_inputs` as higher-priority sources of truth
- `app/services/generated_callable_materializer.py`
  - adds a lightweight `echo_object_keys` generated callable operation for top-level input wiring validation
- `tests/unit/test_skill_factory_api.py`
  - validates install-run succeeds through auto-applied schema-safe mappings without hand-authored wiring
- `docs/requirements.md`
  - records auto-apply behavior for high-confidence safe mappings
- `docs/design.md`
  - documents conservative auto-apply boundaries
- `docs/testing.md`
  - records install-run coverage for auto-applied mapping suggestions

#### Validation
- focused generated app auto-apply regression added alongside explicit mapping/suggestion regressions

### Module: generated mapping suggestions

Added conservative schema-based mapping suggestion support to generated app assembly so adjacent-step field matches can be surfaced without automatically rewriting user intent.

#### Updated
- `app/models/skill_creation.py`
  - `AppFromSkillsResult` now returns `suggested_mappings` and `unresolved_inputs`
- `app/services/skill_factory.py`
  - computes safe adjacent-step mapping suggestions from output/input schema matches
  - reports unresolved required downstream inputs when no safe prior-step source exists
  - keeps explicit user mappings authoritative and suggestion-only logic non-invasive
- `tests/unit/test_skill_factory_api.py`
  - covers suggested mapping and unresolved-input reporting for generated app assembly
- `docs/requirements.md`
  - records schema-based suggestion/unresolved-input expectations for generated apps
- `docs/design.md`
  - documents conservative non-auto-applied suggestion behavior
- `docs/testing.md`
  - records API coverage for generated mapping suggestions

#### Validation
- focused generated app suggestion regressions pass alongside existing explicit mapping and transform/default flows

### Module: generated mapping transforms and defaults

Extended generated app composition with lightweight transform/default support so common multi-step wiring cleanup can be expressed directly in the API-facing assembly request.

#### Updated
- `app/models/skill_creation.py`
  - `StepMappingDefinition` now supports `transform` and `default_value`
- `app/services/skill_factory.py`
  - compiles mapping defaults and literal injections into workflow-native reference objects
  - validates supported transform set during generated app assembly
- `app/services/workflow_executor.py`
  - resolves generated mapping transforms/defaults at execution time through the existing workflow reference path
- `app/services/blueprint_validation.py`
  - validates literal/default mapping compatibility against downstream schemas
- `tests/unit/test_skill_factory_api.py`
  - covers a two-step generated app flow using uppercase/lowercase transforms and literal default injection
- `tests/unit/test_skill_diagnostics_api.py`
  - rejects unsupported transform requests as client-facing 400 errors

#### Validation
- focused generated app transform/default regressions added for supported and unsupported mapping declarations

### Module: runtime snapshot JSON fault tolerance

Hardened runtime snapshot loading so empty or malformed JSON files no longer crash bootstrap, API import, or tests that rely on file-backed runtime state.

#### Updated
- `app/services/runtime_state_store.py`
  - `load_json()` now falls back to the caller-provided default when a snapshot file is unreadable, empty, or malformed
  - invalid snapshot files are quarantined under `data/runtime/corrupted/` (or the active runtime-store base dir) instead of being left in place to repeatedly break startup
- `tests/unit/test_context_runtime_view_serialization.py`
  - adds regression coverage for empty and malformed runtime snapshot files

#### Validation
- targeted runtime-store fault-tolerance regression added for empty and invalid JSON snapshots

### Module: generated multi-step app mapping support

Extended the API-first generated app path so generated skills can be composed into multi-step apps through explicit mapping declarations instead of only static per-step input blobs.

#### Added
- `app/models/skill_creation.py`
  - `StepMappingDefinition`
  - request support for `step_inputs` and `step_mappings` on generated app assembly
- `tests/unit/test_skill_factory_api.py`
  - validates a real two-step generated app flow using script + callable skills with explicit step/output and workflow-input mappings
- `tests/unit/test_skill_diagnostics_api.py`
  - validates malformed generated-app mapping requests are rejected as 400-level API errors

#### Updated
- `app/services/skill_factory.py`
  - compiles generated mapping declarations into workflow-native `$from_step` / `$from_inputs` references
  - supports nested target-field mapping into downstream input payloads
  - rejects malformed or unknown-step mapping declarations during app assembly
- `app/services/blueprint_validation.py`
  - resolves nested target paths during compile-time schema compatibility checks
  - avoids false mismatches when mappings target nested object fields rather than top-level fields only
- `app/api/main.py`
  - surfaces `SkillFactoryError` from generated app assembly/install-run as mapped API errors
- `app/core/errors.py`
  - maps `SkillFactoryError` into ordinary client-facing domain errors instead of leaking 500s
- `docs/requirements.md`
  - records generated multi-step app mapping requirements
- `docs/design.md`
  - documents generated mapping compilation into workflow-native references
- `docs/testing.md`
  - records multi-step mapping coverage and malformed-request diagnostics

#### Validation
- focused regression passes:
  - `test_create_multi_step_generated_app_with_step_mappings`
  - `test_app_from_skills_rejects_invalid_step_mapping_request`
  - `test_blueprint_validation_rejects_incompatible_prior_skill_output_mapping`

## 2026-03-20

### Module: skill authoring scaffold for self-iterating normal skills

Added a small authoring helper layer so ordinary deterministic/script skills can be created through a consistent packaging path instead of repeating registry + manifest boilerplate by hand.

#### Added
- `app/services/skill_authoring.py`
  - `SkillAuthoringSpec`
  - `SkillAuthoringService`
  - helper builders for callable and script-backed skills
- `tests/unit/test_skill_authoring.py`
  - validates callable entry generation
  - validates script entry generation
  - validates capability/dependency preservation

#### Updated
- `app/services/system_skill_registry.py`
  - built-in skills now build manifests through the same authoring helper path used for ordinary skills
- `docs/requirements.md`
  - documented need for a low-friction normal-skill authoring path
- `docs/design.md`
  - documented authoring service as part of skill packaging
- `docs/testing.md`
  - recorded authoring-helper coverage in the current test matrix

#### Validation
- planned focused regression: skill authoring + system skill registry + runtime adapter tests

### Module: API-first generated skill creation and app assembly

Implemented a first minimal interface-driven path for creating a skill, registering schemas/contracts, smoke-executing the skill through runtime, and assembling registered skills into a generated app blueprint.

#### Added
- `app/models/skill_creation.py`
  - API request/response models for generated skills and app assembly
- `app/services/skill_factory.py`
  - `SkillFactoryService`
  - contract registration during creation
  - runtime smoke-test execution after creation
  - app-blueprint assembly from registered skills
- `tests/unit/test_skill_factory_api.py`
  - verifies `/skills/create` for generated script skills
  - verifies smoke execution result
  - verifies `/apps/from-skills` blueprint assembly and registry insertion

#### Updated
- `app/bootstrap/runtime.py`
  - wires `SkillFactoryService` into runtime services
- `app/api/main.py`
  - adds `/skills/create`
  - adds `/apps/from-skills`
- `docs/requirements.md`
  - records API-first generated skill requirements
- `docs/design.md`
  - documents skill factory packaging/execution path
- `docs/testing.md`
  - records API-driven skill creation coverage

#### Validation
- focused API/authoring/runtime regression passes
- result: `12 passed`

### Module: generated app install/run validation and real script skill verification

Extended the generated-skill path so the interface flow can also install and execute the generated app immediately, then validated the path with a more realistic script skill instead of only an echo-style fixture.

#### Added
- `tests/fixtures/script_slugify_skill.py`
  - a real script-backed text normalization skill that generates storage-safe slugs

#### Updated
- `app/models/skill_creation.py`
  - install/run request now supports step-level inputs
- `app/api/main.py`
  - adds `/apps/from-skills/install-run`
- `app/services/skill_factory.py`
  - generated app blueprints now include a minimal role
  - generated step inputs can be attached during app assembly
  - generated input schemas auto-allow runtime `working_set` injection
- `tests/unit/test_skill_factory_api.py`
  - validates create -> assemble -> install -> run
  - validates a more realistic `skill.text.slugify` script skill end-to-end
- `docs/requirements.md`
  - records optional install+execute flow in generated skill path
- `docs/design.md`
  - documents early visibility of generated app execution mismatches
- `docs/testing.md`
  - records non-trivial generated skill coverage

#### Validation
- focused generated-skill regression passes
- result: `13 passed`

### Module: retry advice for generated skill diagnostics

Extended the structured diagnostics baseline into a first retry/recovery contract so failed generated-skill flows can produce suggested correction payloads.

#### Added
- `app/services/skill_retry_advisor.py`
  - converts structured diagnostics into suggested retry requests
- retry-advice API route:
  - `POST /skills/diagnose-retry`

#### Updated
- `app/models/skill_diagnostics.py`
  - diagnostics can now carry `suggested_retry_request`
  - added retry advice request/response models
- `app/services/skill_factory.py`
  - create-phase diagnostics now include suggested retry payloads
- `app/api/main.py`
  - install/execute diagnostics now include suggested retry payloads where applicable
- `tests/unit/test_skill_diagnostics_api.py`
  - validates retry suggestion payloads through the API
- `docs/requirements.md`
  - records retry advice requirement
- `docs/design.md`
  - documents suggested retry requests in diagnostics
- `docs/testing.md`
  - records retry-advice coverage
- `docs/generated-skill-roadmap.md`
  - marks Phase 3 acceptance criteria for retry payloads as complete

#### Validation
- focused diagnostics + retry regression passes
- result: `4 passed`

### Module: generated skill persistence and reload baseline

Implemented the first durability slice for generated skills so API-created script skills can persist as assets and be reloaded into a rebuilt runtime.

#### Added
- `app/services/generated_skill_assets.py`
  - persists generated skill assets into `global:skill_assets`
  - lists generated assets for reload
- `tests/unit/test_generated_skill_persistence.py`
  - validates create -> persist -> rebuild runtime -> reload -> execute

#### Updated
- `app/services/skill_factory.py`
  - persists generated skill metadata/assets on creation
  - can reload generated skills back into registry/runtime
- `app/bootstrap/runtime.py`
  - wires generated asset store and reload on bootstrap
- `docs/requirements.md`
  - records persistence/reload requirement for generated skills
- `docs/design.md`
  - documents durable generated skill asset behavior
- `docs/testing.md`
  - records reload regression coverage

#### Validation
- focused persistence/generated-skill regression passes
- result: `5 passed`

### Module: generated skill roadmap and phased delivery plan

Captured the next-step implementation order for generated skill/app self-iteration so future work can proceed as a staged roadmap instead of ad-hoc feature growth.

#### Added
- `docs/generated-skill-roadmap.md`
  - current baseline
  - phase ordering
  - acceptance criteria per phase
  - suggested validation cases
  - immediate next 3 tasks

#### Validation
- roadmap reflects the currently proven generated script-skill baseline and the known framework gaps exposed by real-skill validation


## 2026-03-16

### Module: lifecycle manager and runtime host

Implemented a first minimal runtime lifecycle layer for persistent app management.

#### Added
- `app/services/lifecycle.py`
  - `AppLifecycleService`
  - deterministic app lifecycle transition rules
  - lifecycle event recording
- `app/services/runtime_host.py`
  - `AppRuntimeHostService`
  - runtime lease tracking
  - task queue tracking
  - checkpoint generation
  - healthcheck and restart-count bookkeeping
- `app/models/runtime.py`
  - `LifecycleEvent`
  - `RuntimeCheckpoint`
  - `RuntimeLease`
  - `LifecycleTransitionResult`
  - `RuntimeOverview`

#### API endpoints added
- `GET /apps`
- `POST /apps`
- `GET /apps/{app_instance_id}`
- `GET /apps/{app_instance_id}/events`
- `POST /apps/{app_instance_id}/actions/{action}`
- `POST /apps/{app_instance_id}/tasks`
- `POST /apps/{app_instance_id}/healthcheck`
- `GET /apps/{app_instance_id}/runtime`

#### Updated
- `app/core/errors.py`
  - added lifecycle/runtime error mapping
- `app/api/main.py`
  - wired lifecycle and runtime host services into FastAPI

#### Tests
- added `tests/unit/test_lifecycle_runtime.py`
- validated:
  - legal lifecycle transitions
  - invalid transition rejection
  - runtime start/pause/resume/stop
  - healthcheck + pending task queue
  - runtime API flow
  - 404/400 error mapping

#### Validation
- Created local virtual environment: `.venv`
- Installed package in editable mode with dev dependencies
- Ran test suite successfully
- Result: `24 passed`

### Module: scheduler and supervisor services

Implemented a first minimal scheduling and supervision layer for long-running app hosting.

#### Added
- `app/models/scheduling.py`
  - `ScheduleRecord`
  - `ScheduleTriggerResult`
  - `SupervisionPolicy`
  - `SupervisionStatus`
  - `SupervisionActionResult`
- `app/services/scheduler.py`
  - interval schedule registration
  - event-triggered schedule registration
  - pause / resume / disable controls
  - task enqueue on trigger
- `app/services/supervisor.py`
  - supervision policy registration
  - failure observation
  - restart attempt logic
  - open-circuit protection
  - supervision status reset

#### API endpoints added
- `GET /schedules`
- `POST /schedules`
- `POST /schedules/trigger/interval`
- `POST /schedules/trigger/event`
- `POST /schedules/{schedule_id}/pause`
- `POST /schedules/{schedule_id}/resume`
- `POST /schedules/{schedule_id}/disable`
- `POST /supervision/policies`
- `GET /supervision/{app_instance_id}`
- `POST /supervision/{app_instance_id}/observe-failure`
- `POST /supervision/{app_instance_id}/attempt-restart`
- `POST /supervision/{app_instance_id}/reset`

#### Updated
- `app/api/main.py`
  - wired scheduler and supervisor services into FastAPI
- `app/core/errors.py`
  - added scheduler/supervisor error mapping

#### Tests
- added `tests/unit/test_scheduler_supervisor.py`
- validated:
  - interval schedule trigger
  - event schedule validation
  - supervision failure observation
  - restart flow
  - circuit-open protection
  - scheduler/supervisor API flow

#### Validation
- Reused local virtual environment: `.venv`
- Ran test suite successfully
- Result: `29 passed`

### Module: interaction gateway and runtime persistence

Implemented a first user-facing command gateway plus minimal file-based runtime persistence.

#### Added
- `app/models/interaction.py`
  - `AppCatalogEntry`
  - `UserCommand`
  - `InteractionDecision`
- `app/services/app_catalog.py`
  - app catalog registry
  - trigger phrase matching
- `app/services/interaction_gateway.py`
  - main user command entry
  - service app open flow
  - pipeline app one-shot run flow
  - fallback clarify decision when no app matches
- `app/services/runtime_state_store.py`
  - JSON file persistence for runtime state collections and mappings

#### Updated
- `app/services/lifecycle.py`
  - persist app instances and lifecycle events
- `app/services/runtime_host.py`
  - persist leases, checkpoints, and pending tasks
- `app/services/scheduler.py`
  - persist schedules
- `app/services/supervisor.py`
  - persist supervision policies and statuses
- `app/api/main.py`
  - added catalog listing endpoint
  - added interaction command endpoint
  - added runtime persistence snapshot endpoint
  - wired a default service app and pipeline app into the catalog
- `app/core/errors.py`
  - added app catalog domain error mapping

#### API endpoints added
- `GET /catalog/apps`
- `POST /interaction/command`
- `GET /runtime/persistence`

#### Behavior added
- user commands can now be routed to:
  - open a long-running service app
  - execute a one-shot pipeline app
  - return a clarify response when no app is matched
- runtime state now persists to `data/runtime/*.json`

#### Tests
- added `tests/unit/test_interaction_gateway.py`
- validated:
  - service app command routing
  - pipeline app command routing
  - clarify fallback
  - runtime persistence file creation
  - interaction API and persistence snapshot

#### Validation
- Reused local virtual environment: `.venv`
- Ran test suite successfully
- Result: `34 passed`

### Module: app registry, installer, and runtime policy alignment

Aligned the architecture around OS-style boundaries: skill as reusable capability, blueprint as definition, instance as lifecycle object.

#### Added
- `app/models/runtime_policy.py`
  - execution mode
  - activation mode
  - restart policy
  - persistence level
  - idle strategy
- `app/models/registry.py`
  - registry entry model
  - install result model
- `app/services/app_registry.py`
  - blueprint registration
  - registry listing
  - blueprint lookup
  - persistence to runtime store
- `app/services/app_installer.py`
  - blueprint -> instance installation flow
  - instance creation with execution mode and runtime policy
  - lifecycle transitions through validate / compile / install

#### Updated
- `app/models/app_blueprint.py`
  - added `runtime_policy`
- `app/models/app_instance.py`
  - added `execution_mode`
  - added `runtime_policy`
- `app/services/interaction_gateway.py`
  - now routes through installer instead of directly constructing instances
- `app/api/main.py`
  - added registry endpoints
  - preloaded example blueprints into registry
  - interaction path now depends on registry + installer flow
- `app/core/errors.py`
  - added registry / installer error mapping
- `README.md`
  - updated current prototype status
- `docs/design.md`
  - added boundary clarification for skill / blueprint / app instance / data layers

#### API endpoints added
- `GET /registry/apps`
- `POST /registry/apps`
- `POST /registry/apps/{blueprint_id}/install`

#### Behavior added
- service/pipeline mode now belongs to runtime policy instead of being only a catalog convention
- app interaction now installs from registered blueprints before runtime activation
- registry data and blueprints are persisted into runtime store snapshots

#### Tests
- added `tests/unit/test_registry_installer.py`
- updated `tests/unit/test_interaction_gateway.py`
- validated:
  - blueprint registration
  - install flow
  - runtime policy propagation into app instance
  - registry API flow
  - interaction gateway installer-backed execution

#### Validation
- Reused local virtual environment: `.venv`
- Ran test suite successfully
- Result: `37 passed`

### Module: app data store and namespace separation

Implemented a first explicit data layer split for long-lived apps.

#### Added
- `app/models/data_record.py`
  - `DataNamespace`
  - `DataRecord`
- `app/services/app_data_store.py`
  - app namespace provisioning
  - skill asset namespace provisioning
  - record write/read APIs
  - persistence of namespaces and records via runtime store
- `.gitignore`
  - ignore local virtualenv, caches, and test data directories

#### Updated
- `app/services/app_installer.py`
  - app installation now provisions app-specific namespaces
- `app/api/main.py`
  - added namespace and record endpoints
  - runtime persistence snapshot now includes data namespaces and records
  - initialized global skill asset namespace
- `app/core/errors.py`
  - added app data store error mapping
- `tests/unit/test_registry_installer.py`
  - installer tests now include app data store wiring
- `tests/unit/test_interaction_gateway.py`
  - gateway tests now include installer + data store wiring

#### API endpoints added
- `GET /data/namespaces`
- `GET /data/namespaces/{namespace_id}`
- `GET /data/namespaces/{namespace_id}/records`
- `POST /data/namespaces/{namespace_id}/records`

#### Behavior added
- every installed app now gets dedicated namespaces for:
  - `app_data`
  - `runtime_state`
  - `system_metadata`
- system also maintains a global `skill_assets` namespace
- app business data is now explicitly separated from runtime state in the model

#### Tests
- added `tests/unit/test_app_data_store.py`
- validated:
  - namespace provisioning
  - installer-driven namespace creation
  - record write/read behavior
  - namespace API flow
  - persistence snapshot exposure

#### Validation
- Reused local virtual environment: `.venv`
- Cleaned transient `data/test-*` directories
- Ran test suite successfully
- Result: `41 passed`

### Module: event bus and event-driven scheduling

Implemented a first internal event bus so long-running apps can react to system and app events.

#### Added
- `app/models/event_bus.py`
  - `EventRecord`
  - `EventSubscription`
  - `EventPublishResult`
- `app/services/event_bus.py`
  - event publishing
  - event log persistence
  - subscription registration
  - scheduler integration on publish
- `tests/unit/test_event_bus.py`
  - event-driven scheduling tests

#### Updated
- `app/services/scheduler.py`
  - event schedules now auto-create subscriptions
  - subscription listing support
  - event subscriptions persist alongside schedules
- `app/api/main.py`
  - added event publish/list/subscription endpoints
  - runtime persistence snapshot now includes event log and subscriptions
- `app/core/errors.py`
  - added event bus error mapping
- `.gitignore`
  - now ignores `*.egg-info/`

#### API endpoints added
- `GET /events`
- `POST /events/publish`
- `GET /events/subscriptions`
- `POST /events/subscriptions`

#### Behavior added
- event schedules can now be triggered through internal event publication instead of only manual scheduler calls
- published events are recorded in a persistent event log
- event subscriptions are visible and persisted as first-class runtime objects

#### Tests
- validated:
  - event publish triggers event schedules
  - scheduler auto-registers event subscriptions
  - event API flow
  - manual subscription creation

#### Validation
- Reused local virtual environment: `.venv`
- Cleaned transient `data/test-*` directories and `*.egg-info`
- Ran test suite successfully
- Result: `45 passed`

### Module: practice review and runtime experience distillation

Implemented a first practice-to-experience loop so the system can summarize runtime behavior into reusable experience records.

#### Added
- `app/models/practice_review.py`
  - `PracticeReviewRequest`
  - `PracticeReviewResult`
- `app/services/practice_review.py`
  - runtime event + data record review
  - experience summary generation
  - experience store integration
- `tests/unit/test_practice_review.py`
  - runtime practice review tests

#### Updated
- `app/api/main.py`
  - added practice review endpoint
- `app/core/errors.py`
  - added practice review error mapping

#### API endpoints added
- `POST /practice/review`

#### Behavior added
- system can now inspect an app instance's recent event log and data records
- runtime behavior is summarized into an `ExperienceRecord`
- generated runtime experiences are added to the experience store

#### Tests
- validated:
  - runtime practice review generates an experience record
  - review works from runtime events + app data records
  - practice review API flow

#### Validation
- Reused local virtual environment: `.venv`
- Cleaned transient `data/test-*` directories and `*.egg-info`
- Ran test suite successfully
- Result: `47 passed`

### Module: experience-to-skill suggestion layer

Implemented a first semi-automatic bridge from runtime experience to reusable skill blueprint suggestions.

#### Added
- `app/models/skill_suggestion.py`
  - `SkillSuggestionRequest`
  - `SkillSuggestionResult`
- `app/services/skill_suggestion.py`
  - experience lookup
  - candidate skill blueprint generation
  - optional persistence into skill blueprint store
- `tests/unit/test_skill_suggestion.py`
  - skill suggestion tests

#### Updated
- `app/api/main.py`
  - added skill suggestion endpoint
- `app/core/errors.py`
  - added skill suggestion error mapping

#### API endpoints added
- `POST /skills/suggest-from-experience`

#### Behavior added
- system can now generate a candidate `SkillBlueprint` from an `ExperienceRecord`
- suggestion can remain advisory or be persisted into the skill blueprint store
- practice review output can now feed the next evolution step: experience -> skill suggestion

#### Tests
- validated:
  - blueprint suggestion generation from runtime experience
  - optional suggestion persistence
  - practice review -> skill suggestion API flow

#### Validation
- Reused local virtual environment: `.venv`
- Cleaned transient `data/test-*` directories and `*.egg-info`
- Ran test suite successfully
- Result: `50 passed`

### Module: self-refinement patch proposal layer

Implemented the first constrained self-iteration layer. The system can now generate patch proposals for itself without directly auto-modifying core runtime behavior.

#### Added
- `app/models/patch_proposal.py`
  - `PatchProposal`
  - `SelfRefinementRequest`
  - `SelfRefinementResult`
- `app/services/self_refinement.py`
  - experience-driven patch proposal generation
  - runtime policy patch suggestions
  - workflow patch suggestions
- `tests/unit/test_self_refinement.py`
  - self-refinement tests

#### Updated
- `app/api/main.py`
  - added self-refinement proposal endpoint
- `app/core/errors.py`
  - added self-refinement error mapping

#### API endpoints added
- `POST /self-refinement/propose`

#### Behavior added
- system can now generate constrained self-refinement proposals from runtime experience
- proposals include:
  - target type
  - evidence
  - expected benefit
  - risk level
  - auto-apply allowance
  - validation checklist
  - rollback target
- current proposal targets:
  - runtime policy
  - workflow

#### Safety boundary
- this layer only produces proposals
- it does not auto-apply structural system changes
- medium/high-risk refinement remains explicitly reviewable

#### Tests
- validated:
  - self-refinement proposal generation from reviewed runtime experience
  - runtime policy and workflow proposals both appear when relevant
  - self-refinement API flow

#### Validation
- Reused local virtual environment: `.venv`
- Cleaned transient `data/test-*` directories and `*.egg-info`
- Ran test suite successfully
- Result: `52 passed`

### Module: proposal review and approval flow

Implemented the first review loop for self-refinement proposals so the system can move from proposal generation to controlled approval and limited application.

#### Added
- `app/models/proposal_review.py`
  - `ProposalReviewRecord`
  - `ProposalReviewRequest`
- `app/services/proposal_review.py`
  - proposal registration
  - proposal listing
  - proposal review state transitions
  - limited low-risk runtime policy patch application
- `tests/unit/test_proposal_review.py`
  - proposal review and apply tests

#### Updated
- `app/api/main.py`
  - self-refinement proposal generation now registers proposals for later review
  - added proposal listing endpoint
  - added review record listing endpoint
  - added approve/reject/apply endpoint
  - persistence snapshot now includes patch proposals and proposal reviews
- `app/core/errors.py`
  - added proposal review error mapping

#### API endpoints added
- `GET /self-refinement/proposals`
- `GET /self-refinement/reviews`
- `POST /self-refinement/review`

#### Behavior added
- self-refinement proposals are now persisted as first-class review objects
- review states now include:
  - proposed
  - approved
  - rejected
  - applied
- low-risk runtime policy proposals can be applied in a constrained way
- workflow proposals currently support review/approval but not direct application

#### Safety boundary
- review and approval are now explicit steps
- structural workflow changes are not auto-applied
- apply remains restricted to low-risk runtime-policy patches only

#### Tests
- validated:
  - proposal registration
  - low-risk runtime patch application
  - proposal review API flow
  - approval flow for workflow proposals

#### Validation
- Reused local virtual environment: `.venv`
- Cleaned transient `data/test-*` directories and `*.egg-info`
- Ran test suite successfully
- Result: `54 passed`

### Module: priority and contradiction analysis for self-refinement

Implemented a first priority-analysis layer so the system can rank its own refinement proposals and identify the current main contradiction.

#### Added
- `app/models/priority_analysis.py`
  - `PriorityAnalysisRequest`
  - `PrioritizedProposal`
  - `PriorityAnalysisResult`
- `app/services/priority_analysis.py`
  - proposal scoring
  - main contradiction description
  - recommended next action generation
- `tests/unit/test_priority_analysis.py`
  - priority analysis tests

#### Updated
- `app/api/main.py`
  - added self-refinement priority analysis endpoint
- `app/core/errors.py`
  - added priority analysis error mapping

#### API endpoints added
- `POST /self-refinement/analyze-priority`

#### Behavior added
- system can now rank multiple refinement proposals by priority
- ranking considers:
  - target type impact
  - risk level
  - auto-apply eligibility
  - amount of evidence
- analysis also outputs:
  - primary contradiction
  - recommended next action

#### Design value
- the system no longer only produces proposals
- it can now distinguish primary vs secondary refinement actions
- this is the first step toward a structured “抓主要矛盾” capability in the runtime evolution loop

#### Tests
- validated:
  - low-risk runtime policy proposal ranks ahead of workflow proposal when appropriate
  - priority analysis API flow

#### Validation
- Reused local virtual environment: `.venv`
- Cleaned transient `data/test-*` directories and `*.egg-info`
- Ran test suite successfully
- Result: `56 passed`

### Module: local model configuration and connectivity probe

Implemented the first project-level model access scaffolding so AgentSystem can connect to an OpenAI-compatible responses API independently of the host assistant runtime.

#### Added
- `app/models/model_config.py`
  - local model configuration schema
- `app/services/model_config_loader.py`
  - local file / environment configuration loader
  - API key resolution
- `app/services/model_client.py`
  - OpenAI-compatible `/v1/responses` probe client
- `config/model.local.example.json`
  - example local model configuration template
- `.env.local.example`
  - example environment variable template
- `scripts/model_probe.py`
  - minimal connectivity probe script
- `tests/unit/test_model_config.py`
  - model configuration loader tests

#### Updated
- `.gitignore`
  - ignore `.env.local`
  - ignore `config/model.local.json`
- `README.md`
  - added local model configuration section
- `docs/testing-detail.md`
  - recorded actual project-level model probe status

#### Behavior added
- project can now load model settings from a local gitignored config file or environment variables
- project can now resolve API key by env var name
- project can probe an OpenAI-compatible responses endpoint directly

#### Validation
- Ran unit tests successfully
- Result: `59 passed`
- Ran actual model probe against configured endpoint
- Result: `/v1/responses` returned `MODEL_PROBE_OK`

#### Security note
- real API secret was written only to local gitignored files
- no secret was added to tracked repository files or commits

### Module: external private default path for model config

Moved the default model configuration lookup path out of the repository so secrets no longer need to live under the project directory.

#### Updated
- `app/services/model_config_loader.py`
  - default config path changed to `/root/.config/agentsystem/model.local.json`
  - default env path changed to `/root/.config/agentsystem/model.local.env`
  - loader now imports environment values from the private env file automatically
- `README.md`
  - updated local model configuration instructions
- `docs/testing-detail.md`
  - updated project-level model probe notes
- `tests/unit/test_model_config.py`
  - added validation for private env-file loading

#### Behavior added
- the project now prefers private configuration outside the repository by default
- local model secrets can live in `/root/.config/agentsystem/` instead of the workspace
- model probe works using the new default private path without requiring project-local secret files

#### Validation
- Ran full test suite successfully
- Result: `60 passed`
- Ran actual model probe via default external config path
- Result: `/v1/responses` returned `MODEL_PROBE_OK`

### Module: unified private YAML configuration

Unified the local private model configuration into a single YAML file outside the repository.

#### Updated
- `pyproject.toml`
  - added `PyYAML`
- `app/models/model_config.py`
  - added optional inline `api_key`
- `app/services/model_config_loader.py`
  - default private config path changed to `/root/.config/agentsystem/config.yaml`
  - YAML `model:` section is now the primary config source
  - legacy JSON/env private paths remain temporarily compatible for migration
- `app/services/model_client.py`
  - now tolerates event-stream probe responses
- `README.md`
  - updated local config docs for the YAML path
- `docs/testing-detail.md`
  - updated private config and probe notes
- `tests/unit/test_model_config.py`
  - rewritten for YAML-based config loading

#### Added
- `config/config.local.example.yaml`
  - repository template for the private YAML structure

#### Behavior added
- project now prefers one private YAML file at `/root/.config/agentsystem/config.yaml`
- the YAML file can carry the real API key locally without needing extra env files
- loader still keeps env fallback and temporary legacy compatibility
- probe now handles both JSON and SSE-style response bodies

#### Validation
- Installed `PyYAML` in the repo-local virtualenv
- Ran full test suite successfully
- Result: `59 passed`
- Ran actual model probe using `/root/.config/agentsystem/config.yaml`
- Result: endpoint reachable and returned SSE response events from `/v1/responses`

### Module: model-enhanced skill suggestion with deterministic fallback

Added an optional model-backed skill suggestion layer while preserving the original deterministic synthesis path as a safe fallback.

#### Added
- `app/services/model_skill_suggester.py`
  - generates constrained skill blueprint JSON from runtime experience via the configured responses API
  - exposes availability checks so model enhancement stays optional

#### Updated
- `app/services/skill_suggestion.py`
  - now supports injected model suggester
  - still builds a deterministic rule-based suggestion first
  - falls back to deterministic synthesis whenever model config or model output is invalid
- `app/api/main.py`
  - wires `ModelSkillSuggester` into the global `SkillSuggestionService`
- `tests/unit/test_skill_suggestion.py`
  - added model-success and model-fallback tests

#### Behavior added
- skill suggestion can now be model-enhanced when local private model config is available
- model output is constrained to a narrow JSON blueprint shape
- deterministic fallback still guarantees the feature works without model access or under model failure

#### Validation
- Ran full test suite successfully
- Result: `61 passed`

### Module: model-enhanced self refinement with constrained fallback

Added an optional model-backed self-refinement proposal synthesizer while keeping the existing deterministic proposal path as the hard safety floor.

#### Added
- `app/services/model_self_refiner.py`
  - generates constrained self-refinement proposal JSON via the configured responses API
  - only targets proposal synthesis, not direct mutation
  - exposes availability checks so model enhancement remains optional

#### Updated
- `app/services/self_refinement.py`
  - now supports injected model self-refiner
  - still builds deterministic runtime_policy/workflow proposals first
  - falls back to deterministic proposals whenever model config or model output is invalid
- `app/api/main.py`
  - wires `ModelSelfRefiner` into the global `SelfRefinementService`
- `tests/unit/test_self_refinement.py`
  - added model-success and model-fallback tests

#### Behavior added
- self refinement can now be model-enhanced when local private model config is available
- model output is constrained to a narrow proposal JSON shape
- refinement remains proposal-before-apply; no direct model-driven mutation was added
- deterministic fallback still guarantees the feature works without model access or under model failure

#### Validation
- Ran full test suite successfully
- Result: `63 passed`

### Module: app shared context model and control-plane boundary docs

Added the first explicit app-local shared context model so apps can maintain internal execution context independently from the user-facing control plane.

#### Added
- `app/models/app_context.py`
  - `AppSharedContext`
  - `AppContextEntry`
- `app/services/app_context_store.py`
  - shared context creation
  - context stage/goal update
  - structured entry append
  - persistence via runtime state store
- `tests/unit/test_app_context_store.py`
  - app context service and API tests

#### Updated
- `app/api/main.py`
  - added app context APIs
  - runtime persistence snapshot now includes `app_contexts`
- `app/core/errors.py`
  - added app context error mapping
- `docs/requirements.md`
  - documented app-local shared context and user-facing control plane boundary
- `docs/design.md`
  - documented control plane vs app runtime boundary and app shared context store
- `docs/testing.md`
  - added app shared context coverage to testing strategy

#### API endpoints added
- `GET /app-contexts`
- `GET /app-contexts/{app_instance_id}`
- `POST /app-contexts/{app_instance_id}`
- `POST /app-contexts/{app_instance_id}/entries`

#### Behavior added
- apps can now maintain app-local shared context independently from the control-plane AI
- app contexts can store structured facts, artifacts, decisions, questions, constraints, and open loops
- the system can now expose app-level goal/stage state without forcing all internal execution back through the user-facing control plane

#### Validation
- Ran full test suite successfully
- Result: `65 passed`

### Module: documentation consolidation for requirements, design, and testing

Reorganized the project documents into a coherent set aligned with the current implemented architecture.

#### Updated
- `docs/requirements.md`
  - rewritten around current scope and implemented milestones
  - clarified app / skill / blueprint / instance boundaries
  - aligned requirements with actual runtime, data, event, and evolution capabilities
- `docs/design.md`
  - rewritten into a single coherent architecture document
  - aligned service map, object model, runtime flows, data model, and evolution chain with the current codebase
- `docs/testing.md`
  - rewritten into a testing strategy document aligned with the implemented test matrix and development discipline

#### Documentation goals achieved
- removed duplicated / conflicting structure from older drafts
- aligned docs with the current implemented milestone instead of a purely hypothetical future system
- made the logic consistent across requirements, design, and testing
- clarified near-term gaps after the current milestone

#### Validation
- Ran full test suite after documentation update
- Result: `50 passed`

## 2026-03-18

### Module: documentation update for system skills, app config, and runtime capability inference

Documented the next-step platform direction for deterministic system defaults, app configuration, skill capability tags, and automatic runtime-profile inference.

#### Updated
- `docs/requirements.md`
  - added requirements for built-in system skills
  - added per-app deterministic config surface expectations
  - added skill classification and app-profile resolution requirements
  - added direct-start/offline-capable behavior requirements
  - added intelligence invocation governance requirements
- `docs/design.md`
  - separated network availability from intelligence availability
  - described capability-tagged skills and runtime profile aggregation
  - documented app-config as a built-in system capability
  - documented policy-driven ask-before-intelligence behavior
- `docs/testing.md`
  - updated suite status to `81 passed`
  - added future test coverage targets for capability classification, direct start, and invocation governance

#### Design intent clarified
- users should not manually choose low-level runtime classes for apps
- the platform should infer app runtime posture from skill metadata
- runtime build-time skills and runtime skills should remain distinct
- optional intelligence should not automatically consume user tokens
- no-network and no-intelligence are separate runtime conditions

### Module: documentation update for skill package contracts and runtime adapters

Extended the documentation direction so skills are treated as runnable capability packages with explicit contracts, adapters, and validation rules.

#### Updated
- `docs/requirements.md`
  - added requirements for skill packaging, skill contracts, runtime adapters, and app/skill validation
- `docs/design.md`
  - documented skill package shape, unified execution envelope, runtime adapter model, orchestrator-mediated dispatch, and compile-time validation expectations
- `docs/testing.md`
  - added future validation targets for manifest/schema/adapter checking and runtime/build-time skill separation

#### Design intent clarified
- skills should be packaged as structured runtime units rather than symbolic names only
- skill execution should flow through a unified runtime/orchestrator surface
- skill contracts should be machine-readable for compile-time validation and safe composition
- adapter diversity (callable/script/rpc/binary/frontend) should not break runtime governance or observability

### Module: documentation update for dedicated skill design principles reference

Moved the core-skill principle table into its own dedicated document so future skill design has a stable, explicit reference point.

#### Added
- `docs/skill-design-principles.md`
  - canonical reference for core skill design principles
  - core-skill principle table
  - design checklist for future core skills

#### Updated
- `docs/requirements.md`
  - records the dedicated canonical reference path
- `docs/design.md`
  - now points to the standalone skill design principles document
- `docs/testing.md`
  - references the standalone document in future validation targets
- `README.md`
  - documents the dedicated skill design principles doc path
- `TOOLS.md`
  - records the dedicated doc path for future implementation work

#### Design intent clarified
- future core skills should be reviewed against one dedicated canonical reference document
- the skill design principles should remain stable and discoverable outside the broader architecture doc
- core skill roles, locality, intelligence posture, and contract strictness should stay explicit

## 2026-03-18

### Module: minimal skill metadata and capability profile registration

Started moving skills from symbolic names toward structured runtime metadata.

#### Implemented
- extended `SkillRegistryEntry` with:
  - `capability_profile`
  - `runtime_adapter`
- introduced `SkillCapabilityProfile` with:
  - intelligence level
  - network requirement
  - runtime criticality
  - execution locality
  - invocation default
  - risk level
- registered built-in system skills and `skill.echo` with explicit capability metadata in the API bootstrap layer
- added test coverage verifying skill metadata is exposed through the skill listing API

#### Design intent clarified
- skills should no longer be treated as names only once they become runtime-visible
- capability metadata should be present before full manifest/contract work begins
- built-in system skills should model the same metadata shape expected of future skills

### Module: minimal skill manifest and contract references

Added a minimal manifest layer so registered skills begin to expose package-style structure in addition to capability tags.

#### Implemented
- introduced `SkillManifest`
- introduced `SkillContractRef`
- extended `SkillRegistryEntry` with optional `manifest`
- registered built-in system skills and demo skill with minimal manifests
- added tests verifying manifests are exposed via the skill listing API

#### Design intent clarified
- manifest/contract evolution should be gradual and backward compatible
- capability tags and manifest structure should coexist during migration
- runtime-visible system skills should expose both operational metadata and package-style identity

### Module: minimal manifest validation on skill registration

Added the first validator layer so manifest structure begins to participate in registration-time checks.

#### Implemented
- introduced `SkillManifestValidatorService`
- registration now validates manifest consistency when a manifest is present
- validator currently checks:
  - manifest skill id matches registry entry skill id
  - manifest name matches registry name
  - manifest version matches active version
  - manifest runtime adapter matches registry runtime adapter
- added validator-focused unit tests and a negative registration test

#### Design intent clarified
- manifest data should not be passive metadata only
- validation should be incremental and preserve backward compatibility for entries without manifests
- registration-time checks are the first step toward fuller skill package validation

### Module: minimal runtime adapter model

Added the first explicit adapter-spec layer so runtime adapter intent begins to exist separately from plain string labels.

#### Implemented
- introduced `SkillAdapterSpec`
- extended `SkillManifest` with `adapter`
- validator now checks adapter-kind alignment with runtime adapter
- `SkillRuntimeService` now distinguishes callable vs script adapters
- script adapters are recognized but intentionally fail with a clear not-implemented error
- added unit coverage for callable execution and script-adapter rejection

#### Design intent clarified
- runtime adapters should become first-class execution specs rather than opaque strings
- adapter evolution can proceed incrementally without pretending unsupported adapters already work
- explicit not-implemented behavior is better than silently treating every adapter like callable

### Module: minimal script adapter execution

Promoted the script adapter from placeholder status to a minimal runnable execution path.

#### Implemented
- `SkillRuntimeService` can now execute `script` adapters via local subprocess
- request payload is serialized as JSON to stdin
- script result is read as JSON from stdout and parsed into `SkillExecutionResult`
- added a fixture script and adapter runtime unit coverage

#### Current constraints
- script execution is local-only
- JSON stdin/stdout only
- no streaming or interactive session support yet
- fixed timeout for the initial implementation

#### Design intent clarified
- script adapter support should be real, not nominal
- the first supported non-callable adapter should stay narrow and deterministic
- JSON request/response envelopes are the foundation for future adapter expansion

### Module: context runtime view serialization hardening

Identified a hang during pytest shutdown around context/runtime-view serialization and made the context skill return path more defensive.

#### Implemented
- hardened `list_runtime_view` to return plain JSON-friendly dict payloads
- added a targeted regression test for JSON serialization of context runtime views

#### Design intent clarified
- system skill outputs should be aggressively normalized to JSON-friendly payloads
- runtime/view helper paths should avoid leaking nested model objects into higher-level serialization

### Module: bootstrap cleanup for built-in skill registration

Reduced duplication in the API bootstrap layer by extracting built-in skill registration and handler wiring into a dedicated helper module.

#### Implemented
- added `app/services/system_skill_registry.py`
- moved built-in skill registry entry construction into shared helper functions
- moved built-in handler registration into a shared helper
- reduced repeated manifest/capability boilerplate in `app/api/main.py`

#### Design intent clarified
- bootstrap wiring should stay readable as the number of built-in skills grows
- system skill definitions should be centralized to reduce drift between metadata and handler registration

### Module: bootstrap extraction for runtime construction and built-in handlers

Further reduced `app/api/main.py` complexity by extracting service construction and built-in handler assembly into dedicated bootstrap modules.

#### Added
- `app/bootstrap/runtime.py`
- `app/bootstrap/skills.py`

#### Implemented
- moved service graph construction into `build_runtime()`
- moved built-in handler creation/wiring into `bootstrap_builtin_skills()`
- reduced `main.py` to mostly composition and route declarations

#### Design intent clarified
- runtime bootstrap and API route declaration should evolve independently
- service graph construction should be centralized for easier future refactors and testing

### Module: demo catalog/bootstrap extraction

Moved demo blueprint registration and catalog seeding out of `app/api/main.py` so the entry file keeps shrinking toward route-only composition.

#### Added
- `app/bootstrap/catalog.py`

#### Implemented
- extracted built-in demo app blueprint registration
- extracted built-in catalog entry registration
- reduced direct bootstrap noise in `main.py`

#### Design intent clarified
- sample/demo bootstrapping should remain easy to find without cluttering API route definitions
- bootstrap data and runtime wiring should stay separated from route implementation details

### Module: organize system skill services under a dedicated directory

Grouped the platform default skill implementations into a clearer service subtree while keeping old import paths as compatibility wrappers.

#### Added
- `app/services/system_skills/app_config.py`
- `app/services/system_skills/state_audit.py`
- `app/services/system_skills/context.py`
- `app/services/system_skills/README.md`

#### Updated
- `app/services/app_config_service.py`
- `app/services/system_skill_service.py`
- `app/services/context_skill_service.py`
  - now act as thin compatibility exports
- `TOOLS.md`
  - notes the new system-skill directory layout

#### Design intent clarified
- default system skills should be easy to find as one family of services
- migration should preserve existing imports while improving layout

### Module: internal import cleanup and code-structure note

Started switching internal wiring toward the new `app/services/system_skills/` package and added a lightweight structure guide for future development.

#### Added
- `docs/code-structure.md`

#### Updated
- `app/bootstrap/runtime.py`
  - now imports system-skill implementations from the new package directly
- `README.md`
  - points to `docs/code-structure.md`
- `TOOLS.md`
  - points to `docs/code-structure.md`

#### Design intent clarified
- the new system-skill package should become the primary import target over time
- a small structure map is useful while the codebase is still actively being reorganized

### Module: stabilize system.context runtime-view tests

Hardened the system-context test path so runtime-view validation no longer depends on reused on-disk test directories.

#### Updated
- `app/services/app_context_store.py`
  - added the missing `LifecycleError` import used by runtime-view fallback handling
- `tests/unit/test_context_runtime_view_serialization.py`
  - expanded coverage for both runtime-present and runtime-unavailable serialization paths
- `tests/unit/test_system_context_skill.py`
  - switched test storage paths to pytest-managed `tmp_path` directories to avoid cross-run state pollution

#### Validation
- Ran targeted regression tests successfully
- Result: `3 passed`

#### Design intent clarified
- file-backed runtime tests should isolate their storage roots per test run
- system skill serialization tests should cover both happy-path and fallback-path payload shapes

### Module: isolate workflow and system-skill tests from on-disk state reuse

Continued converting file-backed unit tests away from fixed `data/test-*` directories so repeated local runs do not inherit stale runtime JSON state.

#### Updated
- `tests/unit/test_workflow_executor.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_skill_runtime.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_interaction_gateway.py`
  - switched file-backed stores and persistence checks to pytest `tmp_path`
- `tests/unit/test_system_app_config_skill.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_system_state_and_audit_skills.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`

#### Validation
- Ran focused regression suite successfully
- Result: `19 passed`

#### Design intent clarified
- unit tests that exercise the JSON file runtime store should use unique temporary roots by default
- repeated local/CI runs should not depend on manual cleanup of prior `data/test-*` artifacts

### Module: isolate refinement and registry/event tests from persistent test state

Extended the `tmp_path` migration to additional file-backed tests in the refinement, registry, and event areas.

#### Updated
- `tests/unit/test_self_refinement.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_priority_analysis.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_registry_installer.py`
  - switched file-backed stores and installer namespaces to pytest `tmp_path`
- `tests/unit/test_event_bus.py`
  - switched file-backed runtime store to pytest `tmp_path`

#### Validation
- Ran focused regression suite successfully
- Result: `13 passed`

#### Design intent clarified
- refinement and registry tests should be isolated from previously persisted runtime JSON just like workflow/runtime tests
- test stability improvements should be applied consistently across subsystems rather than only around the originally failing area

### Module: finish tmp_path migration for remaining file-backed unit tests

Completed another pass over the remaining fixed `data/test-*` unit tests to reduce state leakage across repeated runs.

#### Updated
- `tests/unit/test_proposal_review.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_workflow_subscription.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_app_config_service.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_app_data_store.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_practice_review.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_context_runtime_view_serialization.py`
  - aligned the new serialization regression tests with pytest `tmp_path`

#### Validation
- Ran focused regression suite successfully
- Result: `13 passed`

#### Design intent clarified
- all new and recently touched file-backed unit tests should default to isolated temporary roots
- regression tests added during bug fixing should follow the same isolation rules as the rest of the suite

### Module: stop tracking generated runtime snapshots

Cleaned up repository hygiene around generated runtime JSON snapshots under `data/runtime/`.

#### Updated
- removed tracked `data/runtime/*` files from git index while preserving them locally
- kept `.gitignore` as the source of truth for excluding generated runtime state

#### Why
- these files are execution byproducts, not source artifacts
- keeping them tracked causes constant dirty working trees after local runs and tests
- removing them from version control reduces noisy diffs and accidental snapshot churn in commits

### Module: complete persisted layered-context compaction baseline

Tightened the existing context-compaction path into a more durable layered-context baseline instead of a one-session-only helper.

#### Updated
- `app/services/context_compaction.py`
  - loads persisted summaries/policies on startup
  - supports `stage_change` policy checks in addition to workflow completion/failure
  - enriches summary/working-set metadata with workflow and skill execution references
  - reports skill execution counts in layer detail metadata
- `app/services/workflow_executor.py`
  - triggers policy-driven compaction on workflow stage changes
- `app/api/main.py`
  - exposes `context_summaries` and `context_policies` in runtime persistence snapshots
- `tests/unit/test_context_compaction.py`
  - validates persisted summary/policy reload
- `tests/unit/test_context_policy.py`
  - validates stage-change auto compaction and runtime snapshot exposure

#### Validation
- Ran focused regression suite successfully
- Result: `14 passed`

#### Design intent clarified
- layered context should survive runtime restarts instead of resetting to in-memory-only state
- context compaction policy should govern stage transitions as well as workflow completion/failure
- working-set views should point toward deeper workflow/skill detail rather than pretending summaries are self-sufficient

### Module: add deterministic blueprint and runtime-skill validation baseline

Introduced a first stricter validation layer so obviously invalid app blueprints are rejected before install instead of failing later during runtime execution.

#### Added
- `app/services/skill_validation.py`
  - validates skill existence and blocks build-only skills from runtime workflow execution
- `app/services/blueprint_validation.py`
  - validates required skills, workflow skill declarations, and runtime-step skill usage

#### Updated
- `app/bootstrap/runtime.py`
  - wires blueprint/skill validation into the runtime service graph
- `app/services/app_installer.py`
  - runs blueprint validation before provisioning app instances
- `app/api/main.py`
  - upgrades `/blueprints/validate` from a placeholder shape-check to structured blueprint validation
- `tests/unit/test_blueprint_validation.py`
  - covers undeclared workflow skills, missing required skills, build-only runtime leaks, and installer rejection
- `tests/unit/test_registry_installer.py`
  - updates install API fixture to match stricter validation rules

#### Validation
- Ran focused validation/profile/installer/runtime regression suite successfully
- Result: `31 passed`

#### Design intent clarified
- invalid runtime-skill wiring should fail before install rather than surfacing only during workflow execution
- build-only capability tags must have real enforcement value, not just documentation value

### Module: align contract/validation design with schema-first runtime direction

Refined the design documents after reviewing OpenClaw's schema-first patterns so the next contract-validation work has a clearer target shape.

#### Updated
- `docs/requirements.md`
  - clarifies that machine-readable contracts/schemas should be the single source of truth for validation and runtime envelopes
- `docs/design.md`
  - separates package validation, compile-time workflow validation, and runtime envelope validation
  - clarifies that adapter executability and contract validity are different dimensions
- `docs/testing.md`
  - adds schema-registry, pre-dispatch input validation, and post-dispatch output/error validation expectations

#### Design intent clarified
- schema/contract definitions should drive validation first, then runtime execution
- runtime envelope violations should be treated differently from adapter/runtime failures
- future contract validation should reuse one authoritative schema source instead of parallel ad-hoc checks

### Module: add schema registry baseline for skill contract refs

Started the schema-first contract implementation by introducing a minimal schema registry and wiring manifest validation through it.

#### Added
- `app/services/schema_registry.py`
  - provides schema registration, resolution, and minimal JSON-schema-style payload validation helpers

#### Updated
- `app/services/skill_manifest_validator.py`
  - now verifies non-empty contract refs can be resolved through the schema registry
- `app/services/skill_validation.py`
  - can share the same schema-aware manifest validator path
- `app/bootstrap/runtime.py`
  - instantiates a shared schema registry for runtime wiring
- `tests/unit/test_skill_manifest_validator.py`
  - adds coverage for registered and missing contract refs

#### Validation
- Ran focused manifest/validation/profile regression suite successfully
- Result: `11 passed`

#### Design intent clarified
- contract refs should fail early when they point to nothing
- schema resolution should become a reusable service rather than ad-hoc string checks in validators

### Module: enforce input/output contracts in skill runtime dispatch

Extended the schema-first path from manifest validation into actual runtime dispatch boundaries.

#### Updated
- `app/services/skill_runtime.py`
  - validates request inputs against declared input contract refs before handler execution
  - validates completed outputs against declared output contract refs after handler execution
  - distinguishes contract violations from ordinary runtime failures through dedicated error text
- `app/bootstrap/runtime.py`
  - injects the shared schema registry into the skill runtime service
- `tests/unit/test_skill_runtime.py`
  - adds invalid-input and invalid-output contract regression coverage while preserving existing workflow execution paths

#### Validation
- Ran focused runtime/manifest/blueprint regression suite successfully
- Result: `14 passed`

#### Design intent clarified
- request/response contracts should be enforced at dispatch boundaries, not only during package validation
- runtime contract violations should surface as envelope failures rather than opaque handler exceptions

### Module: add compile-time workflow contract compatibility checks

Extended blueprint validation so some obvious workflow wiring errors are rejected before install instead of waiting for runtime execution.

#### Updated
- `app/services/blueprint_validation.py`
  - checks that `$from_step` references only point to prior workflow steps
  - checks required input fields against declared skill input contracts when compile-time payloads are statically visible
  - checks mapped fields against declared input schema properties when additional properties are disallowed
- `app/services/skill_validation.py`
  - exposes runtime-skill entries for validation-time contract inspection
- `tests/unit/test_blueprint_validation.py`
  - adds regression coverage for future-step references and missing required input fields

#### Validation
- Ran focused blueprint/runtime regression suite successfully
- Result: `16 passed`
- Ran broader install/workflow/runtime regression suite successfully
- Result: `31 passed`

#### Design intent clarified
- compile-time validation should catch obvious workflow wiring mistakes before install/start
- runtime schema enforcement should complement, not replace, static workflow checks

### Module: validate prior skill output schemas against downstream inputs

Pushed compile-time validation one step further so workflow checks can reason about simple skill-to-skill schema wiring, not only missing fields and bad references.

#### Updated
- `app/services/blueprint_validation.py`
  - tracks prior skill-step output schemas when manifests declare them
  - validates `$from_step` field mappings against downstream skill input field schemas
  - rejects simple type mismatches between prior skill outputs and downstream input contracts
- `tests/unit/test_blueprint_validation.py`
  - adds regression coverage for incompatible prior-skill output to downstream input mappings

#### Validation
- Ran focused blueprint/schema/runtime regression suite successfully
- Result: `17 passed`
- Ran broader install/workflow/runtime regression suite successfully
- Result: `32 passed`

#### Design intent clarified
- compile-time compatibility should begin to reason about upstream and downstream schemas, not only reference existence
- the first useful compatibility pass can be field-level and conservative before evolving into fuller graph/type inference

### Module: add usable API-first end-to-end flow and schema-ize builtin system skills

Shifted part of the validation work toward actual usability by adding an API-first end-to-end flow and bringing builtin system skills into the schema-first contract path.

#### Updated
- `app/bootstrap/runtime.py`
  - registers minimal input/output/error schemas for `system.context` and `system.app_config`
  - aligns builtin input schemas with runtime-injected `working_set` payloads
- `app/services/system_skill_registry.py`
  - adds contract refs for builtin `system.context` and `system.app_config` manifests
- `tests/e2e/test_api_usable_flow.py`
  - adds an API-first usable flow covering blueprint registration, install, context/policy updates, workflow execution, runtime/context inspection, and invalid-flow rejection

#### Validation
- Ran usable API-first regression slice successfully
- Result: `17 passed`

#### Design intent clarified
- builtin system skills should participate in the same schema-first runtime path as other skills
- usable-alpha confidence should come from end-to-end API flows, not only isolated unit tests

### Module: connect external model API through builtin skill runtime path

Added a builtin external model probe skill and proved it through an end-to-end workflow that uses the configured OpenAI-compatible Responses API.

#### Updated
- `app/services/system_skill_registry.py`
  - registers builtin `model.responses.probe` with capability metadata and schema-backed contract refs
- `app/bootstrap/runtime.py`
  - registers input/output/error schemas for `model.responses.probe`
- `app/bootstrap/skills.py`
  - wires `model.responses.probe` to `OpenAIResponsesClient` via the existing model config loader
- `tests/e2e/test_external_model_api_flow.py`
  - adds an external API end-to-end flow that registers an app, installs it, executes the model probe workflow, and asserts returned model/provider metadata

#### Validation
- Ran external-model + usable-flow + validation/runtime regression slice successfully
- Result: `16 passed`

#### Design intent clarified
- external APIs should be consumed through the same skill-runtime and schema-validation path as builtin/internal capabilities
- proving real connectivity through an E2E workflow is more meaningful than isolated direct client probes

### Module: add structured runtime error envelopes for skill execution failures

Improved failure observability so runtime and external-model problems are easier to inspect through both skill execution records and workflow step details.

#### Updated
- `app/models/skill_runtime.py`
  - adds structured `error_detail` alongside the legacy string error field
- `app/services/model_client.py`
  - preserves upstream status code and retryability on model-client failures
- `app/services/skill_runtime.py`
  - emits structured error envelopes for contract violations, model client errors, and generic runtime failures
- `app/services/workflow_executor.py`
  - passes `error_detail` through into failed workflow step detail payloads
- `tests/unit/test_skill_runtime.py`
  - validates structured contract violation envelopes
- `tests/unit/test_skill_runtime_adapters.py`
  - validates structured model-client failure envelopes

#### Validation
- Ran runtime/error/external-flow regression slices successfully
- Result: focused suites green including external-model E2E and adapter/runtime tests

#### Design intent clarified
- failure paths should be machine-readable enough for debugging and future retry/policy logic
- external API failures should preserve status/retryability metadata instead of collapsing into opaque strings

### Module: add latest workflow execution lookup and failed-step observability

Pushed workflow observability a bit further so operators and future policy loops can see the newest execution directly and identify failed steps without re-scanning the full step list.

#### Updated
- `app/models/workflow_execution.py`
  - adds `failed_step_ids` to workflow execution results
- `app/services/workflow_executor.py`
  - populates failed-step ids when assembling execution results
- `app/api/main.py`
  - adds `/workflows/latest` for newest execution lookup with optional app-instance filtering
- `tests/unit/test_workflow_executor.py`
  - adds API coverage for latest execution lookup and result payload shape
- `tests/unit/test_workflow_execution_failure_observability.py`
  - adds failure-observability coverage for blocked skill steps

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added/updated deterministic tests for the changed observability path.

#### Design intent clarified
- operators should not need to manually scan full workflow history just to inspect the newest execution
- workflow-level failure summaries should expose exact failed step ids so future retry, UI, and policy layers can target the right step quickly

### Module: add filtered workflow failure inspection and ignore generated runtime assets

Extended the workflow observability path so failure triage can focus on one broken workflow/step, and cleaned up repo hygiene so generated runtime assets stop showing up as stray changes.

#### Updated
- `app/api/main.py`
  - extends `/workflows/failures` with optional `workflow_id` and `failed_step_id` filters
- `tests/unit/test_workflow_executor.py`
  - adds API coverage for filtered workflow failure inspection
- `.gitignore`
  - ignores `data/generated_callable_skills/` alongside other runtime/generated artifacts

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added deterministic API regression coverage for the new filtering behavior.

#### Design intent clarified
- failure inspection should support targeted triage by workflow path and failed step, not only broad history listing
- generated runtime skill assets are execution byproducts and should not pollute normal source-control status

### Module: add retry comparison metadata for failed workflow re-execution

Extended retry observability so re-running the latest failed workflow now reports what changed instead of only returning another raw execution payload.

#### Updated
- `app/models/workflow_execution.py`
  - adds `WorkflowRetryComparison`, `retry_of_completed_at`, and `retry_comparison`
- `app/services/workflow_executor.py`
  - enriches retry results with before/after failed-step and status comparison data
- `tests/unit/test_workflow_executor.py`
  - adds API coverage for retry comparison payloads

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added deterministic API regression coverage for the retry comparison path.

#### Design intent clarified
- retry should be an observable recovery action, not just another execution entry with implicit meaning
- operators and future policy logic should be able to compare failure vs retry outcomes without manually diffing two workflow records

### Module: add workflow diagnostics summary API

Added a lightweight aggregated diagnostics view so operator-facing tooling can inspect one workflow path without stitching together history, failures, and retry payloads by hand.

#### Updated
- `app/api/main.py`
  - adds `/workflows/diagnostics` to summarize latest execution, latest failure, latest retry, and recovery-state flags
- `tests/unit/test_workflow_executor.py`
  - adds API coverage for diagnostics summary behavior on a still-failing retry path

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added deterministic API regression coverage for the diagnostics path.

#### Design intent clarified
- operator-facing diagnostics should expose a compact recovery summary instead of forcing clients to reconstruct state from several low-level endpoints
- recovery panels should distinguish latest execution from latest true failure and latest retry attempt

### Module: add failed-step diagnostics filtering and latest recovery endpoint

Refined the diagnostics surface so clients can focus on one failed step path and query the newest retry outcome through a lighter dedicated endpoint.

#### Updated
- `app/api/main.py`
  - extends `/workflows/diagnostics` with `failed_step_id` filtering
  - adds `/workflows/latest-recovery` for a compact latest retry/recovery summary
- `tests/unit/test_workflow_executor.py`
  - adds API coverage for failed-step diagnostics filtering and latest-recovery output

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added deterministic API regression coverage for both new diagnostics paths.

#### Design intent clarified
- diagnostics consumers should be able to zoom into one failed-step path without post-filtering whole workflow histories client-side
- recovery dashboards benefit from a dedicated latest-recovery view instead of unpacking the full diagnostics payload every time

### Module: centralize workflow diagnostics aggregation and add overview API

Moved diagnostics/recovery aggregation logic into the workflow service so API handlers stop reimplementing the same selection rules, then exposed a combined overview response for dashboard-style consumers.

#### Updated
- `app/services/workflow_executor.py`
  - adds centralized history filtering, diagnostics-summary aggregation, and latest-recovery summary helpers
- `app/api/main.py`
  - simplifies diagnostics/recovery endpoints to use service helpers
  - adds `/workflows/overview` as a combined diagnostics + recovery response
- `tests/unit/test_workflow_executor.py`
  - adds API coverage for the overview response shape

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added deterministic API regression coverage for the service-backed overview path.

#### Design intent clarified
- aggregation rules for workflow diagnostics should live close to workflow execution history, not be copy-pasted across API handlers
- dashboard clients should be able to request one overview payload instead of stitching diagnostics and latest-recovery calls together

### Module: split workflow observability into a dedicated service and add health summary models

Took the next structural step by separating workflow observability from workflow execution, then formalized the overview payload with explicit models and health-summary fields.

#### Updated
- `app/models/workflow_observability.py`
  - adds explicit diagnostics / recovery / health / overview models
- `app/services/workflow_observability.py`
  - adds dedicated observability aggregation service for history filtering, diagnostics, recovery, health, and overview composition
- `app/bootstrap/runtime.py`
  - wires the new workflow observability service into runtime construction
- `app/api/main.py`
  - switches diagnostics/recovery/overview endpoints to the new observability service and returns model-backed payloads
- `tests/unit/test_workflow_executor.py`
  - extends overview coverage with explicit health summary assertions

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added deterministic API regression coverage for the new model-backed overview path.

#### Design intent clarified
- workflow execution and workflow observability are related but distinct concerns and should not continue to accrete inside one service class
- operator-facing health/status fields should be first-class contract elements, not conventions inferred ad hoc from raw diagnostic payloads

### Module: remove duplicate observability helpers from executor and harden health-state coverage

Completed the structural split by deleting leftover observability aggregation helpers from the executor and adding explicit tests for healthy vs unknown health-state outcomes.

#### Updated
- `app/services/workflow_executor.py`
  - removes duplicate observability helper methods now owned by the dedicated observability service
- `tests/unit/test_workflow_executor.py`
  - adds health-summary coverage for completed workflows (`healthy`) and partial-without-failure workflows (`unknown`)

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added deterministic API regression coverage for the health-state transitions.

#### Design intent clarified
- once observability is extracted, the executor should keep only execution/retry concerns instead of retaining stale read-model helpers
- health summaries should have tested semantics for non-error partial states, not only obvious failure cases

### Module: add dedicated workflow observability tests and centralize health classification rules

Continued the refactor by moving observability verification into its own test module and extracting health/severity rule decisions into explicit helper methods inside the observability service.

#### Updated
- `app/services/workflow_observability.py`
  - centralizes unresolved-failure counting and health/severity classification helpers
- `tests/unit/test_workflow_observability.py`
  - adds dedicated service-level tests for failing, healthy, and unknown workflow observability states

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added deterministic service-level coverage for the observability classification rules.

#### Design intent clarified
- observability logic should be testable directly at the service layer without routing every scenario through API-heavy executor tests
- health classification should be a named rule path, not inline conditional glue scattered across summary assembly

### Module: introduce explicit health-rule mapping and recovering-state coverage

Pushed the observability structure one step further by making health classification read from an explicit rule table and by adding service-level coverage for the recovering state.

#### Updated
- `app/services/workflow_observability.py`
  - adds an explicit health-rule table and uses it when classifying health/severity/transition outputs
- `tests/unit/test_workflow_observability.py`
  - adds a recovering-state scenario verifying resolved retry behavior produces the expected health summary

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added deterministic service-level coverage for the recovering-state classification path.

#### Design intent clarified
- state/severity mapping should be easy to inspect and extend without reopening nested conditionals every time a dashboard status rule changes
- recovering is a distinct operator-facing state and deserves explicit test coverage, not just implied support through generic retry metadata

### Module: add observability history slicing with recent-N and unresolved-only filters

Expanded the observability query surface so clients can fetch focused execution slices for dashboard timelines instead of always reconstructing views from the full history.

#### Updated
- `app/services/workflow_observability.py`
  - extends history filtering with `limit` and `unresolved_only`
  - adds `list_observability_history()` for focused observability slices
- `app/api/main.py`
  - adds `/workflows/observability-history`
- `tests/unit/test_workflow_observability.py`
  - adds service-level coverage for recent-N and unresolved-only history queries

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added deterministic service-level coverage for the new history slicing path.

#### Design intent clarified
- timeline and dashboard consumers often need the newest interesting slice, not an unbounded workflow execution dump
- unresolved-only filtering should be a first-class server-side capability so clients do not each reinvent failure-state heuristics

### Module: add compact workflow timeline summaries

Kept pushing the observability framework toward dashboard-readiness by introducing a timeline feed that turns raw execution records into compact event cards.

#### Updated
- `app/models/workflow_observability.py`
  - adds `WorkflowTimelineEvent`
- `app/services/workflow_observability.py`
  - adds timeline event normalization and summary generation
- `app/api/main.py`
  - adds `/workflows/timeline`
- `tests/unit/test_workflow_observability.py`
  - adds service-level coverage for failure/retry timeline summaries

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added deterministic service-level coverage for the timeline summary path.

#### Design intent clarified
- dashboard/activity-stream consumers should read compact, normalized event cards instead of reconstructing semantic events from full execution payloads
- timeline summaries should encode the important operator signal (failure, retry, recovery, completion) close to the service layer so every client sees the same story

### Module: add timeline windowing and cursor pagination

Rounded out the observability feed so it can behave like a real activity stream rather than a static list snapshot.

#### Updated
- `app/models/workflow_observability.py`
  - adds `WorkflowTimelinePage`
- `app/services/workflow_observability.py`
  - extends history/timeline queries with `since` and `cursor`
  - returns paged timeline results with `next_cursor`
- `app/api/main.py`
  - updates `/workflows/timeline` to return a page response instead of a bare list
- `tests/unit/test_workflow_observability.py`
  - adds service-level coverage for `since` windows and cursor-style pagination

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added deterministic service-level coverage for the timeline paging path.

#### Design intent clarified
- observability feeds should support incremental loading and time-window refreshes as first-class capabilities, not afterthought client-side list trimming
- a paged timeline response is a better long-term contract for UI consumers than an unbounded array

### Module: add shared observability filter model

Kept tightening the framework by introducing an explicit filter contract for observability queries so service and API layers stay aligned as the query surface grows.

#### Updated
- `app/models/workflow_observability.py`
  - adds `WorkflowObservabilityFilter`
- `app/services/workflow_observability.py`
  - switches history filtering to consume the shared filter model
- `app/api/main.py`
  - normalizes diagnostics/history/timeline parameter handling through the shared filter model
- `tests/unit/test_workflow_observability.py`
  - adds service-level coverage for filter-model-driven history queries

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added deterministic service-level coverage for the shared filter contract.

#### Design intent clarified
- once observability queries gain multiple knobs, an explicit filter model is safer than hand-copying parameter lists across each handler
- consistent query semantics matter as much as payload shape when you want dashboard and operator tooling to remain predictable

### Module: add observability API contract coverage and formalize history time-window filtering

Closed the next consistency gap by testing the API layer against the shared filter semantics and extending history queries to support the same time-window behavior as timeline feeds.

#### Updated
- `tests/unit/test_workflow_executor.py`
  - adds API contract coverage for shared observability filter semantics across diagnostics/history/timeline endpoints
- `tests/unit/test_workflow_observability.py`
  - extends service-level history coverage with `since` time-window filtering

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added deterministic API/service regression coverage for shared filter semantics and history windowing.

#### Design intent clarified
- it is not enough for services to share a filter model; the exposed HTTP surfaces should be checked for semantic alignment too
- history and timeline query surfaces should evolve together so clients do not face subtle capability mismatches

### Module: align observability-history with paged timeline contracts and centralize API filter construction

Tightened the framework contract by making history responses page-shaped like timeline responses and by removing repeated filter-object assembly from the API handlers.

#### Updated
- `app/models/workflow_observability.py`
  - adds `WorkflowHistoryPage`
- `app/services/workflow_observability.py`
  - returns paged history results with `next_cursor`
  - reuses paged history when building timeline pages
- `app/api/main.py`
  - adds a small `build_workflow_observability_filter()` helper
  - switches `/workflows/observability-history` to return a page response
- `tests/unit/test_workflow_executor.py`
  - updates API contract coverage for paged history responses
- `tests/unit/test_workflow_observability.py`
  - updates service-level history assertions for page-shaped responses

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; updated deterministic API/service coverage for the shared paged-history contract.

#### Design intent clarified
- history and timeline should feel like sibling query surfaces, not two independently shaped APIs that happen to expose similar data
- even small repeated request-construction code in API handlers becomes drift risk once the query contract keeps growing

### Module: add observability page metadata for dashboard consumers

Improved the framework’s read-model quality by adding lightweight metadata to paged history/timeline responses so clients can reason about feed state without re-deriving everything themselves.

#### Updated
- `app/models/workflow_observability.py`
  - adds `WorkflowPageMeta`
  - updates history/timeline page models to include `meta`
- `app/services/workflow_observability.py`
  - populates returned-count, unresolved-count, window, has-more, and next-cursor metadata
- `tests/unit/test_workflow_executor.py`
  - extends API contract checks for page metadata
- `tests/unit/test_workflow_observability.py`
  - extends service-level page assertions for metadata behavior

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added deterministic API/service coverage for paged observability metadata.

#### Design intent clarified
- page responses are more useful when they carry enough context for UI consumers to render feed state without additional bookkeeping calls
- metadata should stay lightweight and derived from server-side query knowledge, not force clients to reverse-engineer pagination and unresolved counts from raw item arrays

### Module: add aggregate workflow observability stats

Rounded out the operator read-model by adding aggregate observability totals so dashboards can render summary cards without fetching and counting every history/timeline record themselves.

#### Updated
- `app/models/workflow_observability.py`
  - adds `WorkflowStatsSummary`
- `app/services/workflow_observability.py`
  - adds `get_stats_summary()` for aggregate workflow observability totals
- `app/api/main.py`
  - adds `/workflows/stats`
- `tests/unit/test_workflow_executor.py`
  - adds API coverage for aggregate observability stats
- `tests/unit/test_workflow_observability.py`
  - adds service-level coverage for stats aggregation

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added deterministic API/service coverage for aggregate observability totals.

#### Design intent clarified
- operator dashboards often need both feed-style detail and card-style aggregate stats; one should not require reconstructing the other client-side
- aggregate stats should respect the same filtering concepts as the rest of the observability framework so summary cards and feeds remain coherent

### Module: add dashboard-oriented observability summary

Added a higher-level operator read model so dashboards can fetch one coherent payload instead of stitching overview, stats, and recent timeline calls together on the client side.

#### Updated
- `app/models/workflow_observability.py`
  - adds `WorkflowDashboardSummary`
- `app/services/workflow_observability.py`
  - adds `get_dashboard_summary()` to bundle overview, stats, and recent timeline
- `app/api/main.py`
  - adds `/workflows/dashboard`
- `tests/unit/test_workflow_executor.py`
  - adds API coverage for the dashboard summary payload
- `tests/unit/test_workflow_observability.py`
  - adds service-level coverage for combined dashboard composition

#### Validation
- Could not run `pytest` in the current shell because the command is unavailable in this environment; added deterministic API/service coverage for the dashboard read-model path.

#### Design intent clarified
- once observability data is rich enough, clients benefit from a composed read model that reflects operator needs directly instead of forcing repeated orchestration calls
- the dashboard summary should remain a thin composition over existing observability primitives so lower-level query surfaces stay reusable and testable

### Module: split observability helpers and API filter construction into dedicated modules

Started the next cleanup pass by moving low-level observability filtering/classification helpers and API filter construction out of the large service/main files.

#### Updated
- `app/services/workflow_observability_helpers.py`
  - extracts history filtering, health classification, unresolved counting, and retry step iteration helpers
- `app/api/workflow_observability.py`
  - extracts workflow observability filter construction from `main.py`
- `app/services/workflow_observability.py`
  - now delegates low-level helper logic instead of owning every concern directly
- `app/api/main.py`
  - now imports the dedicated observability filter builder instead of defining it inline

#### Validation
- Public API/service contracts were preserved while moving helper logic into dedicated modules; existing regression coverage remains the guardrail in this environment.

#### Design intent clarified
- once a sub-framework reaches this size, readability and future change safety improve by separating request-building and low-level helper logic from the primary orchestration layer
- module extraction should reduce file bloat without forcing a breaking change in the public observability contract
