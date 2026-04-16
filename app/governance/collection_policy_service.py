from __future__ import annotations

from app.models.telemetry import CollectionPolicyRecord
from app.services.runtime_state_store import RuntimeStateStore


class CollectionPolicyService:
    def __init__(self, store: RuntimeStateStore) -> None:
        self.store = store
        self._policies: dict[str, CollectionPolicyRecord] = {}
        self._load()

    def set_policy(self, policy: CollectionPolicyRecord) -> CollectionPolicyRecord:
        self._policies[self._key(policy.scope_type, policy.scope_id)] = policy
        self._persist()
        return policy

    def get_policy(self, scope_type: str, scope_id: str) -> CollectionPolicyRecord | None:
        return self._policies.get(self._key(scope_type, scope_id))

    def resolve_policy(self, *, app_id: str | None = None, skill_id: str | None = None) -> CollectionPolicyRecord:
        if skill_id:
            policy = self.get_policy("skill", skill_id)
            if policy:
                return policy
        if app_id:
            policy = self.get_policy("app", app_id)
            if policy:
                return policy
        policy = self.get_policy("global", "default")
        if policy:
            return policy
        default = CollectionPolicyRecord(scope_type="global", scope_id="default")
        self.set_policy(default)
        return default

    def list_policies(self) -> list[CollectionPolicyRecord]:
        return list(self._policies.values())

    def _persist(self) -> None:
        self.store.save_mapping("telemetry_collection_policies", self._policies)

    def _load(self) -> None:
        raw = self.store.load_json("telemetry_collection_policies", {})
        self._policies = {
            key: CollectionPolicyRecord.model_validate(value)
            for key, value in raw.items()
        }

    @staticmethod
    def _key(scope_type: str, scope_id: str) -> str:
        return f"{scope_type}:{scope_id}"
