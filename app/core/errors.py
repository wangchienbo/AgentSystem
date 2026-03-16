from __future__ import annotations

from fastapi import HTTPException

from app.services.app_catalog import AppCatalogError
from app.services.app_data_store import AppDataStoreError
from app.services.app_installer import AppInstallerError
from app.services.app_registry import AppRegistryError
from app.services.event_bus import EventBusError
from app.services.lifecycle import LifecycleError
from app.services.practice_review import PracticeReviewError
from app.services.runtime_host import RuntimeHostError
from app.services.scheduler import SchedulerError
from app.services.self_refinement import SelfRefinementError
from app.services.skill_control import SkillControlError
from app.services.skill_suggestion import SkillSuggestionError
from app.services.supervisor import SupervisorError


def map_domain_error(error: Exception) -> HTTPException:
    if isinstance(error, (SkillControlError, LifecycleError, RuntimeHostError, SchedulerError, SupervisorError, AppCatalogError, AppRegistryError, AppInstallerError, AppDataStoreError, EventBusError, PracticeReviewError, SkillSuggestionError, SelfRefinementError)):
        message = str(error)
        if "not found" in message.lower():
            return HTTPException(status_code=404, detail=message)
        return HTTPException(status_code=400, detail=message)
    return HTTPException(status_code=500, detail="Internal server error")
