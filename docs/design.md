# AgentSystem / App OS Design

## 1. Design Intent

Detailed companion reference: `docs/telemetry-and-upgrade-logging.md`.

AgentSystem is designed as a **stateful, persistent App OS** rather than a single assistant runtime.
Its core job is to manage apps as long-lived, isolated system objects — each app is a persistent functional module with its own data, context, and lifecycle — while allowing the system to learn from runtime practice and gradually improve its reusable capability layer.

### Core Architecture Philosophy

The system's fundamental identity is a **stateful operating system for apps**, not an ephemeral workflow engine:
- **Stateful & Persistent by Default**: Everything persists — apps, their data, configurations, execution context, and runtime state. The system survives restarts and rebuilds without losing operational continuity.
- **App-Level Isolation (光脑 Model)**: Inspired by the "光脑" (Light Brain) concept from science fiction, each app is an isolated, self-contained functional module. Apps are the unit of isolation, governance, and persistence — analogous to how an OS isolates processes, AgentSystem isolates apps. No app directly accesses another app's data or context.
- **User Commands → Workflows → App Operations**: Users never directly manipulate app internals. Every user command is translated into a workflow, and workflows are the control mechanism that starts, stops, pauses, modifies, queries, and composes apps. This is the primary interaction model.
- **Functional Modules = Persistable Apps**: Every functional capability in the system is an app. Apps are installable, persistable, and governable units. Skills are reusable capabilities that apps depend on.

The current design direction is:
- user interacts with the system through a control plane and unified gateway
- user commands become workflows that orchestrate app lifecycle operations
- the core platform stays thin and standard-oriented while higher-order behaviors should remain skill-centric wherever practical
- runtime operational telemetry and upgrade/evolution evidence are separated by design
- self-iteration must remain evidence-bound, user-governed, and cost-aware
- apps are defined as blueprints, installed as instances, and governed by runtime policy
- apps own separated namespaces for business and runtime data
- apps also own app-local shared context for internal execution and coordination
- apps can react to events and schedules
- runtime behavior can be reviewed into experience
- experience can be turned into candidate skills

---

## 2. Core Design Principles

### 2.1 App is the main product object
Users primarily interact with apps, not with low-level skills.

### 2.2 Skill is a reusable capability asset
Skills are versioned, replaceable, suggestible capability units. They are dependencies of apps and builders, not usually the top-level product unit.

### 2.3 Definition and instance are separate
- blueprint = definition template
- instance = installed lifecycle object

### 2.4 Data and runtime are separate
- app data persists with the app instance
- runtime state persists only as needed for recovery and supervision

### 2.5 Intelligence is selective
The system should use deterministic services first, and use intelligence mainly for abstraction, suggestion, diagnosis, and generation.

System capability skills should sit above stable core capability APIs/services:
- core protocols, stores, lifecycle, registry, and execution APIs remain the durable substrate
- reusable higher-level capabilities (especially requirement understanding, retrieval/evidence access, context shaping, workflow insight, governance/risk surfaces, prompt selection, and future model-assisted selection) should be exposed as system skills when feasible
- skill facades should wrap services rather than replace the underlying capability APIs

A lightweight requirement-understanding loop should exist before blueprint generation:
- first route the request (`app | skill | hybrid | unclear`)
- then build a minimal structured requirement spec
- then decide whether the request is ready, needs clarification, needs demonstration, or contains conflicting constraints
- only after that should later generation flows consume the request as a candidate blueprint/app/skill definition input
- when the request is ready and app-oriented, the system may emit a minimal blueprint draft as a handoff artifact rather than forcing later stages to re-parse raw user text
- that handoff artifact should already carry lightweight app-shape and runtime-profile cues (for example pipeline vs transform posture, ask-user invocation pressure, and offline/network expectations) so later control-plane and install paths start from a more stable draft
- for transform-style drafts, the builder may directly emit a `prompt.invoke` workflow step so blueprint generation captures the intended prompt-driven execution posture instead of leaving that structure implicit

The prompt-selection layer should sit between context compaction/evidence retrieval and future model invocation:
- it should consume working-set context plus retrieval-index entries instead of raw runtime history where possible
- it should expose a machine-readable selection policy rather than hiding ranking heuristics in opaque prompt code
- it should support explicit budget accounting (working-set tokens, reserved output tokens, per-evidence estimates)
- it should produce prompt-ready sections or a lightweight assembled prompt so downstream model calls can remain thin wrappers instead of reconstructing retrieval logic ad hoc
- it may also expose a direct model-ready invocation path for bounded prompt-selection-driven prompting, while still keeping selection and model invocation inspectable as separate layers in the contract
- when that path becomes operationally important, selection-to-model handoff should live in a dedicated prompt-invocation service rather than being trapped inside one capability handler
- workflow execution should be able to reuse that same service through a first-class module step (for example `prompt.invoke`) so prompt-driven tasks can be orchestrated without inventing a parallel prompt path
- the prompt invocation service should normalize model output and emit telemetry/evaluation records so prompt-driven orchestration does not become an observability blind spot
- workflow/runtime policy should retain the ability to gate prompt invocation (for example hard disable or require ask-user approval) so prompt-driven steps do not become a governance bypass
- prompt-invocation governance signals should be emitted into shared risk/evidence channels so repeated blocked or sensitive prompt paths contribute to later policy learning rather than disappearing inside workflow execution
- prompt-driven execution should also project into replay/acceptance/regression summaries via the core skill toolchain so it can participate in the same operator review loop as other candidate behaviors
- real nightly/manual governance execution responses may expose a derived `governance_rollout_summary` read model sourced from the same rollout/preflight truth, so operator clients can consume a stable compact decision view without owning payload reconstruction logic
- the real `/api/chat` path may asynchronously persist a derived `live_chat_observation` probe after response completion, and governance dashboards may expose `live_chat_observation_digest` as a compatibility-safe read-side summary sourced from that persisted truth rather than from inline request blocking
- nightly/manual governance cycles may pass a service session id into trigger application so `observation_digest` can be derived from merged fixed-regression and live-chat evidence instead of from synthetic regression probes alone
- trigger read models may derive additive `observation_topic` and `observation_lane_hint` from `topic_failure_stage_counts`, allowing downstream operator/refinement consumers to interpret live-chat evidence with finer lane hints while keeping core family/subdomain routing compatibility-safe
- refinement translation may consume those additive observation hints in descriptive text fields while preserving the existing `queue_note` structural shape, so rollout and priority parsers do not regress
- the self-iteration line may also expose additive asset summaries for regression history, live observation digest, governance dashboard/triggers, and refinement backlog, so model-facing consumers can reason over asset-level views instead of reconstructing raw persistence files
- self-iteration asset exposure should evolve toward a strategy surface, not just a flat list surface: the same read-only runtime asset may expose a whole-system Observe / Summarize / Act overview plus a derived `recommended_next_asset` navigator so model-facing callers can choose what to inspect next without inventing their own cross-asset reasoning every turn
- that strategy view should remain additive and compatibility-safe: it can summarize system layers and recommended navigation while leaving the underlying self-iteration summary assets and their existing query/list contracts intact
- the same strategy view may also expose additive `recommended_next_action` and `follow_up_actions` guidance so operators and models receive not only what to inspect next, but also which runtime asset method call should be made next and which adjacent inspections typically follow
- the strategy surface may further expose a compact phase-aware `route` that closes the loop across current pressure inspection, governance summarization, act-stage review, and validation return-to-observation, allowing callers to follow a short closed-loop path instead of a bag of unrelated suggestions
- to avoid fragmentation, the recommendation, action, follow-up, and route construction logic should live in shared strategy builders rather than accumulating as one-off branches inside one asset service, so later strategy surfaces can reuse the same policy assembly primitives
- app asset manifests must translate blueprint `required_skills` into AssetCenter dependency ids instead of copying raw skill ids directly; the runtime blueprint contract and the asset-install contract use different identifier spaces, and mixing them creates false missing-dependency warnings during build/install
- prompt-invocation acceptance should be allowed to incorporate richer post-execution signals (normalized response quality, workflow outcome hints, and explicit feedback) instead of depending only on coarse success proxies
- those richer signals should be structured and inspectable (empty text, very short text, expected-output satisfaction, workflow-success hint) rather than buried only inside one derived score
- the same quality signals should flow into operator-facing replay/acceptance/archive summaries so review tooling can explain prompt quality regressions without reconstructing them from raw payloads
- expected-output validation should cover a practical family of prompt-task shapes (JSON objects, slugs, markdown summaries, bullet lists, key/value text, approval decisions) so prompt-quality review can track more than one narrow output format
- executable skills should be integrated as a runtime-adapter concern, not as a special app-only primitive: app/workflow layers continue referencing skills by `skill_id`, while runtime dispatch decides whether the skill is builtin-callable or process-executable
- the executable-skill v1 contract should use a bounded JSON stdin/stdout protocol, manifest-declared entrypoint/runtime metadata, timeout governance, and structured runtime failure mapping (for example entrypoint missing / timeout / non-zero exit / invalid JSON / invalid result payload / skill-id mismatch) so generated script skills remain compatible with app management and review tooling
- generated executable skills should enter the system through normal skill registry/runtime paths, then be consumable by app install/workflow execution without introducing a separate app-specific adapter layer
- generated executable skill scaffolds should separate input/output/error contracts into distinct schema assets instead of collapsing them into one generic schema file, so registry validation, runtime envelope validation, and future review tooling can reason over request/result/error semantics independently
- manifest validation for executable/generated skills should check more than command-prefix policy: the install-time package gate should also verify non-empty entry metadata, entrypoint existence, timeout sanity, and schema-ref resolvability when a schema registry is available
- code/repository introspection paths should be evidence-bound across both prompt and execution layers: prompt rules may require reading real files first, but the runtime should also replay only bounded excerpts/search-hit summaries from introspection tools into subsequent model turns so later reasoning stays anchored to verified source evidence instead of bloated raw payloads or inferred structure
- anti-hallucination control should gradually converge toward a reusable evidence-grade contract instead of accumulating many scenario-specific hard-coded branches
- answer generation should distinguish at least between low-grade hints, read-confirmed excerpts, verified implementation facts, and runtime observations, and should not allow lower-grade evidence to inherit the wording privileges of higher-grade evidence
- product/governance skills should prefer diagnosing whether a failure comes from prompt weakness, execution semantics, evidence semantics, or termination strategy before prescribing scene-specific patches

### 2.5.6 Governance evolution roadmap (next-stage design)
The recently completed chat-regression governance loop, nightly automation control plane, and domain-aware refinement persistence establish a usable first-generation self-governance substrate.
The next design task is not to blindly add more signals, but to evolve that substrate into a disciplined, layered governance pipeline that can absorb more reality while remaining auditable and structurally stable.

The preferred next-stage roadmap is five phased layers.

#### Phase G1: Evidence refinement and replay-grade observation
The first next step should deepen the observation layer so governance is grounded not only in fixed prompt matrices but also in richer structured evidence.

Target capabilities:
- extend regression evidence from summary/result-level artifacts into finer-grained envelopes such as:
  - input evidence
  - routing evidence
  - tool-selection evidence
  - execution evidence
  - output evidence
  - user-feedback evidence
- introduce replay-grade regression samples derived from real production traces or accepted historical conversations rather than only manually curated prompt seeds
- allow governance summaries to distinguish whether a poor outcome came from:
  - requirement misunderstanding
  - routing error
  - missing evidence
  - bad tool execution
  - weak final answer shaping

Preferred design objects:
- `ObservationRecord`
- `EvidenceEnvelope`
- `ReplayRegressionSample`
- `GovernanceEvidenceDigest`

Boundaries:
- this phase should enrich evidence structure without yet requiring a full universal evidence graph
- replay ingestion should remain bounded and curated, not an unfiltered mirror of all production traffic

Success criteria:
- operator surfaces can explain not only that a regression happened, but what evidence layer it failed in
- nightly regression can include a bounded replay-backed slice in addition to the fixed canonical prompt matrix

#### Phase G2: Contradiction tree and governance taxonomy
The current system can already distinguish `automation_control_plane` from `regression_quality`.
The next step should refine that binary split into a contradiction tree so governance can represent finer classes of failure without flattening them into one warning list.

Target taxonomy direction:
- `automation_control_plane`
  - schedule_trigger_failure
  - retry_recovery_failure
  - degraded_automation_loop
- `regression_quality`
  - prompt_policy_risk
  - evidence_governance_risk
  - execution_semantics_risk
  - answer_shaping_risk
  - cost_efficiency_risk

Required behaviors:
- signals should carry `domain`, `subdomain`, and `signal`
- operator summary should surface both the top contradiction and the contradiction family
- refinement memory should preserve contradiction family so later review can detect repeated structural failure classes

Success criteria:
- the system can tell whether two regressions are instances of the same contradiction family or unrelated symptoms
- prioritization can operate at both signal level and contradiction-family level

#### Phase G3: Domain-specific refinement and rollout policies
The current implementation already persists different queue-note and hypothesis semantics for automation vs regression risks.
The next step should let those differences influence actual execution policy, not only stored text.

Target capabilities:
- domain-specific verification checklists
- domain-specific rollout queue lanes
- domain-specific approval rules
- domain-specific remediation templates
- domain-specific rollback posture

Illustrative direction:
- automation-control-plane items may require stronger runtime validation, health stabilization checks, and lower tolerance for risky rollout
- regression-quality items may prefer faster prompt/evidence iteration cycles, replay-based acceptance, and lower-cost experimentation loops

Preferred objects or fields:
- `queue_domain`
- `verification_profile`
- `rollout_policy_profile`
- `approval_posture`

Success criteria:
- two items with equal severity but different contradiction families do not automatically flow through the same remediation path
- operator review can see why one queued item requires stricter validation than another

#### Phase G4: Human feedback and accepted-practice return flow
A governance loop remains incomplete if it only circulates system-generated observations.
The next phase should explicitly connect operator decisions, user feedback, and accepted production outcomes back into refinement memory.

Target capabilities:
- attach explicit human/operator confirmation to regression findings
- attach user-visible acceptance or dissatisfaction signals to governance evidence
- preserve whether a refinement was accepted because:
  - tests improved
  - operator confirmed the diagnosis
  - production outcomes improved
  - user feedback improved
- distinguish system-internal confidence from socially validated usefulness

Preferred objects:
- `FeedbackEvidenceRecord`
- `OperatorConfirmationRecord`
- `AcceptedPracticeRecord`

Success criteria:
- refinement memory can explain not only what the system believed, but what was later confirmed by operators or users
- future prioritization can weight human-confirmed contradictions above purely model-internal suspicions

#### Phase G5: Full governance pipeline orchestration
After evidence refinement, contradiction taxonomy, differentiated execution policy, and human-return flow are in place, the final step should be to make governance itself a first-class long-running pipeline.

Target layered pipeline:
1. observe
2. organize
3. diagnose
4. prioritize
5. refine
6. verify
7. rollout
8. review

This should eventually become a reusable governance substrate rather than a special-purpose regression bundle.
That means:
- governance stages should have explicit contracts
- each stage should emit auditable artifacts
- later apps or skills should be able to reuse the same governance pipeline shape with different probes and policy profiles

Preferred future services:
- `GovernanceObservationService`
- `GovernanceDiagnosisService`
- `GovernancePrioritizationService`
- `GovernanceRefinementService`
- `GovernanceVerificationService`
- `GovernanceRolloutService`

Success criteria:
- governance stops being a growing set of adjacent helpers and becomes an explicit operating capability of the platform
- the same pipeline shape can later govern prompt systems, skill systems, executable skills, or app workflows under shared evidence and policy discipline

#### Roadmap guardrails
This roadmap should follow several guardrails:
- do not collapse evidence, governance policy, and execution into one fat module again
- prefer typed intermediate artifacts over hidden prompt-only judgments
- let high-risk rollout remain slower and more verified than low-risk prompt tuning
- keep replay/observation bounded and auditable
- preserve user governance and human override over autonomous mutation
- treat cost and operator attention as first-class constraints, not afterthoughts

#### Why this roadmap fits the current architecture
This roadmap is a continuation of the current design direction, not a reset.
It extends the already-established sequence:
- observe through regression and nightly automation
- summarize through dashboard/operator summary
- act through triggers and refinement persistence
- separate policy from aggregation
- move toward evidence-bound self-governance

In practical terms, it evolves the current system from a first useful governance loop into a reusable governance operating model for the broader AgentSystem platform.

### 2.5.7 Practice-first governance method and architectural mapping
The governance roadmap above is consistent with a practice-first systems method:
- reality produces signals
- signals become bounded evidence
- evidence is organized into contradictions
- contradictions are prioritized by domain and severity
- prioritized contradictions are translated into differentiated remediation paths
- remediation returns to practice for verification

Architecturally, that maps to:
- regression / replay / runtime observation -> practice acquisition
- evidence digests / ledgers / automation health -> investigation and organization
- contradiction family + signal priority -> principal-contradiction identification
- domain-aware refinement + queue policy -> differentiated treatment
- nightly verification + operator review + rollout evidence -> return-to-practice validation

The long-term product implication is that AgentSystem should become not merely a more capable responder, but a more disciplined governed system that improves by structured confrontation with reality rather than by prompt-only improvisation.

Network reachability and intelligence availability are separate concerns:
- an app may have network but should still avoid intelligent calls by default
- an app may be offline-capable while still carrying optional intelligent enhancements
- intelligent invocation should be governed by policy, not by mere model availability

### 2.5.1 Evidence-grade governance for anti-hallucination control
The system should treat anti-hallucination control as an evidence-governance discipline rather than a prompt-only discipline.

A preferred design direction is:
- tool execution produces not only replay text but also typed evidence semantics
- answer generation consumes an evidence ledger or equivalent structured fact surface
- wording privileges depend on evidence grade, not only on whether the model appears cautious
- low-grade evidence should fail closed into uncertainty instead of being promoted into concrete implementation claims

This governance should preferably be implemented through reusable contracts in shared engine / interpreter / result-processing layers, so future high-risk surfaces can inherit the same control model without duplicating many scene-specific rules.

Potential grade model for the current phase:
- `hint`
- `excerpt`
- `verified_fact`
- `runtime_observation`

Potential contract responsibilities:
- ToolCallingEngine: preserve bounded evidence metadata and provenance hints
- ToolCallingInterpreter: enforce answer-grade compatibility before emitting final user text
- higher-level PM/governance skills: diagnose whether failures arise from prompt weakness, execution semantics, evidence semantics, or termination strategy before recommending patches

### 2.5.2 Evidence ledger contract (initial proposal)
To support reusable hallucination governance, the system should introduce an evidence ledger abstraction that survives tool execution and remains available to final answer shaping.

The evidence ledger should record bounded, typed evidence items such as:
- `grade`: `hint | excerpt | verified_fact | runtime_observation`
- `source_type`: for example `search_files | read_file | exec_shell | http_response | runtime_service`
- `source_ref`: file path, endpoint, command target, asset id, or other bounded source reference
- `snippet`: bounded supporting content or normalized observation
- `truncated`: whether the supporting snippet was truncated
- `scope`: static code, runtime state, configuration, documentation, filesystem, network, or mixed
- `supports_claims`: machine-readable list of claim classes this evidence is allowed to support
- `metadata`: optional bounded fields such as line range, match count, status code, timestamp, or observation tags

Initial contract split:
- ToolCallingEngine should emit or preserve ledger-ready evidence items when tools execute
- ToolCallingInterpreter should consume the ledger, or a derived summary, when deciding whether final answer wording exceeds the available evidence grade
- later governance / PM skills may inspect ledger summaries to diagnose whether a failure came from missing evidence, weak evidence, bad promotion, or bad answer shaping

A practical initial rule is:
- tool replay text remains useful for model continuity
- but user-facing answer privileges should ultimately depend on ledger semantics rather than replay text alone

### 2.5.3 OPT-005 P2 implementation slice (initial mapping plan)
The first implementation slice should avoid introducing a fully generalized evidence system everywhere at once.
Instead, it should land a narrow but reusable vertical slice across the current high-risk introspection path.

Recommended slice order:
1. map current introspection tool outputs into ledger-ready evidence items inside `ToolCallingEngine`
   - `search_files` → `hint`
   - `read_file` → `excerpt`
   - bounded result metadata should populate `source_ref`, `snippet`, `truncated`, and initial `supports_claims`
2. attach ledger summaries or raw ledger items to `ToolCallingResult`
3. let `ToolCallingInterpreter` consume ledger semantics first for high-risk answer gating, while preserving backward compatibility with existing final-text behavior for non-governed paths
4. keep the initial governed path intentionally narrow: repository/code introspection, configuration claims, and implementation-detail claims

Initial non-goals for P2:
- no attempt to fully solve every answer type in one pass
- no requirement to infer `verified_fact` automatically from every excerpt yet
- no broad rewrite of all tool handlers before the contract proves useful in one production-critical path

Success criteria for P2:
- the engine emits structured ledger-ready evidence for current introspection tools
- the interpreter can choose between replay text and ledger semantics for high-risk answer shaping
- existing OPT-004 regression scenarios can be re-expressed in terms of ledger-compatible answer privileges

The intended evolutionary chain is:
- practice
- experience
- skill suggestion
- future workflow/app refinement

This should be treated as a disciplined world-model loop rather than a purely verbal planning loop.

### 2.5.5 Self / World / Value governance and the cognition-practice loop
AgentSystem should not evolve into a system that merely imitates human conversation style. Its deeper target is to become a governed cognition-action system that can know itself, know the world, understand value priorities, and then act on reality through evidence-bound practice.

This direction can borrow method from practice-first thought traditions: start from reality, form provisional understanding, verify through action, revise through contradiction, and then expand capability only after evidence accumulates. In product terms, the system should learn by a disciplined cycle of observation -> organization -> judgment -> verification -> action -> review, rather than by prompt-only confidence.

#### Self model: how the system knows itself
The system should maintain an explicit self-model rather than relying on implicit model behavior.
At the center of that self-model is capability self-awareness: the system should know what it can do, what it cannot do, what it can only do through tools, and what remains uncertain until observation or verification occurs.
That self-model should answer at least:
- what kind of system it is
- what responsibilities it owns
- what capabilities are currently available
- what capabilities are unavailable or uncertain
- which facts require explicit observation before they can be claimed
- what level of confidence supports the current answer or action
- what policy boundary prevents further action

AgentSystem may learn from human cognitive method, but it must not assume human-equivalent cognition.
In practical terms, the system should explicitly recognize that:
- it is not a human subject with continuous lived experience
- it does not have human-style instant associative recall
- it cannot access all relevant knowledge without explicit retrieval, storage, or tool use
- its response quality and speed are constrained by context budget, tool latency, and verification cost
- unobserved content is not known fact, only a possible hypothesis or guess

A practical self-model should gradually surface machine-readable fields such as:
- `role_identity`
- `mission`
- `capability_state`
- `tool_dependence_state`
- `boundary_state`
- `confidence_state`
- `uncertainty_state`
- `policy_state`
- `human_equivalence_state`

Without this layer, the system tends to overclaim, over-execute, hide technical limits, or fail to stop when clarification or verification is required.

#### World model: how the system knows reality
The system should treat world knowledge as a reality-modeling discipline rather than a memory accumulation contest.
It should continuously distinguish among:
- raw observation
- candidate clue
- bounded evidence
- provisional claim
- contradiction
- unresolved question
- verified result

This aligns with current evidence-bound introspection and deterministic analysis work:
- repository reads, script scans, API calls, runtime observations, and telemetry are world-contact operations
- summaries should be treated as bounded cognitive products, not reality itself
- promotion from clue to claim should require explicit evidence semantics

Representative future objects for this layer may include:
- `ObservationRecord`
- `EvidenceEnvelope`
- `EvidenceLedger`
- `Claim`
- `ContradictionRecord`
- `VerificationResult`

#### Value model: how the system prioritizes action
A capable system still fails if it lacks a stable value-ordering model.
AgentSystem should therefore carry explicit value priorities that govern tradeoffs, not just task completion pressure.

Preferred value ordering for the current phase:
1. truthfulness over pleasing fluency
2. safety and boundary discipline over reckless completion
3. verified practice over abstract confidence
4. long-term reusable mechanism over repeated narrow patching
5. user-helpfulness over blind agreement
6. auditability over opaque cleverness

These values should influence not only text generation but also execution, review, and later self-refinement.

#### Cognition-practice loop: from knowing to changing reality
The system should unify current and future modules through a six-part cognition-practice loop:
1. world observation
   - read files, inspect runtime state, collect telemetry, query services, run bounded scripts
2. cognitive organization
   - group observations by topic, bound excerpts, normalize evidence, record contradictions and unknowns
3. judgment and hypothesis
   - produce provisional claims with evidence grade, confidence, and explicit unverified points
4. practice and verification
   - run tests, perform actions, compare outcomes, verify whether a claim survives contact with reality
5. action orchestration
   - choose skills, workflows, deterministic routes, clarification paths, and fallbacks based on evidence and policy
6. review and refinement
   - record why a strategy worked or failed, preserve negative evidence, and feed reusable lessons into future governance and capability evolution

This loop should become the default architectural interpretation of "knowing the world and changing the world" inside AgentSystem.
The system should not stop at analysis. It should use practice to correct cognition, and use corrected cognition to improve future action.

#### Current module mapping
The present codebase already contains partial implementations of this direction:
- world observation
  - file reads, repository introspection, `exec_shell`, deterministic scan profiles, runtime services, telemetry capture
- cognitive organization
  - deterministic pre-step aggregation, bounded scan results, topic-aware scan profiles, prompt/context shaping
- judgment and hypothesis
  - evidence-grade governance direction, bounded summarizer prompts, explicit "未证实" discipline, refinement hypothesis objects in later governance flows
- practice and verification
  - unit/integration/E2E tests, grouped regression execution, runtime verification paths, approval-gated workflow execution
- action orchestration
  - gateway interpreter, workflow engine, skill dispatch, dynamic path composition, script-first routing, ask-clarification paths
- review and refinement
  - telemetry/evolution evidence split, proposal review, verification, rollout, failed-hypothesis preservation, governance dashboard paths

This means the architecture does not need a ground-up rewrite. The immediate task is to converge scattered capabilities into a shared cognition-governance model.

#### Immediate design implications
Near-term implementation and refactoring should follow these consequences:
- answer generation should expose uncertainty when evidence grade is insufficient instead of optimizing for surface completeness
- deterministic introspection paths should become the first pilot of the full cognition-practice contract, not remain a one-off workaround
- telemetry should begin recording not only latency/success but also profile-hit, fallback, overreach-risk, and verification outcomes where practical
- refinement should preserve negative lessons such as disproven strategies, false-positive scan themes, and repeated fallback patterns
- future planning/dynamic-path modules should consume evidence and policy state, not only user intent text

#### Implementation posture
This governance model should be integrated as architecture, not as ideology-only prose.
That means it should eventually appear in:
- design principles
- machine-readable contracts
- planner/interpreter decision rules
- workflow and verification policy
- review/refinement feedback loops
- operator-facing observability surfaces

The preferred rollout order is:
1. codify the self/world/value and cognition-practice model in design docs
2. pilot the contract in deterministic introspection and evidence-bound answer shaping
3. extend it into workflow verification, refinement governance, and future planning modules

### 2.5.4 Tool-loop governance skill architecture
For multi-turn tool use, the preferred near-term control surface should be a compact skill-oriented guidance architecture rather than many embedded tool-specific branches in engine/interpreter code.

Recommended shape:
- one compact top-level tool-loop governor skill that encodes only the universal loop discipline
- multiple branch files for scenario-specific retrieval/execution strategies
- branch selection should depend on task shape, not on hardcoded truth rankings for particular tool names

The top-level governor should focus on:
- whether to continue calling tools
- whether the requested precision has been achieved
- whether the next step should be another direct tool call or a script-first execution strategy
- when to stop with explicit uncertainty

Suggested initial branch families:
- repository / code introspection
- runtime observation
- script-first execution strategy
- stop rules / convergence control

This preserves a thin core while making loop discipline inspectable, evolvable, and less likely to fragment into scattered prompt patches.

The platform core should own:
- standard contracts
- telemetry/event envelopes
- collection policy and safety boundaries
- primitive compare / evaluate / publish / rollback / archive operations

Higher-order workflows such as:
- next-version generation
- replay/test orchestration
- acceptance review
- archive/report generation
- publish/rollback orchestration

should remain skill-oriented wherever practical. This preserves extensibility while keeping the core implementable and governable.

### 2.8 Runtime telemetry and upgrade evidence are separate
The system should maintain two distinct observation planes:
- lightweight online telemetry for runtime/control-plane usage
- append-only upgrade/evolution evidence for replay, acceptance, and self-iteration

On top of those planes, the system should begin forming an evidence-promotion layer:
- raw event/log references remain cheap and mostly non-prompt-facing
- repeated patterns are aggregated into draft summaries
- repeated or high-pressure patterns are elevated into suspicious signals
- only promoted evidence and retrieval-index entries should become primary candidates for future prompt/context retrieval
- context-compaction and future prompt-assembly paths should prefer promoted/indexed evidence summaries over re-reading raw operational history

This separation reduces online cost while preserving the historical evidence needed for improvement.

### 2.9 Cost-aware optimization, not intelligence-first optimization
Candidate improvements should be judged by:
- user experience
- task success
- token efficiency
- latency efficiency
- stability and rollback posture

The design should prefer reducing unnecessary work before adding heavier intelligence.

### 2.10 Core-skill toolchain before broad self-expansion
The preferred long-term expansion path is:
- keep the platform core small
- establish a governed core-skill toolchain for generation, testing, acceptance, archive, publish, and rollback
- let that toolchain produce and govern additional ordinary skills
- reserve direct core changes for standards, safety boundaries, and primitive runtime/governance capabilities

In other words, the system should mainly grow by adding and governing skills, not by continuously enlarging the core platform.

This world-model loop should be treated as a disciplined runtime-governed process rather than a purely verbal planning loop:
- investigate reality through runtime signals, user corrections, and concrete outcomes
- transform observations into explicit contradictions, hypotheses, and proposed changes
- test those changes in bounded workflows before wider rollout
- keep revision tied to evidence, not only narrative plausibility
- record the loop as first-class system objects (hypothesis, experiment, verification result, rollout decision) so refinement is inspectable rather than hidden inside one-shot proposal text
- persist those refinement-loop objects through the runtime store and expose query surfaces so system learning remains visible across process rebuilds
- keep verification execution pluggable: runtime paths may invoke real grouped regression, while tests should be able to inject a bounded executor so learning-loop regression coverage stays fast and deterministic
- treat rollout as a governable queue, not only an immediate promote/hold judgment; queue items and overview read models should make the learning loop operationally visible
- rollout queue items should support explicit lifecycle transitions (approve/apply/reject/rollback) so refinement promotion is operationally governed rather than hidden in one-off side effects
- the system should preserve negative learning signals through failed-hypothesis records and expose recent refinement history through dashboard read models, so self-improvement can incorporate both success and disproof
- refinement loop decisions should become failure-aware: previously disproven hypotheses should raise repeat-risk scores, annotate verification with gating reasons, and block naive promotion of repeated strategies
- refinement governance should expose lightweight operator read models parallel to workflow observability, including filtered rollout-queue pages, failed-hypothesis archive pages, and aggregate stats summaries keyed by app/hypothesis/proposal filters
- refinement governance should also expose a dashboard-style aggregate surface that composes overview + stats + recent queue/failure slices so operators can review learning-governance state through one higher-level read model
- refinement operator endpoints should share a small API-side filter builder, mirroring workflow observability, so future query knobs stay aligned across queue/stats/dashboard surfaces
- refinement operator workflows should also expose a one-call summary read model that merges proposal inventory, review state, latest priority decision, and governance dashboard slices so operators do not need to stitch multiple endpoints together for routine triage
- refinement governance API-path coverage may be maintained as a dedicated slower integration slice rather than being forced into the main workflow golden path, preserving faster regression loops for the common operator path
- runtime wiring should support test-only opt-outs for model-backed self-refinement and grouped-regression verification so deterministic API-path tests can exercise refinement flows without accidentally invoking remote model calls or recursive full-suite regressions
- model-backed self-refinement should be explicit opt-in at runtime wiring time (`AGENTSYSTEM_ENABLE_MODEL_REFINER=1`), with fallback proposal synthesis remaining the default path when the feature is not deliberately enabled
- refinement governance page-style responses should mirror workflow observability structure by nesting counts/has-more state under `meta`, which reduces contract drift between the two operator surfaces
- shared operator-facing pagination semantics should live in a common contract model (`OperatorPageMeta`), with domain-specific extensions such as workflow unresolved counts layering on top instead of redefining the whole shape
- shared operator-facing query semantics should likewise live in a common base filter model (`OperatorFilterParams`), with workflow/refinement filters layering on domain-specific selectors without redefining common pagination/time-window fields
- shared operator dashboard semantics should live in a common overview/stats core (`OperatorDashboardCore`), while domain-specific dashboards add their own recent timeline/queue/archive sections on top
- API-side operator filter construction should be centralized in a shared helper module (`app/api/operator_filters.py`), while thin compatibility wrappers may remain temporarily to avoid churn during migration
- generated/runtime skill manifests should begin carrying explicit risk metadata (`risk_level`, network/filesystem/shell allowances), and script adapters should be validated against an allowlisted command-prefix policy before registration/runtime use
- generated app assembly should enforce a default deny gate for risky skills (e.g. networked, shell, filesystem-write, or explicitly high-risk manifests), so self-iteration cannot silently turn high-risk assets into auto-install/auto-run apps
- generated-app policy gates should emit structured skill diagnostics (stage=`assemble`, kind=`policy_blocked`) with machine-readable policy reasons, so future approval or override layers can consume them cleanly
- reviewer-managed skill risk decisions should live in a dedicated persisted policy store, and generated app assembly should consult active overrides before enforcing default deny behavior for risky skills
- risk governance should emit and persist a lightweight event trail (`policy_blocked`, `override_approved`, `override_revoked`) so audit and observability layers can expose more than the latest policy decision snapshot
- the risk policy layer should also provide stats and dashboard-shaped read models (overview + stats + recent events) consistent with the broader operator-surface direction in the system
- app rollout governance should extend beyond activate/rollback controls to include explicit release-to-release comparison, so operators can inspect note / required-skill / runtime-policy / runtime-profile / app-shape drift before promoting or reverting a release
- app rollout governance should also expose a release-history summary contract, so control-plane readers do not need to reconstruct active/draft/rollback posture or timeline ordering from raw release lists alone
- app registry/control-plane reads should also provide a single summary contract for common operator views, aggregating active release posture, release counts, rollback availability, app shape, and runtime profile without requiring client-side joins across multiple registry endpoints
- app governance should also expose a registry-wide overview contract so operators can triage draft-bearing or rollback-relevant apps before drilling into per-app compare/history surfaces
- app governance should further expose an explicit attention/triage contract that explains *why* an app needs review (draft present, rollback target available, recently rolled back) instead of forcing operators to infer urgency from overview fields alone
- app operator surfaces should also support lightweight action records (for example acknowledging or dismissing an attention case) so review state can affect what the triage queue shows without requiring full release-state mutation
- skill suggestion / self-iteration entry paths should be able to consume risk governance summaries so generated recommendations can adapt toward lower-risk execution forms when the governance layer shows recent blocking pressure
- that governance context should include blueprint-materialization policy pressure specifically, allowing suggestions to bias not only toward lower-risk execution but also toward callable materialization when shell/script forms are being blocked
- blueprint materialization should consume `prefer_callable_materialization` as an active default-selection hint when the caller does not explicitly choose an adapter, so governance-aware defaults influence real artifact shape selection
- governance-aware suggestions should project that bias into blueprint-level `safety_profile` metadata (preferred risk level, local-only preference, shell/network/write allowances) so later generation/materialization stages can inherit safer defaults
- `SkillFactoryService` should expose a creation-defaults bridge from `SkillBlueprint.safety_profile` into concrete capability/risk defaults, even before the full generated-skill authoring pipeline consumes it end-to-end
- `SkillFactoryService` should also expose a blueprint-to-`SkillCreationRequest` bridge so governance-aware defaults can enter the concrete request object used by later materialization/registration flows
- the API layer should expose blueprint materialization as a first-class path, allowing stored `SkillBlueprint` records to become real skills while preserving the request defaults derived from governance-aware safety metadata
- blueprint materialization responses should expose both the intermediate creation request and the final registered skill state so governance-aware propagation can be validated end-to-end
- blueprint materialization should interpret safety metadata as active policy, not passive annotation: for example, low-risk blueprints should be able to block shell/script materialization unless a future explicit override layer authorizes it
- blueprint materialization should consult skill risk overrides under a dedicated `blueprint_materialization` scope before enforcing shell/script blocks, keeping approval logic aligned with the existing risk-governance subsystem
- blueprint-derived risk defaults should not stop at request construction: they must remain part of the concrete `SkillCreationRequest` contract and flow through skill authoring into the final `SkillManifest`, so validators and downstream governance inspect the same risk state the blueprint materialization logic intended
- when a scoped blueprint-materialization override intentionally authorizes shell/script materialization, the resulting authored manifest should carry explicit elevated shell-risk metadata rather than relying on an invisible side channel, preserving consistency across API diagnostics, manifest validation, registry state, and future audit surfaces
- generated app assembly should reuse `AppProfileResolverService` so blueprint skeleton defaults (execution mode, idle behavior, operator-facing overview/run/activity views, and the default generated-agent task) reflect the runtime properties of the selected skills instead of always emitting the same bare service shell
- the inferred `AppRuntimeProfile` should be promoted into both generated blueprints and registry-entry summaries, not kept only inside installer/runtime state, so pre-install control-plane reads and generated-app UIs can consume the same normalized runtime capability view that installation later persists into `AppInstance`
- generated app assembly should also perform a lightweight app-shape classification using available skill metadata (ids, descriptions, tags, and basic schema field signals) so the emitted role/task/view wording differs across text-oriented apps, structured-data transforms, and multi-step pipelines without requiring manual blueprint editing
- the same inferred app runtime profile exposed pre-install in blueprints/registry summaries should also be returned from install results, keeping pre-install and post-install control-plane reads aligned around one normalized runtime capability contract
- lightweight generated-app shape classification should also persist into explicit `app_shape` fields on `AppBlueprint`, `AppRegistryEntry`, and `AppInstallResult`, leaving human-facing wording as a presentation layer rather than the only place where app-type semantics exist

---

## 3A. Telemetry and upgrade-evidence architecture

The observation layer should be split into two coordinated but distinct planes.

### 3A.1 Online telemetry plane
This plane serves ordinary runtime and control-plane needs.

It should hold lightweight, queryable records such as:
- interaction summaries
- step/invocation summaries
- token and latency totals
- success/failure outcomes
- explicit and implicit feedback
- version bindings across app / skill / agent / policy

This plane should stay cheap enough to keep enabled by default in light mode.

### 3A.2 Upgrade/evolution evidence plane
This plane serves replay, acceptance, version comparison, optimization, publish, and rollback analysis.

It should use:
- append-only writing
- time-sliced files
- JSONL-oriented event storage
- event-first records with optional aggregate snapshots

It should not become a hard dependency for the online serving path.

### 3A.3 Collection policy model
Observation policy should support:
- global scope
- app scope
- skill scope
- agent scope
- task-type scope

Collection levels should support at least:
- off
- light
- medium
- heavy
- custom

Default posture should be light collection enabled, with expensive raw capture disabled unless explicitly enabled.

### 3A.4 Skill-extensible upgrade evidence
The core platform should define the baseline telemetry/event envelope.

Skills may append structured upgrade-oriented evidence on top of that envelope, for example:
- replay-sample reasons
- optimization hints
- domain-specific acceptance notes
- archive/report metadata

This preserves consistency while keeping higher-order evolution workflows skill-centric.

### 3A.5 Buildability boundary
The full conceptual model should not be interpreted as mandatory Day-1 scope.

The first implementation should prefer:
- light telemetry over heavy capture
- simple scope precedence over policy combinatorics
- append-only evidence substrate over full autonomous optimization loops

If a requirement cannot be delivered without making the core too heavy, it should be deferred, reduced, or shifted into a skill-level workflow.

### 3A.6 Core vs core-skill vs ordinary-skill boundary
The architecture should preserve three distinct layers:

- **core platform**: standards, runtime, registry, telemetry, policy, primitive governance operations
- **core skills**: the governed toolchain for generation, replay selection, testing, acceptance, archive, publish, and rollback workflows
- **ordinary skills**: business or domain skills that can be generated, revised, tested, accepted, published, and rolled back through the governed toolchain

Ordinary skills should not directly mutate platform-core standards or safety boundaries. Those changes must remain under explicit platform or core-skill governance.

## 3. High-level Architecture

```text
[ User / API / Chat Input ]
            |
            v
[ LLM Interaction Gateway ] ← NEW: unified natural-language entry point
            |
            v
[ Conversation Router (LLM) ] ← NEW: intent classification + parameter extraction
            |
            v
[ Control Plane / Interaction Gateway ]
            |
            +------------------------------+
            |                              |
            v                              v
[ App Catalog ] ----> [ App Registry ] ----> [ App Installer ]
            |                                 |
            |                                 v
            |                          [ App Instance ]
            |                                 |
            v                                 v
[ Lifecycle Manager ] <----> [ Runtime Host ] <----> [ Scheduler ]
                                      |                  |
                                      |                  v
                                      |            [ Event Bus ]
                                      |
                                      +------> [ App Shared Context Store ]
                                      |
                                      v
                              [ App Data Store ]
                                      |
                                      v
                              [ Runtime Persistence ]

[ Experience Store ] <---- [ Practice Review ] <---- [ Event Log + Data Records ]
        |
        v
[ Skill Suggestion Service ]
```

---

## 4. Object Model

## 4.1 Capability Layer

### Module
Deterministic building block such as file, state, event, auth, config, or network operations.

### Skill
Reusable capability asset, versioned and controlled. Skills may be manually replaced, rolled back, enabled, disabled, or suggested from experience.

Each skill should also carry capability tags used by the platform for automatic classification and runtime governance:
- intelligence level (`L0_deterministic | L1_assisted | L2_semantic | L3_autonomous`)
- network requirement (`N0_none | N1_optional | N2_required`)
- runtime criticality (`C0_build_only | C1_optional_runtime | C2_required_runtime`)
- execution locality (`local | hybrid | remote`)
- invocation default (`automatic | ask_user | explicit_only`)
- risk level

A skill should evolve toward a package model that includes:
- metadata / manifest
- machine-readable input/output/error contracts
- one or more runtime adapters
- dependency declarations
- examples and validation assets

To make normal skill authoring viable for self-iteration, the platform now also treats skill packaging as a first-class builder concern:
- `SkillAuthoringService` can generate consistent registry entries for callable and script skills
- built-in skills should use the same authoring path as normal skills where possible
- tests should verify authoring output separately from runtime execution so skill authors can localize failures faster

The next packaging layer now starts to exist as an API-facing factory path:
- `SkillFactoryService` can create a skill from an API request
- skill contracts are registered into the schema registry during creation
- the newly created skill is immediately smoke-tested through the runtime
- registered skills can be assembled into a minimal app blueprint through an interface instead of hand-written blueprint editing
- the generated app path can also be installed and executed immediately, which makes contract mismatches in the authoring path visible early
- generated app assembly now supports step-level inputs plus explicit step mapping declarations so multi-step generated apps can be composed without hand-editing blueprints
- generated mappings are compiled into the same declarative workflow reference shape already understood by runtime execution (`$from_step` / `$from_inputs`) instead of introducing a separate execution path
- generated mapping targets may point into nested downstream object fields, which keeps the API-facing assembly surface compact while preserving schema-first workflow validation
- generated mappings may also carry lightweight assembly-time transforms/defaults (for example lowercase/uppercase/stringify/wrap-object and literal/default injection) so common app-composition cleanup can happen without inventing a separate workflow DSL
- generated app assembly now computes conservative schema-based mapping suggestions between adjacent steps and returns unresolved required downstream fields
- high-confidence adjacent-step suggestions are auto-applied into generated workflow inputs only when they do not conflict with explicit user mappings or hand-authored step inputs
- generated skills should persist as assets and be reloaded into registry/runtime on bootstrap so the path becomes durable rather than session-only
- generated skill failures should surface as structured diagnostics with stage/kind/hint metadata instead of only raw error strings
- structured diagnostics should be able to carry a suggested retry request so failure handling can flow into the next generation attempt
- blueprint validation now has two semantics: strict validation for explicit operator/API checks, and a relaxed install-time path that still validates declared dependencies/contracts while allowing intentionally partial runtime workflows and demo catalog blueprints to install without every step skill being predeclared or prebootstrapped
- retry semantics now treat the latest `partial` execution as the canonical retry target so workflow recovery and observability remain aligned even when a partial run has no explicit failed step ids
- paginated workflow timeline responses should preserve backward-compatible list-like access (`len`, iteration, indexing) at the service model layer even though the public contract is page-shaped

## 4.2 Definition Layer

### RequirementIntent
Structured routing output from user requirement intake.

### DemonstrationRecord
Observed user demonstration used for extraction.

### AppBlueprint
Defines:
- goal
- roles
- tasks
- workflows
- views
- required modules
- required skills
- storage plan
- runtime policy

### RuntimePolicy
Defines:
- execution mode (`service | pipeline`)
- activation mode
- restart policy
- persistence level
- idle strategy
- restart limit
- network behavior
- intelligence behavior
- invocation governance for optional intelligent steps

## 4.3 Runtime Layer

### AppInstance
Installed lifecycle object containing:
- blueprint id
- owner user id
- status
- installed version
- execution mode
- runtime policy
- data namespace root

### LifecycleEvent
Represents state transitions.

### RuntimeLease
Tracks current runtime health and heartbeat.

### RuntimeCheckpoint
Captures resumable runtime snapshots.

### ScheduleRecord
Defines interval or event-based task triggering.

### SupervisionPolicy / SupervisionStatus
Define restart behavior and current supervision state.

### EventRecord / EventSubscription
Represent internal system events and their subscriptions.

## 4.4 Data / Evolution Layer

### DataNamespace
Represents an isolated namespace for:
- app_data
- runtime_state
- system_metadata
- skill_assets

### DataRecord
Structured record within a namespace.

### AppSharedContext / AppContextEntry
Structured app-local shared execution context containing:
- app identity and description
- current goal and current stage
- grouped entries for facts, artifacts, decisions, questions, constraints, and open loops

This context is separate from the user-facing control AI context and is intended to support autonomous app-local execution.

### ExperienceRecord
Structured runtime, demonstration, or human knowledge asset.

### SkillBlueprint
Structured candidate reusable skill artifact.

### PracticeReviewResult
Structured output of reviewing recent runtime practice.

### SkillSuggestionResult
Structured output of turning experience into a candidate skill blueprint.

---

## 5. Layered Services

## 5.1 Requirement Routing
Current implementation uses a rule-driven `RequirementRouter` to classify user intent and decide whether demonstration is needed.

## 5.2 Skill Control Interface
`SkillControlService` acts as a protected human override layer for skill lifecycle control.

## 5.3 Experience Store
`ExperienceStore` is currently an in-memory asset store for:
- experiences
- skill blueprints

It supports linking skill blueprints to related experiences.

## 5.4 Demonstration Extraction
`DemonstrationExtractor` converts demonstrations into:
- an experience record
- a skill blueprint

## 5.5 App Registry and Installer
`AppRegistryService` stores blueprint definitions.
`AppInstallerService` converts blueprints into installable instances and provisions namespaces.

The intended next-step installer behavior is:
- inject a mandatory deterministic system skill baseline for every app
- initialize app configuration records and defaults
- classify runtime skills from capability tags
- resolve an app runtime profile from the installed skill set
- determine whether direct start, optional-intelligence start, or intelligence-required start is appropriate
- reject blueprints that deterministically violate runtime-skill validation rules before provisioning instances

## 5.6 Lifecycle and Runtime
`AppLifecycleService` manages valid state transitions.
`AppRuntimeHostService` manages runtime lease, checkpoint, pending tasks, and health updates.

## 5.7 Scheduler and Supervisor
`SchedulerService` manages interval and event schedules.
`SupervisorService` manages failure observation, restart attempts, and circuit-open protection.

Proposal review and priority analysis now also support context-aware operation:
- review records can retain context-derived notes
- proposal prioritization can consider open loops, decisions, constraints, and paused stage
- contradiction and recommendation output can reflect app-local execution context

## 5.8 Event Bus
`EventBusService` records internal events, supports subscriptions, and triggers event schedules.

## 5.9 App Data Store
`AppDataStore` provisions and manages namespaces and records for apps and global skill assets.

## 5.10 Interaction Gateway / Control Plane Boundary
`InteractionGateway` is the main command entry point for the user-facing control plane.
It routes user commands to app catalog entries and triggers install/open/run flows.

The user-facing layer should not require users to manually pick low-level technical runtime classes such as offline-capable, intelligence-optional, or direct-start mode.
Instead, the control plane should expose the resolved app behavior after platform inference.

The control plane is responsible for:
- user-facing interaction
- app routing and orchestration
- high-level intervention
- inspection and explanation

The control plane is not required for every app-internal execution step.

## 5.11 App Shared Context
`AppContextStore` maintains app-local shared execution context so an app can continue internal work without routing every step through the control plane.

Alongside context, each app should also have a deterministic app-configuration surface exposed through a built-in `system.app_config` skill. This config surface should be separate from runtime state and separate from app-local reasoning context.

The current implementation now binds shared context into install and interaction flows:
- installer ensures a context exists when an app instance is provisioned
- blueprint goal can seed the initial current goal
- service-app open updates current stage/goal and records the latest user command as an open loop
- pipeline execution records the latest run artifact and marks the context archived after completion
- context inspection can optionally include runtime overview for joined operational debugging

## 5.12 Skill classification, runtime profile resolution, and invocation governance
The intended platform direction is to classify skills internally and aggregate them into an app runtime profile.

### Skill classification
A future `SkillClassificationService` should infer or validate capability tags from skill declarations, dependencies, and execution traits.

### App profile resolution
A future `AppProfileResolver` should aggregate runtime-capable skills and determine:
- highest runtime intelligence level
- runtime network requirement
- offline capability
- direct-start support
- default ask-before-intelligence behavior

Build-only skills should influence builder flows but should not inflate runtime classification for apps that no longer depend on intelligence once installed.

### Invocation governance
At runtime, the system should evaluate in order:
1. whether a step can be completed deterministically
2. whether network is required and available
3. whether intelligence is required and available
4. whether policy requires user confirmation before spending intelligence resources

This allows the platform to distinguish:
- no network
- no intelligence
- intelligence available but not worth invoking automatically

## 5.13 Skill package, contract, and adapter model
A skill should be treated as a runnable capability package rather than only a named dependency.

### Skill package shape
A future skill package should include at least:
- manifest metadata (`id`, `name`, `version`, purpose, category)
- capability tags
- runtime adapter declaration
- input/output/error schema references
- dependency declarations (modules, skills, binaries, services)
- validation examples and optional healthcheck metadata

The intended direction is schema-first:
- machine-readable contract/schema definitions should be the authoritative source for runtime envelopes
- adapter declarations should describe how execution happens, not redefine payload shapes independently
- future inspection/debugging surfaces should reuse the same contract source instead of inventing parallel representations

### Runtime adapters
The runtime layer should support multiple adapter types behind one execution contract:
- `callable` for in-process deterministic handlers
- `script` for local script execution with structured JSON input/output
- `rpc` for local or remote services
- `binary` for compiled executables or tools
- `frontend` / human-interaction adapters where user interaction is the execution surface

### Unified execution envelope
Regardless of adapter, skill execution should converge on a common request/response envelope so workflow orchestration, policy enforcement, observability, and retry remain uniform.

## 5.14 Skill orchestration and dispatch
Skill execution should be orchestrator-mediated by default.

The platform should prefer workflow/runtime dispatch over uncontrolled skill-to-skill direct calling so it can uniformly apply:
- schema validation
- timeout and retry handling
- audit and tracing
- permission checks
- network and intelligence policies
- cost/token governance

Direct skill-to-skill dependencies may still be declared, but dependency resolution should remain visible to the orchestrator/runtime layer.

## 5.15 Skill validation and compile-time checking
A future `SkillValidationService` should validate skill packages before they become active runtime capabilities.

Validation should be treated as three connected layers rather than one undifferentiated check:

### Package validation
Runs before a skill becomes active or installable.
It should cover at least:
- manifest completeness
- schema correctness
- adapter resolvability
- consistency between capability tags and actual runtime form
- compatibility between declared dependencies and the execution environment

### Compile-time app/workflow validation
Runs before app install or runtime activation.
It should cover at least:
- required skill existence
- workflow step / skill contract compatibility
- input/output mapping compatibility between steps
- misuse of build-only skills inside runtime execution paths
- mismatch between app runtime profile and runtime-critical skill requirements

### Runtime envelope validation
Runs at dispatch boundaries even after compile-time checks pass.
It should cover at least:
- request/input payload validation before adapter execution
- response/output/error validation after adapter execution
- adapter/runtime failures being distinguished from contract violations

This separation follows a stricter schema-first model:
- contract validity and adapter executability are different dimensions
- invalid packages should be blocked before activation
- invalid workflow wiring should be blocked before install/start
- invalid runtime payloads should fail as envelope violations rather than silently poisoning downstream steps

## 5.16 Core skill design principles reference
The canonical core-skill design principles are maintained in:

- `docs/skill-design-principles.md`

That document should be consulted before introducing new system-default skills, runtime-governance skills, or builder/intelligent platform skills.

## 5.17 Practice Review
`PracticeReviewService` reviews recent runtime events and data records, then distills them into an experience.

The current implementation also folds app shared context into review output:
- current goal and stage can enrich the practice summary
- recent context entries can become review evidence and tags
- the resulting experience can retain more app-local execution state instead of only event/data traces

## 5.18 Skill Suggestion
`SkillSuggestionService` generates candidate reusable skill blueprints from stored experiences.

---

## 6. Main Runtime Flows

## 6.1 User command -> service app
1. user command enters interaction gateway
2. catalog matches the app
3. installer ensures the instance exists
4. lifecycle ensures app reaches `installed`
5. runtime host starts the service app
6. app remains available for ongoing work

## 6.2 User command -> pipeline app
1. user command enters interaction gateway
2. catalog matches a pipeline app
3. installer ensures the instance exists
4. runtime host starts the app
5. task is enqueued
6. runtime host stops the app after execution

## 6.3 Runtime event -> event schedule
1. event bus publishes an event
2. scheduler locates matching event schedules
3. pending task is enqueued into runtime host
4. event is recorded in persistent log

## 6.4 Runtime practice -> experience
1. runtime generates event log and data records
2. practice review inspects recent facts
3. app shared context is joined as local execution evidence
4. review generates an experience summary
5. experience is stored for later reuse

## 6.5 Experience -> suggested skill
1. a stored experience is selected
2. self-refinement can combine experience with app shared context to generate patch proposals
3. skill suggestion service generates a candidate skill blueprint
4. suggestion may remain advisory or be persisted into the skill store

---

## 7. State and Lifecycle Design

## 7.1 App lifecycle states
Supported states:
- draft
- validating
- compiled
- installed
- running
- paused
- stopped
- failed
- upgrading
- archived

## 7.2 App execution modes
### Service app
Used for long-running, event-aware, reopenable app instances.

### Pipeline app
Used for one-shot execution, after which runtime stops but data may remain.

## 7.3 Runtime supervision model
The supervision model supports:
- failure observation
- restart attempts
- restart caps
- circuit-open protection

---

## 8. Data Design

## 8.1 Namespace split
Each installed app gets:
- `app_data`
- `runtime_state`
- `system_metadata`

The system also maintains:
- `global:skill_assets`

## 8.2 Persistence split
Current file-based persistence stores:
- app instances
- lifecycle events
- runtime leases
- runtime checkpoints
- runtime tasks
- schedules
- supervision state
- registry entries
- registry blueprints
- namespaces
- data records
- event log
- event subscriptions

## 8.3 Why this split matters
This prevents app business data from being confused with ephemeral runtime state, and keeps skill assets from turning into hidden app data.

---

## 9. Intelligence / Evolution Design

## 9.1 Demonstration to experience and skill
Demonstration extraction is the first path from observed user behavior to reusable system assets.

## 9.2 Practice review as runtime learning
Practice review creates a feedback loop from actual runtime behavior to explicit experience records.

## 9.3 Experience to skill suggestion
Skill suggestion turns explicit experience into reusable capability proposals without automatically mutating the system.

This keeps a safe evolution boundary:
- observe
- summarize
- suggest
- optionally persist
- future human or system approval can decide actual adoption

---

## 10. Safety and Control Boundaries

### 10.1 Immutable human override
The skill control surface should remain protected and deterministic.

### 10.2 Suggestion is not direct mutation
Practice review and skill suggestion should not silently rewrite core skills or app structure.

### 10.3 Runtime services remain deterministic
Lifecycle, installer, data provisioning, scheduling, and event dispatch should remain deterministic.

---

## 11. Current Implemented Boundary Summary

At the current stage the codebase already implements a meaningful subset of the target design:
- requirement routing
- skill control
- experience store
- demonstration extraction
- lifecycle manager
- runtime host
- scheduler
- supervisor
- interaction gateway
- runtime persistence
- app registry
- installer
- app data namespaces
- event bus
- practice review
- experience-to-skill suggestion

This means the project is no longer just schema scaffolding; it already contains an initial operating skeleton plus an early practice-driven evolution loop.

---

## 12. Near-term Design Gaps

The next most important missing pieces are:
- richer workflow execution beyond the current minimal deterministic executor
- app data operations as workflow primitives
- contradiction / priority analysis for better focus
- app/workflow refinement based on suggested skills
- suggested-skill refinement should not require callers to manually materialize each suggested blueprint first; the platform should provide a one-call orchestration path that materializes missing suggested skills and assembles an app blueprint from them
- stronger permission and policy enforcement
- durable production-grade persistence backends
- layered context compaction and retrieval

These gaps are now grouped into three execution phases:
- **Phase 4**: workflow execution enhancement (`docs/phase-4-workflow-execution-enhancement.md`)
- **Phase 5**: suggested-skill -> app refinement closure (`docs/phase-5-refinement-and-assembly-closure.md`)
- **Phase 6**: governance, production persistence, and layered context (`docs/phase-6-governance-persistence-and-layered-context.md`)

## 13. Layered Context Architecture

To avoid context explosion, runtime context should be split into layers instead of accumulated into one prompt-sized blob.

### 13.1 Layers
- **L0 Working Set**: current goal, stage, active constraints, current open loops, most recent critical outputs
- **L1 Task/App Summary**: compact summary of progress, major decisions, unresolved issues, key artifacts
- **L2 Execution Detail**: step/node-level details, logs, intermediate inputs/outputs, failure traces
- **L3 Long-term Experience**: reusable lessons, patterns, and promoted operational knowledge

### 13.2 Design Rules
- prompts should prefer L0 + selected L1, not raw L2
- L2 detail should remain queryable by reference rather than always loaded
- compaction should preserve decisions, constraints, open loops, artifacts, and references
- app/workflow execution history should serve as a primary detail source for compaction
- app shared context should remain the active mutable layer, while summaries become derived state

### 13.3 Minimal Implementation Plan
- add `ContextCompactionService`
- persist `context_summaries`
- build a `working_set` view derived from app context + recent execution history
- expose APIs for compaction, listing layers, and retrieving working set
- keep detail in `app_contexts`, `workflow_execution_history`, and `skill_executions`

Current implementation note:
- context compaction summaries and policies are now persisted and reloaded through the runtime state store
- working-set and summary metadata now include recent workflow/skill references for selective deep retrieval
- policy-driven auto compaction can now trigger on workflow completion, workflow failure, and stage change
- runtime persistence inspection now exposes `context_summaries` and `context_policies`
- a minimal workflow executor now exists for workflow execution
- it supports deterministic step skeletons for `state.set`, `state.get`, and event emission
- it also includes placeholders for `human_task` and `skill` steps so workflows can preserve unresolved work in context
- step outputs can now be passed into later steps through lightweight `$from_step` / `$from_inputs` references
- step-level conditional execution is supported through simple `when` checks
- workflow execution returns an aggregated outputs summary for completed/skipped steps and step outputs
- event-driven workflow subscriptions can now auto-trigger workflow execution from published internal events
- `skill` steps now support a minimal dispatch contract through `SkillRuntimeService`, with registered handlers, structured request/result payloads, input mapping, failure capture, execution persistence, and blueprint-declared allowlist enforcement
- workflow and skill execution now expose basic observability surfaces: execution history, filtered failure inspection, latest execution lookup, and skill failure listings
- workflow failure inspection can now be narrowed by app instance, workflow id, and failed step id for faster operator triage
- workflow execution results now carry explicit `failed_step_ids` so failure review and future policy/retry tooling can identify the exact blocked steps without re-scanning every step payload
- retrying the latest failed workflow now returns structured before/after comparison metadata so operators can see whether status changed and which failed steps were resolved, unchanged, or newly introduced
- workflow diagnostics can now aggregate latest execution, latest true failure, latest retry, and a lightweight recovery-state summary for operator-facing failure panels
- diagnostics can also be narrowed to one failed step path, and a dedicated latest-recovery view exposes the newest retry outcome in a UI-friendly shape
- diagnostics/recovery aggregation logic is now separated into a dedicated workflow observability service instead of being duplicated in the API layer or mixed into execution code, and `/workflows/overview` exposes a combined response for operator dashboards
- workflow overview now includes a first-class health summary (`health_status`, `severity`, unresolved failure count, latest failed steps, retry presence) so dashboards can render status without inferring it client-side
- health rules now explicitly distinguish `healthy`, `failing`, and `unknown` (partial-without-failed-steps) states, avoiding ambiguous dashboard status inference
- health/severity classification is now centralized inside the observability service, making future additions like `recovering` rule changes or dashboard severities easier to evolve safely
- observability health classification now follows a small explicit rule table, which makes state additions and severity tuning less error-prone than growing nested conditionals
- observability queries now support recent-N and unresolved-only history retrieval, which is a better fit for dashboards/timelines than forcing clients to slice the full execution history themselves
- timeline-style observability summaries are now exposed as compact event cards (failure / retry / recovery / completed / partial) so UI surfaces do not need to transform full execution payloads just to render an incident feed
- timeline queries now support `since` windows and cursor-style pagination so the observability layer can back activity feeds without forcing clients to pull and sort the entire history each time
- observability queries now share an explicit filter model so API handlers and service logic stop drifting in which query knobs they support
- API contract coverage now checks that diagnostics/history/timeline honor the same filter semantics, and observability-history formally supports time-window filtering alongside unresolved/recent slicing
- history and timeline now share the same page-style response shape, and API-side filter construction is centralized through a small helper instead of repeated inline parameter assembly
- paged observability responses now carry lightweight metadata (`returned_count`, `unresolved_count`, `has_more`, `window_since`, `next_cursor`) so dashboard clients can render state without re-deriving feed stats client-side
- an aggregate stats summary is now available for workflow observability, giving operator-facing surfaces totals for executions, failures, retries, recoveries, unresolved states, and latest activity time
- a dashboard-style read model now combines overview, stats, and recent timeline into one higher-level payload for operator surfaces that want one coherent summary call
- observability internals are now starting to split into helper/query modules so API parsing and low-level classification/filter logic stop accumulating inside one large service/file
- registry/operator surfaces now include release comparison, overview, attention, and control-plane summary read models so release review can happen through one coherent operator-facing contract
- operator-facing workflow/refinement surfaces now share small common filter/page/dashboard contracts, reducing drift between related read models while keeping domain-specific payloads explicit
- workflow execution telemetry now binds app versions through the installed app-instance version surface, avoiding contract drift between installer/runtime models and executor telemetry
- recent failed workflow executions can now be retried directly from stored execution history and inputs
- execution can write app data, append shared-context artifacts, persist runtime execution records, and publish internal events
