"""App creation orchestrator — coordinates intent → design → confirm → create.

This is the Path B replacement for MetaAppCreationOrchestrator.
"""
from __future__ import annotations

from typing import Any

from app.models.app_design import (
    AppCreationResult,
    AppDesignResult,
    AppIntentResult,
    DesignConfirmation,
)
from app.services.app_designer.architect import AppArchitect, AppArchitectError
from app.services.app_designer.intent_analyzer import AppIntentAnalyzer, AppIntentAnalyzerError


class AppDesignOrchestratorError(ValueError):
    pass


class AppDesignOrchestrator:
    """Orchestrates the full app creation flow.

    Flow:
    1. Intent analysis (cheap model)
    2. If clarification needed → return to user
    3. Architecture design (strong model, with skill registry)
    4. Present design to user for confirmation
    5. If approved → create skills → build blueprint → install
    6. If rejected → return feedback
    """

    def __init__(
        self,
        intent_analyzer: AppIntentAnalyzer,
        architect: AppArchitect,
        skill_factory: Any = None,
        user_gateway: Any = None,
        blueprint_builder: Any = None,
        app_installer: Any = None,
    ) -> None:
        self._intent_analyzer = intent_analyzer
        self._architect = architect
        self._skill_factory = skill_factory
        self._user_gateway = user_gateway
        self._blueprint_builder = blueprint_builder
        self._app_installer = app_installer

    def analyze_intent(self, user_input: str, context: dict[str, Any] | None = None) -> AppCreationResult:
        """Step 1: Analyze user intent."""
        try:
            intent = self._intent_analyzer.analyze(user_input, context)
        except AppIntentAnalyzerError as exc:
            return AppCreationResult(
                status="failed",
                error=str(exc),
                message="意图分析失败，请换种方式描述",
            )

        if intent.needs_clarification:
            return AppCreationResult(
                status="needs_clarification",
                clarification_questions=intent.clarification_questions,
                message="需要更多信息来理解你的需求",
            )

        return AppCreationResult(
            status="approved",
            app_name=intent.app_name,
            message="意图分析完成",
        )

    def design_app(self, user_input: str, context: dict[str, Any] | None = None) -> AppCreationResult:
        """Steps 1-3: Analyze → Design (internal, no user confirmation)."""
        # Step 1: Intent
        try:
            intent = self._intent_analyzer.analyze(user_input, context)
        except AppIntentAnalyzerError as exc:
            return AppCreationResult(
                status="failed",
                error=str(exc),
                message="意图分析失败",
            )

        if intent.needs_clarification:
            return AppCreationResult(
                status="needs_clarification",
                clarification_questions=intent.clarification_questions,
            )

        # Step 2: Architecture design
        try:
            design = self._architect.design(intent)
        except AppArchitectError as exc:
            return AppCreationResult(
                status="failed",
                app_name=intent.app_name,
                error=str(exc),
                message="架构设计失败",
            )

        return AppCreationResult(
            status="needs_confirmation",
            app_name=design.app_name,
            design=design,
            message="设计方案已生成，请确认",
        )

    def confirm_and_create(
        self,
        design: AppDesignResult,
        confirmation: DesignConfirmation,
    ) -> AppCreationResult:
        """Steps 4-6: Confirm → Create skills → Build blueprint."""
        if not confirmation.approved:
            return AppCreationResult(
                status="rejected_by_user",
                app_name=design.app_name,
                message=f"设计被拒绝: {confirmation.feedback}",
            )

        # Step 5: Create skills (reuse existing + create new)
        created_skill_ids: list[str] = []

        if self._skill_factory:
            # Reuse existing skills
            created_skill_ids.extend(design.reused_skills)

            # Create new skills
            for skill_design in design.subordinate_skills:
                if skill_design.reuse_existing:
                    continue  # Already counted in reused

                skill_id = skill_design.suggested_name
                try:
                    # Check if skill already exists
                    self._skill_factory._skill_control.get_skill(skill_id)
                    created_skill_ids.append(skill_id)
                    continue
                except Exception:
                    pass  # Skill doesn't exist, create it

                # Create skill stub
                created_skill_ids.extend(
                    self._create_skill_stub(skill_design, design.app_slug)
                )

        blueprint_id = None
        install_status = None
        if self._blueprint_builder is not None:
            try:
                blueprint = self._blueprint_builder.build_blueprint_from_design(
                    design,
                    created_skill_ids=created_skill_ids,
                )
                blueprint_id = getattr(blueprint, "id", None)
                if blueprint_id and self._app_installer is not None:
                    install_result = self._app_installer.install_app(blueprint_id, user_id="system")
                    install_status = getattr(install_result, "install_status", None)
            except Exception:
                pass

        message = f"✅ App '{design.app_name}' 创建成功！共 {len(created_skill_ids)} 个 skill"
        if blueprint_id:
            message += f"，blueprint={blueprint_id}"
        if install_status:
            message += f"，install={install_status}"

        return AppCreationResult(
            status="success",
            app_name=design.app_name,
            design=design,
            created_skill_ids=created_skill_ids,
            message=message,
        )

    def _create_skill_stub(self, skill_design, app_slug: str) -> list[str]:
        """Create a skill stub for a new subordinate skill."""
        if not self._skill_factory:
            return []

        from app.models.skill_creation import SkillCreationRequest, SkillSchemaDefinition

        skill_id = skill_design.suggested_name
        handler_code = (
            f'"""Auto-generated skill stub: {skill_id}\n'
            f"App: {app_slug}\n"
            f"Purpose: {skill_design.responsibility}\n"
            f"Scope: {skill_design.scope}\n"
            'This is a placeholder — refine the handler for production use.\n'
            '"""\n\n'
            f"def handle(request: dict) -> dict:\n"
            f'    text = request.get("text", "")\n'
            f'    return {{"skill_id": "{skill_id}", "result": f"Processed: {{text}}", "status": "stub"}}\n'
        )

        import os
        skills_dir = f"skills/generated/{skill_id}"
        os.makedirs(skills_dir, exist_ok=True)
        handler_path = f"{skills_dir}/handler.py"
        with open(handler_path, "w") as f:
            f.write(handler_code)

        creation_request = SkillCreationRequest(
            skill_id=skill_id,
            name=skill_design.responsibility,
            description=f"Subordinate skill for {app_slug}: {skill_design.responsibility}",
            adapter_kind="script",
            handler_entry=handler_path,
            tags=[app_slug, skill_design.priority, "generated-by-designer"],
            schemas=SkillSchemaDefinition(
                input={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
                output={"type": "object", "properties": {"result": {"type": "string"}, "skill_id": {"type": "string"}}},
                error={"type": "object", "properties": {"message": {"type": "string"}}},
            ),
        )

        try:
            self._skill_factory.create_skill(creation_request)
            return [skill_id]
        except Exception as exc:
            return []
