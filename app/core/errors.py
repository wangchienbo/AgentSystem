from __future__ import annotations

from fastapi import HTTPException

from app.services.app_catalog import AppCatalogError
from app.services.app_context_store import AppContextStoreError
from app.services.app_data_store import AppDataStoreError
from app.services.app_installer import AppInstallerError
from app.services.app_config_service import AppConfigError
from app.services.app_registry import AppRegistryError
from app.services.event_bus import EventBusError
from app.services.lifecycle import LifecycleError
from app.services.system_skill_service import SystemSkillError
from app.services.context_skill_service import ContextSkillError
from app.services.practice_review import PracticeReviewError
from app.services.priority_analysis import PriorityAnalysisError
from app.services.proposal_review import ProposalReviewError
from app.services.runtime_host import RuntimeHostError
from app.services.scheduler import SchedulerError
from app.services.self_refinement import SelfRefinementError
from app.services.skill_control import SkillControlError
from app.services.skill_manifest_validator import SkillManifestValidationError
from app.services.skill_suggestion import SkillSuggestionError
from app.services.supervisor import SupervisorError
from app.services.blueprint_validation import BlueprintValidationError
from app.services.skill_validation import SkillValidationError
from app.models.skill_diagnostics import SkillDiagnosticError
from app.services.skill_factory import SkillFactoryError


def map_domain_error(error: Exception) -> HTTPException:
    if isinstance(error, SkillDiagnosticError):
        diagnostic = error.diagnostic.model_dump(mode="json")
        status_code = 400
        if diagnostic["kind"] in {"reload_error", "execution_error"}:
            status_code = 422
        return HTTPException(status_code=status_code, detail=diagnostic)
    if isinstance(error, (SkillControlError, SkillManifestValidationError, SkillValidationError, BlueprintValidationError, SkillFactoryError, LifecycleError, RuntimeHostError, SchedulerError, SupervisorError, AppCatalogError, AppRegistryError, AppInstallerError, AppDataStoreError, AppContextStoreError, AppConfigError, SystemSkillError, ContextSkillError, EventBusError, PracticeReviewError, SkillSuggestionError, SelfRefinementError, ProposalReviewError, PriorityAnalysisError)):
        message = str(error)
        if "not found" in message.lower():
            return HTTPException(status_code=404, detail=message)
        return HTTPException(status_code=400, detail=message)
    return HTTPException(status_code=500, detail="Internal server error")
