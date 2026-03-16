from __future__ import annotations

from app.models.event_bus import EventRecord
from app.models.experience import ExperienceRecord
from app.models.practice_review import PracticeReviewRequest, PracticeReviewResult
from app.services.app_data_store import AppDataStore
from app.services.event_bus import EventBusService
from app.services.experience_store import ExperienceStore


class PracticeReviewError(ValueError):
    pass


class PracticeReviewService:
    def __init__(
        self,
        event_bus: EventBusService,
        data_store: AppDataStore,
        experience_store: ExperienceStore,
    ) -> None:
        self._event_bus = event_bus
        self._data_store = data_store
        self._experience_store = experience_store

    def review(self, request: PracticeReviewRequest) -> PracticeReviewResult:
        namespaces = self._data_store.list_namespaces(request.app_instance_id)
        if not namespaces:
            raise PracticeReviewError(f"No namespaces found for app instance: {request.app_instance_id}")

        events = [
            event
            for event in self._event_bus.list_events()
            if event.app_instance_id == request.app_instance_id
        ][-request.max_events :]

        records = []
        for namespace in namespaces:
            records.extend(self._data_store.list_records(namespace.namespace_id)[: request.max_records_per_namespace])

        summary = self._build_summary(request.app_instance_id, events, records)
        experience = ExperienceRecord(
            experience_id=f"exp.review.{request.app_instance_id}.{len(self._experience_store.list_experiences()) + 1}",
            title=f"Practice review for {request.app_instance_id}",
            summary=summary,
            source="runtime",
            tags=self._collect_tags(events, records),
            related_apps=[request.app_instance_id],
        )
        self._experience_store.add_experience(experience)
        return PracticeReviewResult(
            app_instance_id=request.app_instance_id,
            event_count=len(events),
            record_count=len(records),
            experience=experience,
        )

    def _build_summary(self, app_instance_id: str, events: list[EventRecord], records: list) -> str:
        event_names = [event.event_name for event in events]
        record_keys = [record.key for record in records]
        event_part = "、".join(event_names) if event_names else "无明显事件"
        record_part = "、".join(record_keys) if record_keys else "无关键数据记录"
        return (
            f"App {app_instance_id} 最近实践中出现的事件包括：{event_part}；"
            f"沉淀的数据记录包括：{record_part}；"
            "可基于这些运行事实继续提炼 skill 或 workflow 优化建议。"
        )

    def _collect_tags(self, events: list[EventRecord], records: list) -> list[str]:
        tags: list[str] = ["practice-review", "runtime"]
        for event in events:
            if event.event_name not in tags:
                tags.append(event.event_name)
        for record in records:
            for tag in record.tags:
                if tag not in tags:
                    tags.append(tag)
        return tags
