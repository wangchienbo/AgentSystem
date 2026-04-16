from __future__ import annotations

from app.models.policy_authority import AuthorityDecisionResult, AuthorityPolicyRecord, AuthoritySummary
from app.services.runtime_state_store import RuntimeStateStore


class PolicyAuthorityError(ValueError):
    pass


class PolicyAuthorityService:
    def __init__(self, store: RuntimeStateStore) -> None:
        self._store = store
        self._policies: dict[str, AuthorityPolicyRecord] = {}
        self._load()

    def set_policy(self, policy: AuthorityPolicyRecord) -> AuthorityPolicyRecord:
        self._policies[policy.scope] = policy
        self._persist()
        return policy

    def get_policy(self, scope: str) -> AuthorityPolicyRecord:
        return self._policies.get(scope, AuthorityPolicyRecord(scope=scope))

    def list_policies(self) -> list[AuthorityPolicyRecord]:
        return list(self._policies.values())

    def enforce(self, *, scope: str, reviewer: str = "", reason: str = "", automatic: bool = False) -> AuthorityDecisionResult:
        policy = self.get_policy(scope)
        if automatic and not policy.allow_automatic:
            raise PolicyAuthorityError(f"automatic action disabled for scope: {scope}")
        if policy.require_reviewer and not reviewer:
            raise PolicyAuthorityError(f"reviewer required for scope: {scope}")
        if policy.allowed_reviewers and reviewer and reviewer not in policy.allowed_reviewers:
            raise PolicyAuthorityError(f"reviewer not authorized for scope: {scope}")
        if policy.require_reason and not reason:
            raise PolicyAuthorityError(f"reason required for scope: {scope}")
        return AuthorityDecisionResult(
            scope=scope,
            allowed=True,
            reason=reason,
            reviewer_required=policy.require_reviewer,
            reviewer=reviewer,
        )

    def get_summary(self) -> AuthoritySummary:
        items = self.list_policies()
        return AuthoritySummary(
            items=items,
            active_scope_count=len(items),
            reviewer_required_scope_count=sum(1 for item in items if item.require_reviewer),
            automatic_scope_count=sum(1 for item in items if item.allow_automatic),
        )

    def _persist(self) -> None:
        self._store.save_mapping("policy_authority", self._policies)

    def _load(self) -> None:
        raw = self._store.load_json("policy_authority", {})
        self._policies = {key: AuthorityPolicyRecord.model_validate(value) for key, value in raw.items()}
