"""Phase R: Phase 5 (App Refinement Closure) E2E validation."""
from __future__ import annotations

import pytest

from app.orchestration.app_refinement import AppRefinementService
from app.orchestration.app_refinement_orchestrator import AppRefinementOrchestratorService
from app.services.experience_store import ExperienceStore
from app.models.experience import ExperienceRecord
from app.models.skill_blueprint import SkillBlueprint
from app.models.app_refinement import (
    SuggestedSkillRefinementRequest,
    SuggestedSkillRefinementClosureRequest,
)


def test_experience_store():
    """R-01: ExperienceStore works."""
    store = ExperienceStore()
    
    bp = SkillBlueprint(
        skill_id="test.skill.v1",
        name="Test Skill",
        goal="A test skill",
        version="0.1.0",
        adapter_kind="callable",
    )
    store.add_skill_blueprint(bp)
    
    blueprints = store.list_skill_blueprints()
    assert len(blueprints) == 1
    assert blueprints[0].skill_id == "test.skill.v1"
    
    found = store.get_skill_blueprint("test.skill.v1")
    assert found.skill_id == "test.skill.v1"


def test_app_refinement_build_from_skills():
    """R-02: AppRefinementService can build from suggested skills.
    
    This is the core Phase 5 flow:
    suggested skill blueprints → assembled app blueprint
    """
    store = ExperienceStore()
    
    # Add a skill blueprint
    bp = SkillBlueprint(
        skill_id="refine.skill.v1",
        name="Refine Skill",
        goal="A skill for refinement",
        version="0.1.0",
        adapter_kind="callable",
    )
    store.add_skill_blueprint(bp)
    
    # Mock dependencies
    class MockSkillControl:
        def get_skill(self, skill_id):
            # Return mock to mark as reusable
            return type('obj', (object,), {'skill_id': skill_id})()
    
    class MockSkillFactory:
        def choose_adapter_kind_for_blueprint(self, blueprint, preferred):
            return "callable", {}, "default"
        def build_creation_request_from_blueprint(self, blueprint, **kwargs):
            return type('obj', (object,), {'skill_id': blueprint.skill_id})()
        def create_skill(self, request):
            return type('obj', (object,), {'skill_id': request.skill_id})()
        def build_blueprint_from_skills(self, request):
            from app.models.app_blueprint import AppBlueprint
            bp = AppBlueprint(
                id=request.blueprint_id,
                name=request.blueprint_id,
                goal="Refined app",
                description="Refined app",
                version="0.1.0",
                required_skills=set(request.skill_ids),
                app_shape="generic",
                workflows=[],
                views=[],
            )
            from app.models.skill_creation import AppFromSkillsResult
            app_result = AppFromSkillsResult(
                blueprint_id=request.blueprint_id,
                workflow_id='default',
            )
            return bp, app_result
    
    refinement = AppRefinementService(
        experience_store=store,
        skill_control=MockSkillControl(),
        skill_factory=MockSkillFactory(),
    )
    
    request = SuggestedSkillRefinementRequest(
        skill_ids=["refine.skill.v1"],
        blueprint_id="test.refine.app",
        name="Test Refine App",
    )
    
    result = refinement.build_app_from_suggested_skills(request)
    assert result is not None
    assert result.blueprint is not None
    assert result.blueprint.id == "test.refine.app"
    assert len(result.reused_skill_ids) >= 1


def test_refinement_orchestrator_class_exists():
    """R-03: AppRefinementOrchestratorService class is available."""
    assert AppRefinementOrchestratorService is not None
    assert hasattr(AppRefinementOrchestratorService, 'refine_closure')


def test_refinement_services_complete():
    """R-04: All Phase 5 services are available."""
    assert AppRefinementService is not None
    assert AppRefinementOrchestratorService is not None
    assert ExperienceStore is not None
    assert SkillBlueprint is not None
    assert SuggestedSkillRefinementRequest is not None
    assert SuggestedSkillRefinementClosureRequest is not None


def test_experience_store_suggest_skills():
    """R-05: ExperienceStore can suggest skills for an experience."""
    store = ExperienceStore()
    
    # Add experience
    exp = ExperienceRecord(experience_id="exp.test.v1", summary="Test experience", title="Test", source="runtime")
    store.add_experience(exp)
    
    # Add skill blueprint linked to experience
    bp = SkillBlueprint(
        skill_id="suggested.skill.v1",
        name="Suggested Skill",
        goal="A suggested skill",
        version="0.1.0",
        adapter_kind="callable",
        related_experience_ids=["exp.test.v1"],
    )
    store.add_skill_blueprint(bp)
    
    suggested = store.suggest_skills_for_experience("exp.test.v1")
    assert len(suggested) == 1
    assert suggested[0].skill_id == "suggested.skill.v1"
