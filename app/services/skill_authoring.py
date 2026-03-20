from __future__ import annotations

from dataclasses import dataclass, field

from app.models.skill_adapter import SkillAdapterSpec
from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.models.skill_manifest import SkillContractRef, SkillManifest


@dataclass(slots=True)
class SkillAuthoringSpec:
    skill_id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    runtime_adapter: str = "callable"
    adapter_entry: str = ""
    adapter_command: list[str] = field(default_factory=list)
    input_schema_ref: str = ""
    output_schema_ref: str = ""
    error_schema_ref: str = ""
    tags: list[str] = field(default_factory=list)
    immutable_interface: bool = False
    dependencies: list[str] = field(default_factory=list)
    content: str = ""
    capability_profile: SkillCapabilityProfile = field(default_factory=SkillCapabilityProfile)


class SkillAuthoringService:
    """Small helper for building consistent skill registry entries.

    This keeps normal skill authoring on the same shape as built-in system skills,
    but removes repetitive manifest/registry boilerplate from callers and tests.
    """

    def build_entry(self, spec: SkillAuthoringSpec) -> SkillRegistryEntry:
        adapter = SkillAdapterSpec(
            kind=spec.runtime_adapter,
            entry=spec.adapter_entry,
            command=list(spec.adapter_command),
        )
        manifest = SkillManifest(
            skill_id=spec.skill_id,
            name=spec.name,
            version=spec.version,
            description=spec.description,
            runtime_adapter=spec.runtime_adapter,
            adapter=adapter,
            contract=SkillContractRef(
                input_schema_ref=spec.input_schema_ref,
                output_schema_ref=spec.output_schema_ref,
                error_schema_ref=spec.error_schema_ref,
            ),
            tags=list(spec.tags),
        )
        content = spec.content or spec.description or spec.name
        return SkillRegistryEntry(
            skill_id=spec.skill_id,
            name=spec.name,
            immutable_interface=spec.immutable_interface,
            active_version=spec.version,
            versions=[SkillVersion(version=spec.version, content=content)],
            dependencies=list(spec.dependencies),
            capability_profile=spec.capability_profile,
            runtime_adapter=spec.runtime_adapter,
            manifest=manifest,
        )

    def build_callable_entry(
        self,
        *,
        skill_id: str,
        name: str,
        handler_entry: str,
        description: str = "",
        version: str = "1.0.0",
        input_schema_ref: str = "",
        output_schema_ref: str = "",
        error_schema_ref: str = "",
        tags: list[str] | None = None,
        immutable_interface: bool = False,
        dependencies: list[str] | None = None,
        content: str = "",
        capability_profile: SkillCapabilityProfile | None = None,
    ) -> SkillRegistryEntry:
        return self.build_entry(
            SkillAuthoringSpec(
                skill_id=skill_id,
                name=name,
                description=description,
                version=version,
                runtime_adapter="callable",
                adapter_entry=handler_entry,
                input_schema_ref=input_schema_ref,
                output_schema_ref=output_schema_ref,
                error_schema_ref=error_schema_ref,
                tags=list(tags or []),
                immutable_interface=immutable_interface,
                dependencies=list(dependencies or []),
                content=content,
                capability_profile=capability_profile or SkillCapabilityProfile(),
            )
        )

    def build_script_entry(
        self,
        *,
        skill_id: str,
        name: str,
        command: list[str],
        description: str = "",
        version: str = "1.0.0",
        input_schema_ref: str = "",
        output_schema_ref: str = "",
        error_schema_ref: str = "",
        tags: list[str] | None = None,
        immutable_interface: bool = False,
        dependencies: list[str] | None = None,
        content: str = "",
        capability_profile: SkillCapabilityProfile | None = None,
    ) -> SkillRegistryEntry:
        return self.build_entry(
            SkillAuthoringSpec(
                skill_id=skill_id,
                name=name,
                description=description,
                version=version,
                runtime_adapter="script",
                adapter_command=list(command),
                input_schema_ref=input_schema_ref,
                output_schema_ref=output_schema_ref,
                error_schema_ref=error_schema_ref,
                tags=list(tags or []),
                immutable_interface=immutable_interface,
                dependencies=list(dependencies or []),
                content=content,
                capability_profile=capability_profile or SkillCapabilityProfile(),
            )
        )
