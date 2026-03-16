from __future__ import annotations

from fastapi import HTTPException

from app.services.lifecycle import LifecycleError
from app.services.runtime_host import RuntimeHostError
from app.services.skill_control import SkillControlError


def map_domain_error(error: Exception) -> HTTPException:
    if isinstance(error, (SkillControlError, LifecycleError, RuntimeHostError)):
        message = str(error)
        if "not found" in message.lower():
            return HTTPException(status_code=404, detail=message)
        return HTTPException(status_code=400, detail=message)
    return HTTPException(status_code=500, detail="Internal server error")
