"""Tests for config center — skill template + app binding model preference management."""

import json
import tempfile
from pathlib import Path

import pytest

from app.services.config_center import (
    AppSkillBinding,
    ConfigCenterService,
    SkillTemplateConfig,
)
from app.services.model_router import DEFAULT_MODEL_POOL, ModelRouter
from app.models.skill_control import (
    SkillCapabilityProfile,
    SkillManifest,
    SkillRegistryEntry,
)
from app.services.skill_control import SkillControlService


class TestSkillTemplateConfig:
    """Test skill template default configuration."""

    def test_set_and_get(self):
        cc = ConfigCenterService(data_dir=tempfile.mkdtemp())
        cc.set_skill_config("novel-writer", model_preference="balanced", description="小说写作")
        cfg = cc.get_skill_config("novel-writer")
        assert cfg is not None
        assert cfg.skill_id == "novel-writer"
        assert cfg.model_preference == "balanced"

    def test_update(self):
        cc = ConfigCenterService(data_dir=tempfile.mkdtemp())
        cc.set_skill_config("novel-writer", model_preference="balanced")
        cc.set_skill_config("novel-writer", model_preference="cheap")
        assert cc.get_skill_config("novel-writer").model_preference == "cheap"

    def test_delete(self):
        cc = ConfigCenterService(data_dir=tempfile.mkdtemp())
        cc.set_skill_config("novel-writer", model_preference="balanced")
        assert cc.delete_skill_config("novel-writer") is True
        assert cc.get_skill_config("novel-writer") is None

    def test_list_all(self):
        cc = ConfigCenterService(data_dir=tempfile.mkdtemp())
        cc.set_skill_config("skill-a", "cheap")
        cc.set_skill_config("skill-b", "strong")
        assert len(cc.list_skill_configs()) == 2


class TestAppSkillBinding:
    """Test app-level skill binding overrides."""

    def test_set_and_get(self):
        cc = ConfigCenterService(data_dir=tempfile.mkdtemp())
        cc.set_app_skill_binding("app.novel", "novel-writer", model_preference="strong")
        binding = cc.get_app_skill_binding("app.novel", "novel-writer")
        assert binding is not None
        assert binding.model_preference == "strong"

    def test_override_template_default(self):
        cc = ConfigCenterService(data_dir=tempfile.mkdtemp())
        cc.set_skill_config("novel-writer", "cheap")  # template default
        cc.set_app_skill_binding("app.novel", "novel-writer", "strong")  # app override
        resolved = cc.resolve_model_preference("app.novel", "novel-writer")
        assert resolved == "strong"  # app binding wins

    def test_fallback_to_template(self):
        cc = ConfigCenterService(data_dir=tempfile.mkdtemp())
        cc.set_skill_config("novel-writer", "balanced")
        resolved = cc.resolve_model_preference("app.novel", "novel-writer")
        assert resolved == "balanced"  # no app binding, use template

    def test_get_all_app_bindings(self):
        cc = ConfigCenterService(data_dir=tempfile.mkdtemp())
        cc.set_app_skill_binding("app.novel", "novel-writer", "strong")
        cc.set_app_skill_binding("app.novel", "summarizer", "cheap")
        cc.set_app_skill_binding("app.music", "novel-writer", "balanced")
        bindings = cc.get_app_bindings("app.novel")
        assert len(bindings) == 2

    def test_delete_binding(self):
        cc = ConfigCenterService(data_dir=tempfile.mkdtemp())
        cc.set_app_skill_binding("app.novel", "novel-writer", "strong")
        assert cc.delete_app_skill_binding("app.novel", "novel-writer") is True
        assert cc.get_app_skill_binding("app.novel", "novel-writer") is None

    def test_disabled_binding_ignored(self):
        cc = ConfigCenterService(data_dir=tempfile.mkdtemp())
        cc.set_app_skill_binding("app.novel", "novel-writer", "strong", enabled=False)
        resolved = cc.resolve_model_preference("app.novel", "novel-writer")
        assert resolved is None  # disabled, falls through


class TestResolutionPriority:
    """Test full priority chain: app binding > skill template > None."""

    def test_app_binding_wins(self):
        cc = ConfigCenterService(data_dir=tempfile.mkdtemp())
        cc.set_skill_config("writer", "cheap")
        cc.set_app_skill_binding("app.a", "writer", "strong")
        assert cc.resolve_model_preference("app.a", "writer") == "strong"

    def test_template_default_when_no_binding(self):
        cc = ConfigCenterService(data_dir=tempfile.mkdtemp())
        cc.set_skill_config("writer", "balanced")
        assert cc.resolve_model_preference("app.a", "writer") == "balanced"

    def test_none_when_nothing_configured(self):
        cc = ConfigCenterService(data_dir=tempfile.mkdtemp())
        assert cc.resolve_model_preference("app.a", "writer") is None

    def test_multi_app_isolation(self):
        cc = ConfigCenterService(data_dir=tempfile.mkdtemp())
        cc.set_skill_config("writer", "balanced")  # template default
        cc.set_app_skill_binding("app.alice", "writer", "strong")
        cc.set_app_skill_binding("app.bob", "writer", "cheap")
        assert cc.resolve_model_preference("app.alice", "writer") == "strong"
        assert cc.resolve_model_preference("app.bob", "writer") == "cheap"
        # Without app binding, falls to template
        assert cc.resolve_model_preference("app.charlie", "writer") == "balanced"


class TestModelRouterWithConfigCenter:
    """Test ModelRouter integrates with ConfigCenter."""

    def test_config_center_override(self):
        cc = ConfigCenterService(data_dir=tempfile.mkdtemp())
        cc.set_skill_config("novel-writer", "cheap")

        ctrl = SkillControlService()
        router = ModelRouter(skill_control=ctrl, config_center=cc)

        # ConfigCenter: skill template = cheap
        route = router.resolve("skill:novel-writer")
        assert route.model_name == "gpt-4o-mini"  # cheap
        assert "config_center" in route.source

    def test_app_skill_binding_in_router(self):
        cc = ConfigCenterService(data_dir=tempfile.mkdtemp())
        cc.set_skill_config("writer", "cheap")
        cc.set_app_skill_binding("app.novel", "writer", "strong")

        router = ModelRouter(config_center=cc)

        # App-level binding: skill instance with app context
        route = router.resolve("skill:writer:app:app.novel")
        assert route.model_name == "gpt-5.4"  # strong

    def test_fallback_to_skill_preference(self):
        cc = ConfigCenterService(data_dir=tempfile.mkdtemp())
        # No config center entry

        ctrl = SkillControlService()
        manifest = SkillManifest(
            skill_id="writer",
            name="Writer",
            version="1.0.0",
            description="Writing skill",
            handler_entry="test.handler",
            tags=["test"],
        )
        profile = SkillCapabilityProfile(
            intelligence_level="L2_semantic",
            model_preference="balanced",  # skill-declared
        )
        entry = SkillRegistryEntry(
            skill_id="writer",
            name="Writer",
            active_version="1.0.0",
            capability_profile=profile,
            manifest=manifest,
            versions=[],
        )
        ctrl.register(entry)

        router = ModelRouter(skill_control=ctrl, config_center=cc)
        route = router.resolve("skill:writer")
        assert route.model_name == "gpt-4.1"  # balanced
        assert "skill:writer" in route.source


class TestPersistence:
    """Test config center persistence."""

    def test_save_and_load(self):
        data_dir = tempfile.mkdtemp()
        cc = ConfigCenterService(data_dir=data_dir)
        cc.set_skill_config("writer", "cheap")
        cc.set_app_skill_binding("app.novel", "writer", "strong")

        # Load fresh instance
        cc2 = ConfigCenterService(data_dir=data_dir)
        assert cc2.get_skill_config("writer").model_preference == "cheap"
        assert cc2.get_app_skill_binding("app.novel", "writer").model_preference == "strong"

    def test_empty_file_graceful(self):
        data_dir = tempfile.mkdtemp()
        # No file exists
        cc = ConfigCenterService(data_dir=data_dir)
        assert len(cc.list_skill_configs()) == 0

    def test_corrupted_file_graceful(self):
        data_dir = tempfile.mkdtemp()
        path = Path(data_dir) / "config_center.json"
        path.write_text("{broken json", encoding="utf-8")
        cc = ConfigCenterService(data_dir=data_dir)
        assert len(cc.list_skill_configs()) == 0  # graceful fallback
