from __future__ import annotations

from app.services.context_compaction import ContextCompactionService
from app.services.log_evidence_service import LogEvidenceService


class PromptSelectionService:
    def __init__(
        self,
        context_compaction: ContextCompactionService,
        log_evidence: LogEvidenceService,
    ) -> None:
        self._context_compaction = context_compaction
        self._log_evidence = log_evidence

    def select_for_prompt(
        self,
        app_instance_id: str,
        limit: int = 5,
        *,
        query: str = "",
        category: str | None = None,
        max_prompt_tokens: int | None = None,
        reserved_output_tokens: int = 256,
        working_set_token_estimate: int = 400,
        per_evidence_token_estimate: int = 120,
        strategy: str = "balanced",
        include_prompt_assembly: bool = True,
    ) -> dict:
        working_set = self._context_compaction.build_working_set(app_instance_id).model_dump(mode="json")
        working_set_summary = working_set.get("metadata", {}).get("evidence_summary") or {}
        evidence_page = self._log_evidence.search_index(
            query=query,
            app_instance_id=app_instance_id,
            category=category,
            limit=None,
        )
        ranked_items = sorted(
            evidence_page.items,
            key=lambda item: self._ranking_tuple(item, query=query, category=category, strategy=strategy),
            reverse=True,
        )

        budget = self._build_budget(
            max_prompt_tokens=max_prompt_tokens,
            reserved_output_tokens=reserved_output_tokens,
            working_set_token_estimate=working_set_token_estimate,
            per_evidence_token_estimate=per_evidence_token_estimate,
            requested_limit=limit,
            available_candidates=len(ranked_items),
        )
        selected_items = ranked_items[: budget["selected_limit"]]
        selected = [self._serialize_index_entry(item, query=query, category=category, strategy=strategy) for item in selected_items]
        selected_topics = [item["topic"] for item in selected]
        selected_scope_keys = [item["scope_key"] for item in selected]
        prompt_sections = self._build_prompt_sections(working_set=working_set, selected_evidence=selected)

        result = {
            "app_instance_id": app_instance_id,
            "working_set": working_set,
            "selected_evidence": selected,
            "selection_policy": {
                "prefer_promoted_index_entries": True,
                "max_evidence_items": budget["selected_limit"],
                "avoid_raw_history": True,
                "ranking_strategy": strategy,
                "budget_mode": "token_aware" if max_prompt_tokens is not None else "count_only",
                "query_aware": bool(query),
                "category_bias": category or "",
            },
            "prompt_budget": budget,
            "selection_summary": {
                "selected_count": len(selected),
                "selected_topics": selected_topics,
                "selected_scope_keys": selected_scope_keys,
                "working_set_evidence_count": working_set_summary.get("count", 0),
            },
            "prompt_sections": prompt_sections,
        }
        if include_prompt_assembly:
            result["assembled_prompt"] = self._assemble_prompt(prompt_sections)
        return result

    def search_evidence(
        self,
        *,
        query: str = "",
        app_instance_id: str | None = None,
        category: str | None = None,
        limit: int = 5,
        strategy: str = "balanced",
    ) -> dict:
        page = self._log_evidence.search_index(
            query=query,
            app_instance_id=app_instance_id,
            category=category,
            limit=None,
        )
        ranked_items = sorted(
            page.items,
            key=lambda item: self._ranking_tuple(item, query=query, category=category, strategy=strategy),
            reverse=True,
        )
        truncated_items = ranked_items[:limit]
        items = [
            self._serialize_index_entry(item, query=query, category=category, strategy=strategy)
            for item in truncated_items
        ]
        return {
            "items": items,
            "meta": {
                "returned_count": len(items),
                "total_count": len(ranked_items),
                "filtered_count": len(ranked_items),
                "has_more": len(ranked_items) > limit,
                "window_since": None,
                "next_cursor": None,
            },
            "retrieval_policy": {
                "query_mode": "substring_keyword_match",
                "ranking_strategy": strategy,
                "category_filter_applied": bool(category),
                "app_filter_applied": app_instance_id is not None,
                "prefer_evidence_over_signal": True,
                "freshness_bias": True,
            },
        }

    def _serialize_index_entry(self, item, *, query: str, category: str | None, strategy: str) -> dict:
        query_match_score = self._query_match_score(item, query, category)
        evidence_type_score = self._evidence_type_score(item)
        freshness_score = self._freshness_score(item)
        rank_score = self._rank_score(item, query=query, category=category, strategy=strategy)
        return {
            "source_type": item.source_type,
            "source_id": item.source_id,
            "topic": item.topic,
            "summary": item.short_summary,
            "priority": item.priority,
            "scope_key": item.scope_key,
            "app_instance_id": item.app_instance_id,
            "workflow_id": item.workflow_id,
            "skill_id": item.skill_id,
            "keywords": list(item.keywords),
            "freshness_ts": item.freshness_ts.isoformat(),
            "match_score": query_match_score,
            "evidence_type_score": evidence_type_score,
            "freshness_score": freshness_score,
            "rank_score": rank_score,
        }

    def _ranking_tuple(self, item, *, query: str, category: str | None, strategy: str) -> tuple[int, int, object]:
        query_match = self._query_match_score(item, query, category)
        evidence_type = self._evidence_type_score(item)
        freshness = self._freshness_score(item)
        if strategy == "query_first":
            return (query_match, evidence_type + item.priority, item.freshness_ts)
        if strategy == "recency_first":
            return (freshness, query_match + evidence_type + item.priority, item.freshness_ts)
        return (query_match + evidence_type, item.priority + freshness, item.freshness_ts)

    def _rank_score(self, item, *, query: str, category: str | None, strategy: str) -> int:
        query_match = self._query_match_score(item, query, category)
        evidence_type = self._evidence_type_score(item)
        freshness = self._freshness_score(item)
        if strategy == "query_first":
            return query_match * 100 + (evidence_type + item.priority) * 10 + freshness
        if strategy == "recency_first":
            return freshness * 100 + (query_match + evidence_type + item.priority) * 10
        return (query_match + evidence_type) * 100 + (item.priority + freshness) * 10

    def _query_match_score(self, item, query: str, category: str | None) -> int:
        score = 0
        if category and item.topic == category:
            score += 5
        needle = query.strip().lower()
        if not needle:
            return score
        if needle in item.topic.lower():
            score += 5
        if needle in item.short_summary.lower():
            score += 4
        if any(needle in keyword.lower() for keyword in item.keywords):
            score += 3
        if needle in item.scope_key.lower():
            score += 2
        return score

    def _evidence_type_score(self, item) -> int:
        score = 0
        if item.source_type == "evidence":
            score += 5
        elif item.source_type == "signal":
            score += 2
        if item.topic == "workflow_failure":
            score += 2
        elif item.topic == "policy_pressure":
            score += 1
        return score

    def _freshness_score(self, item) -> int:
        return 1 if item.freshness_ts is not None else 0

    def _build_budget(
        self,
        *,
        max_prompt_tokens: int | None,
        reserved_output_tokens: int,
        working_set_token_estimate: int,
        per_evidence_token_estimate: int,
        requested_limit: int,
        available_candidates: int,
    ) -> dict:
        if max_prompt_tokens is None:
            selected_limit = min(requested_limit, available_candidates)
            return {
                "mode": "count_only",
                "max_prompt_tokens": None,
                "reserved_output_tokens": reserved_output_tokens,
                "working_set_token_estimate": working_set_token_estimate,
                "per_evidence_token_estimate": per_evidence_token_estimate,
                "available_input_tokens": None,
                "selected_limit": selected_limit,
                "truncated_by_budget": False,
            }

        available_input_tokens = max(max_prompt_tokens - reserved_output_tokens - working_set_token_estimate, 0)
        budget_limit = available_input_tokens // per_evidence_token_estimate if per_evidence_token_estimate > 0 else 0
        selected_limit = min(requested_limit, available_candidates, budget_limit)
        return {
            "mode": "token_aware",
            "max_prompt_tokens": max_prompt_tokens,
            "reserved_output_tokens": reserved_output_tokens,
            "working_set_token_estimate": working_set_token_estimate,
            "per_evidence_token_estimate": per_evidence_token_estimate,
            "available_input_tokens": available_input_tokens,
            "selected_limit": selected_limit,
            "truncated_by_budget": selected_limit < min(requested_limit, available_candidates),
        }

    def _build_prompt_sections(self, *, working_set: dict, selected_evidence: list[dict]) -> dict:
        working_lines = [
            f"goal: {working_set.get('current_goal', '')}",
            f"stage: {working_set.get('current_stage', '')}",
        ]
        evidence_lines = [
            f"- [{item['source_type']}/{item['topic']}] {item['summary']} (scope={item['scope_key']}, rank={item['rank_score']})"
            for item in selected_evidence
        ]
        return {
            "system_context": "Use working set plus promoted/indexed evidence; avoid replaying raw history unless evidence is insufficient.",
            "working_set_summary": "\n".join(working_lines),
            "evidence_digest": "\n".join(evidence_lines),
        }

    def _assemble_prompt(self, prompt_sections: dict) -> str:
        parts = [
            "[SYSTEM CONTEXT]",
            prompt_sections.get("system_context", ""),
            "",
            "[WORKING SET]",
            prompt_sections.get("working_set_summary", ""),
            "",
            "[EVIDENCE DIGEST]",
            prompt_sections.get("evidence_digest", ""),
        ]
        return "\n".join(parts).strip()
