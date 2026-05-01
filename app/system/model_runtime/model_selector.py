from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.system.model_runtime.model_client_registry import ModelRuntimeRecord


class ModelSelectionError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedModelSelection:
    model_id: str
    reason: str
    record: ModelRuntimeRecord


class ModelSelector:
    def resolve(
        self,
        *,
        model_records: list[ModelRuntimeRecord],
        preferred_model: str | None,
        fallback_model: str | None,
        minimum_requirements: dict[str, Any] | None = None,
    ) -> ResolvedModelSelection:
        minimum_requirements = minimum_requirements or {}
        records_by_id = {record.model_id: record for record in model_records if record.enabled}

        preferred = self._pick(records_by_id, preferred_model)
        if preferred and preferred.healthy and self._meets_requirements(preferred, minimum_requirements):
            return ResolvedModelSelection(model_id=preferred.model_id, reason="preferred", record=preferred)

        fallback = self._pick(records_by_id, fallback_model)
        if fallback and fallback.healthy and self._meets_requirements(fallback, minimum_requirements):
            return ResolvedModelSelection(model_id=fallback.model_id, reason="fallback", record=fallback)

        raise ModelSelectionError("No healthy model satisfies the minimum requirements")

    def _pick(self, records_by_id: dict[str, ModelRuntimeRecord], model_id: str | None) -> ModelRuntimeRecord | None:
        if not model_id:
            return None
        return records_by_id.get(model_id)

    def _meets_requirements(self, record: ModelRuntimeRecord, minimum_requirements: dict[str, Any]) -> bool:
        metadata = record.metadata or {}
        for key, expected in minimum_requirements.items():
            if metadata.get(key) != expected:
                return False
        return True
