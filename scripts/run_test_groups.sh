#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/project/AgentSystem"
PYTEST="$ROOT/.venv/bin/python -m pytest -q"

cd "$ROOT"

run_group() {
  local name="$1"
  shift
  echo "==> GROUP: $name"
  $PYTEST "$@"
  echo
}

run_group core \
  tests/unit/test_requirement_router.py \
  tests/unit/test_skill_control.py \
  tests/unit/test_experience_store.py \
  tests/unit/test_demonstration_extractor.py \
  tests/unit/test_skill_authoring.py \
  tests/unit/test_skill_manifest.py \
  tests/unit/test_skill_manifest_validator.py \
  tests/unit/test_skill_metadata.py

run_group runtime \
  tests/unit/test_lifecycle_runtime.py \
  tests/unit/test_scheduler_supervisor.py \
  tests/unit/test_event_bus.py \
  tests/unit/test_health.py \
  tests/unit/test_registry_installer.py \
  tests/unit/test_blueprint_validation.py \
  tests/unit/test_app_profile_resolver.py

run_group context_data \
  tests/unit/test_app_data_store.py \
  tests/unit/test_app_context_store.py \
  tests/unit/test_app_config_service.py \
  tests/unit/test_context_policy.py \
  tests/unit/test_context_compaction.py \
  tests/unit/test_context_runtime_view_serialization.py \
  tests/unit/test_system_app_config_skill.py \
  tests/unit/test_system_context_skill.py \
  tests/unit/test_system_state_and_audit_skills.py

run_group workflows \
  tests/unit/test_workflow_executor.py \
  tests/unit/test_workflow_observability.py \
  tests/unit/test_workflow_execution_failure_observability.py \
  tests/unit/test_workflow_subscription.py \
  tests/unit/test_observability.py

run_group intelligence \
  tests/unit/test_practice_review.py \
  tests/unit/test_skill_suggestion.py \
  tests/unit/test_self_refinement.py \
  tests/unit/test_priority_analysis.py \
  tests/unit/test_proposal_review.py

run_group generated \
  tests/unit/test_generated_callable_skill.py \
  tests/unit/test_generated_skill_persistence.py \
  tests/unit/test_generated_skill_durability.py \
  tests/unit/test_generated_app_durability.py \
  tests/unit/test_skill_factory_api.py \
  tests/unit/test_skill_diagnostics_api.py \
  tests/unit/test_skill_runtime.py \
  tests/unit/test_skill_runtime_adapters.py

run_group operator_paths \
  tests/unit/test_interaction_gateway.py \
  tests/unit/test_bootstrap_smoke.py \
  tests/unit/test_golden_path_integration.py \
  tests/unit/test_api_golden_path.py \
  tests/e2e/test_api_usable_flow.py

echo "All test groups passed."
