from __future__ import annotations

from fastapi import HTTPException

from app.system.runtime.app_catalog import AppCatalogError
from app.system.runtime.app_context_store import AppContextStoreError
from app.system.runtime.app_data_store import AppDataStoreError
from app.app_installer import AppInstallerError
from app.system.runtime.app_config_service import AppConfigError
from app.system.runtime.app_registry import AppRegistryError
from app.persistence.event_bus import EventBusError
from app.system.runtime.lifecycle import LifecycleError
from app.skills.system_skill_service import SystemSkillError
from app.persistence.context_skill_service import ContextSkillError
from app.governance.practice_review import PracticeReviewError
from app.governance.priority_analysis import PriorityAnalysisError
from app.governance.proposal_review import ProposalReviewError
from app.system.runtime.runtime_host import RuntimeHostError
from app.system.runtime.scheduler import SchedulerError
from app.refinement.self_refinement import SelfRefinementError
from app.skills.skill_control import SkillControlError
from app.skills.skill_manifest_validator import SkillManifestValidationError
from app.skills.skill_suggestion import SkillSuggestionError
from app.ai.supervisor import SupervisorError
from app.refinement.blueprint_validation import BlueprintValidationError
from app.skills.skill_validation import SkillValidationError
from app.models.skill_diagnostics import SkillDiagnosticError
from app.skills.skill_factory import SkillFactoryError
from app.refinement.requirement_blueprint_builder import RequirementBlueprintBuilderError


def map_domain_error(error: Exception) -> HTTPException:
    if isinstance(error, SkillDiagnosticError):
        diagnostic = error.diagnostic.model_dump(mode="json")
        status_code = 400
        if diagnostic["kind"] in {"reload_error", "execution_error"}:
            status_code = 422
        return HTTPException(status_code=status_code, detail=diagnostic)
    if isinstance(error, (SkillControlError, SkillManifestValidationError, SkillValidationError, BlueprintValidationError, SkillFactoryError, RequirementBlueprintBuilderError, LifecycleError, RuntimeHostError, SchedulerError, SupervisorError, AppCatalogError, AppRegistryError, AppInstallerError, AppDataStoreError, AppContextStoreError, AppConfigError, SystemSkillError, ContextSkillError, EventBusError, PracticeReviewError, SkillSuggestionError, SelfRefinementError, ProposalReviewError, PriorityAnalysisError)):
        message = str(error)
        if "not found" in message.lower():
            return HTTPException(status_code=404, detail=message)
        return HTTPException(status_code=400, detail=message)
    return HTTPException(status_code=500, detail="Internal server error")
