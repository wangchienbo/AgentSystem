from __future__ import annotations

from app.models.app_context import AppSharedContext
from app.models.event_bus import EventRecord
from app.models.experience import ExperienceRecord
from app.models.practice_review import PracticeReviewRequest, PracticeReviewResult
from app.services.app_context_store import AppContextStore, AppContextStoreError
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
        context_store: AppContextStore | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._data_store = data_store
        self._experience_store = experience_store
        self._context_store = context_store

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

        context = self._get_context(request.app_instance_id)
        summary = self._build_summary(request.app_instance_id, events, records, context)
        experience = ExperienceRecord(
            experience_id=f"exp.review.{request.app_instance_id}.{len(self._experience_store.list_experiences()) + 1}",
            title=f"Practice review for {request.app_instance_id}",
            summary=summary,
            source="runtime",
            tags=self._collect_tags(events, records, context),
            related_apps=[request.app_instance_id],
        )
        self._experience_store.add_experience(experience)
        return PracticeReviewResult(
            app_instance_id=request.app_instance_id,
            event_count=len(events),
            record_count=len(records),
            context_entry_count=0 if context is None else len(context.entries),
            experience=experience,
        )

    def _get_context(self, app_instance_id: str) -> AppSharedContext | None:
        if self._context_store is None:
            return None
        try:
            return self._context_store.get_context(app_instance_id)
        except AppContextStoreError:
            return None

    def _build_summary(
        self,
        app_instance_id: str,
        events: list[EventRecord],
        records: list,
        context: AppSharedContext | None,
    ) -> str:
        event_names = [event.event_name for event in events]
        record_keys = [record.key for record in records]
        event_part = "、".join(event_names) if event_names else "无明显事件"
        record_part = "、".join(record_keys) if record_keys else "无关键数据记录"
        context_part = self._build_context_summary(context)
        return (
            f"App {app_instance_id} 最近实践中出现的事件包括：{event_part}；"
            f"沉淀的数据记录包括：{record_part}；"
            f"共享上下文显示：{context_part}；"
            "可基于这些运行事实继续提炼 skill 或 workflow 优化建议。"
        )

    def _build_context_summary(self, context: AppSharedContext | None) -> str:
        if context is None:
            return "暂无共享上下文"
        sections = []
        if context.current_goal:
            sections.append(f"当前目标是 {context.current_goal}")
        if context.current_stage:
            sections.append(f"当前阶段是 {context.current_stage}")
        if context.entries:
            latest_entries = context.entries[-3:]
            latest_keys = "、".join(f"{item.section}:{item.key}" for item in latest_entries)
            sections.append(f"最近上下文条目包括 {latest_keys}")
        return "；".join(sections) if sections else "上下文存在但尚未记录重点"

    def _collect_tags(self, events: list[EventRecord], records: list, context: AppSharedContext | None) -> list[str]:
        tags: list[str] = ["practice-review", "runtime"]
        for event in events:
            if event.event_name not in tags:
                tags.append(event.event_name)
        for record in records:
            for tag in record.tags:
                if tag not in tags:
                    tags.append(tag)
        if context is not None:
            if "shared-context" not in tags:
                tags.append("shared-context")
            for entry in context.entries[-5:]:
                if entry.section not in tags:
                    tags.append(entry.section)
                for tag in entry.tags:
                    if tag not in tags:
                        tags.append(tag)
        return tags
