from __future__ import annotations

from app.models.app_instance import AppInstance
from app.models.registry import AppInstallResult
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_registry import AppRegistryService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.app_config_service import AppConfigService
from app.services.app_profile_resolver import AppProfileResolverService
from app.services.blueprint_validation import BlueprintValidationError, BlueprintValidationService


class AppInstallerError(ValueError):
    pass


DEFAULT_SYSTEM_SKILLS = [
    "system.app_config",
    "system.context",
    "system.state",
    "system.audit",
]


class AppInstallerService:
    def __init__(
        self,
        registry: AppRegistryService,
        lifecycle: AppLifecycleService,
        runtime_host: AppRuntimeHostService,
        data_store: AppDataStore,
        context_store: AppContextStore | None = None,
        app_config_service: AppConfigService | None = None,
        app_profile_resolver: AppProfileResolverService | None = None,
        blueprint_validation: BlueprintValidationService | None = None,
    ) -> None:
        self._registry = registry
        self._lifecycle = lifecycle
        self._runtime_host = runtime_host
        self._data_store = data_store
        self._context_store = context_store
        self._app_config_service = app_config_service
        self._app_profile_resolver = app_profile_resolver
        self._blueprint_validation = blueprint_validation

    def install_app(self, blueprint_id: str, user_id: str, app_instance_id: str | None = None) -> AppInstallResult:
        blueprint = self._registry.get_blueprint(blueprint_id)
        if self._blueprint_validation is not None:
            try:
                self._blueprint_validation.require_valid(blueprint)
            except BlueprintValidationError as error:
                raise AppInstallerError(str(error)) from error
        instance_id = app_instance_id or f"{blueprint_id}:{user_id}"

        try:
            instance = self._lifecycle.get_instance(instance_id)
            install_status = "upgraded"
        except Exception:
            resolved_skills = list(dict.fromkeys([*DEFAULT_SYSTEM_SKILLS, *blueprint.required_skills]))
            runtime_profile = self._app_profile_resolver.resolve(resolved_skills) if self._app_profile_resolver is not None else None
            instance = AppInstance(
                id=instance_id,
                blueprint_id=blueprint.id,
                owner_user_id=user_id,
                status="draft",
                installed_version=blueprint.version,
                data_namespace=f"users/{user_id}/apps/{instance_id}",
                execution_mode=blueprint.runtime_policy.execution_mode,
                runtime_policy=blueprint.runtime_policy,
                system_skills=list(DEFAULT_SYSTEM_SKILLS),
                resolved_skills=resolved_skills,
                runtime_profile=runtime_profile.model_dump() if runtime_profile is not None else {},
            )
            self._runtime_host.register_instance(instance)
            install_status = "installed"

        if instance.status == "draft":
            self._lifecycle.transition(instance.id, "validate", reason="installer")
            self._lifecycle.transition(instance.id, "compile", reason="installer")
            self._lifecycle.transition(instance.id, "install", reason="installer")

        self._data_store.ensure_app_namespaces(instance.id, instance.owner_user_id)
        if self._app_config_service is not None:
            self._app_config_service.ensure_initialized(
                instance.id,
                defaults={
                    "app": {"id": instance.id, "blueprint_id": blueprint.id},
                    "runtime": {
                        "execution_mode": instance.execution_mode,
                        "runtime_profile": instance.runtime_profile.model_dump(mode="json"),
                    },
                },
            )
        if self._context_store is not None:
            context = self._context_store.ensure_context(instance.id)
            context.current_stage = self._lifecycle.get_instance(instance.id).status
            if install_status == "installed" and not context.current_goal:
                context.current_goal = blueprint.goal
            self._context_store.update_context(
                instance.id,
                current_goal=context.current_goal,
                current_stage=context.current_stage,
                status="active",
            )

        return AppInstallResult(
            app_instance_id=instance.id,
            blueprint_id=blueprint.id,
            install_status=install_status,
            execution_mode=instance.execution_mode,
            status=self._lifecycle.get_instance(instance.id).status,
        )
