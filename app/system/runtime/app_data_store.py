from __future__ import annotations

from pathlib import Path

from app.models.data_record import DataNamespace, DataRecord
from app.services.runtime_state_store import RuntimeStateStore


class AppDataStoreError(ValueError):
    pass


class AppDataStore:
    def __init__(self, base_dir: str = "data/namespaces", store: RuntimeStateStore | None = None) -> None:
        self.base_path = Path(base_dir)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._namespaces: dict[str, DataNamespace] = {}
        self._records: dict[str, list[DataRecord]] = {}
        self._store = store

    def ensure_app_namespaces(self, app_instance_id: str, owner_user_id: str) -> list[DataNamespace]:
        namespaces = [
            self._ensure_namespace(
                namespace_id=f"{app_instance_id}:app_data",
                app_instance_id=app_instance_id,
                owner_user_id=owner_user_id,
                namespace_type="app_data",
                path=f"{app_instance_id}/app_data",
            ),
            self._ensure_namespace(
                namespace_id=f"{app_instance_id}:runtime_state",
                app_instance_id=app_instance_id,
                owner_user_id=owner_user_id,
                namespace_type="runtime_state",
                path=f"{app_instance_id}/runtime_state",
            ),
            self._ensure_namespace(
                namespace_id=f"{app_instance_id}:system_metadata",
                app_instance_id=app_instance_id,
                owner_user_id=owner_user_id,
                namespace_type="system_metadata",
                path=f"{app_instance_id}/system_metadata",
            ),
        ]
        self._persist()
        return namespaces

    def ensure_skill_asset_namespace(self) -> DataNamespace:
        namespace = self._ensure_namespace(
            namespace_id="global:skill_assets",
            app_instance_id=None,
            owner_user_id=None,
            namespace_type="skill_assets",
            path="global/skill_assets",
        )
        self._persist()
        return namespace

    def put_record(
        self,
        namespace_id: str,
        key: str,
        value: dict,
        tags: list[str] | None = None,
    ) -> DataRecord:
        namespace = self.get_namespace(namespace_id)
        record_id = f"{namespace_id}:{key}"
        record = DataRecord(
            record_id=record_id,
            namespace_id=namespace.namespace_id,
            key=key,
            value=value,
            tags=tags or [],
        )
        bucket = self._records.setdefault(namespace_id, [])
        bucket = [item for item in bucket if item.key != key]
        bucket.append(record)
        self._records[namespace_id] = bucket
        self._persist()
        return record

    def list_records(self, namespace_id: str) -> list[DataRecord]:
        self.get_namespace(namespace_id)
        return list(self._records.get(namespace_id, []))

    def get_namespace(self, namespace_id: str) -> DataNamespace:
        if namespace_id not in self._namespaces:
            raise AppDataStoreError(f"Namespace not found: {namespace_id}")
        return self._namespaces[namespace_id]

    def list_namespaces(self, app_instance_id: str | None = None) -> list[DataNamespace]:
        namespaces = list(self._namespaces.values())
        if app_instance_id is None:
            return namespaces
        return [item for item in namespaces if item.app_instance_id == app_instance_id]

    def _ensure_namespace(
        self,
        namespace_id: str,
        app_instance_id: str | None,
        owner_user_id: str | None,
        namespace_type: str,
        path: str,
    ) -> DataNamespace:
        if namespace_id in self._namespaces:
            return self._namespaces[namespace_id]
        fs_path = self.base_path / path
        fs_path.mkdir(parents=True, exist_ok=True)
        namespace = DataNamespace(
            namespace_id=namespace_id,
            app_instance_id=app_instance_id,
            namespace_type=namespace_type,  # type: ignore[arg-type]
            owner_user_id=owner_user_id,
            path=str(fs_path),
        )
        self._namespaces[namespace_id] = namespace
        self._records.setdefault(namespace_id, [])
        return namespace

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save_mapping("data_namespaces", self._namespaces)
        self._store.save_nested_mapping("data_records", self._records)
