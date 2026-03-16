from __future__ import annotations

from app.models.app_instance import AppInstance
from app.models.registry import AppInstallResult
from app.services.app_registry import AppRegistryService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService


class AppInstallerError(ValueError):
    pass


class AppInstallerService:
    def __init__(
        self,
        registry: AppRegistryService,
        lifecycle: AppLifecycleService,
        runtime_host: AppRuntimeHostService,
    ) -> None:
        self._registry = registry
        self._lifecycle = lifecycle
        self._runtime_host = runtime_host

    def install_app(self, blueprint_id: str, user_id: str, app_instance_id: str | None = None) -> AppInstallResult:
        blueprint = self._registry.get_blueprint(blueprint_id)
        instance_id = app_instance_id or f"{blueprint_id}:{user_id}"

        try:
            instance = self._lifecycle.get_instance(instance_id)
            install_status = "upgraded"
        except Exception:
            instance = AppInstance(
                id=instance_id,
                blueprint_id=blueprint.id,
                owner_user_id=user_id,
                status="draft",
                installed_version=blueprint.version,
                data_namespace=f"users/{user_id}/apps/{instance_id}",
                execution_mode=blueprint.runtime_policy.execution_mode,
                runtime_policy=blueprint.runtime_policy,
            )
            self._runtime_host.register_instance(instance)
            install_status = "installed"

        if instance.status == "draft":
            self._lifecycle.transition(instance.id, "validate", reason="installer")
            self._lifecycle.transition(instance.id, "compile", reason="installer")
            self._lifecycle.transition(instance.id, "install", reason="installer")

        return AppInstallResult(
            app_instance_id=instance.id,
            blueprint_id=blueprint.id,
            install_status=install_status,
            execution_mode=instance.execution_mode,
            status=self._lifecycle.get_instance(instance.id).status,
        )
