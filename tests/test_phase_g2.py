"""Tests for Phase G.2: skill meta, identity tracing, log center."""
from __future__ import annotations

import pytest

from app.models.request_context import RequestContext
from app.models.skill_meta import SkillMetaInfo, ActionMeta
from app.models.log_center import SkillLogEntry, LogCollectionConfig, LogQuery, LOG_LEVEL_ORDER
from app.models.app_binding import AppInstanceBinding, SkillBindingConfig
from app.services.log_center import LogCenter
from app.services.skill_meta_service import SkillMetaService


# -- RequestContext -----------------------------------------------------------

def test_new_root_context():
    ctx = RequestContext.new_root(user_id="alice", app_instance_id="app-001")
    assert ctx.trace_id.startswith("t-")
    assert ctx.user_id == "alice"
    assert ctx.app_instance_id == "app-001"
    assert ctx.caller_id == "user"
    assert ctx.parent_trace_id is None


def test_child_context_shares_trace():
    parent = RequestContext.new_root(user_id="alice", app_instance_id="app-001")
    child = parent.child(caller_id="skill.maoxuan")

    assert child.trace_id == parent.trace_id
    assert child.request_id != parent.request_id
    assert child.parent_trace_id == parent.request_id
    assert child.caller_id == "skill.maoxuan"


def test_context_inject_extract():
    ctx = RequestContext.new_root(user_id="bob", app_instance_id="app-002")
    config = ctx.inject_into_config({})

    assert config["__trace_id__"] == ctx.trace_id
    assert config["__user_id__"] == "bob"

    restored = RequestContext.from_config(config)
    assert restored is not None
    assert restored.trace_id == ctx.trace_id


# -- Log Center ---------------------------------------------------------------

def test_log_entry_creation():
    entry = SkillLogEntry(
        trace_id="t-001",
        skill_id="skill.maoxuan",
        action="analyze",
        app_instance_id="app-001",
        user_id="alice",
        level="INFO",
        message="Analysis completed",
        duration_ms=3200,
    )
    assert "INFO" in entry.to_display()
    assert "skill.maoxuan" in entry.to_display()


def test_log_center_filtering():
    lc = LogCenter()
    lc.set_app_config("app-001", LogCollectionConfig(level="INFO", record_inputs=False))

    # INFO entry — should be recorded
    lc.log("t-001", "skill.a", "execute", "app-001", "alice",
           "INFO", "step completed")

    # DEBUG entry — should be filtered out (below INFO)
    result = lc.log("t-001", "skill.a", "execute", "app-001", "alice",
                    "DEBUG", "debug info")
    assert result is None

    # ERROR entry — should be recorded
    lc.log("t-001", "skill.a", "execute", "app-001", "alice",
           "ERROR", "failed", error="connection refused")

    # Query by level
    entries = lc.query(LogQuery(trace_id="t-001"))
    assert len(entries) == 2  # INFO + ERROR

    error_entries = lc.query(LogQuery(trace_id="t-001", error_only=True))
    assert len(error_entries) == 1


def test_log_center_trace_query():
    lc = LogCenter()
    lc.log("t-001", "skill.intent", "parse", "app-001", "alice",
           "INFO", "parsed")
    lc.log("t-001", "skill.maoxuan", "analyze", "app-001", "alice",
           "INFO", "analyzed")
    lc.log("t-002", "skill.echo", "execute", "app-001", "bob",
           "INFO", "echoed")

    trace = lc.get_trace("t-001")
    assert len(trace) == 2
    assert all(e.trace_id == "t-001" for e in trace)

    summary = lc.get_trace_summary("t-001")
    assert summary["found"]
    assert summary["entry_count"] == 2
    assert "skill.intent" in summary["skills_called"]


def test_log_center_retention():
    lc = LogCenter()
    lc.set_app_config("app-001", LogCollectionConfig(
        level="INFO",
        retention_hours=1,
        max_entries=5,
    ))

    for i in range(10):
        lc.log(f"t-{i:03d}", "skill.a", "execute", "app-001", "alice",
               "INFO", f"entry {i}")

    stats = lc.stats()
    assert stats["total_entries"] <= 100_000  # global max


# -- Skill Meta Service -------------------------------------------------------

def test_meta_registration():
    ms = SkillMetaService()
    ms.register_simple(
        skill_id="skill.analyzer",
        name="Data Analyzer",
        description="Analyzes data",
        input_schema={"required": ["data"]},
        output_schema={"properties": {"result": {"type": "string"}}},
        actions={"analyze": {"description": "Run analysis"}},
    )

    meta = ms.get("skill.analyzer")
    assert meta is not None
    assert meta.name == "Data Analyzer"
    assert "analyze" in meta.actions


def test_meta_search():
    ms = SkillMetaService()
    ms.register_simple(skill_id="skill.maoxuan", name="毛选分析", description="用毛泽东思想分析")
    ms.register_simple(skill_id="skill.data", name="数据分析", description="数据分析工具")

    results = ms.search("分析")
    assert len(results) == 2

    results = ms.search("毛选")
    assert len(results) == 1
    assert results[0].skill_id == "skill.maoxuan"


def test_meta_composition_validation():
    ms = SkillMetaService()
    ms.register_simple(skill_id="skill.a", name="A", dependencies=["skill.b"])
    ms.register_simple(skill_id="skill.b", name="B")
    ms.register_simple(skill_id="skill.c", name="C", dependencies=["skill.d"])

    # Valid: a + b (b is registered)
    report = ms.validate_composition(["skill.a", "skill.b"])
    assert report["valid"]

    # Invalid: c needs d, d not registered
    report = ms.validate_composition(["skill.c"])
    assert not report["valid"]
    assert "Missing dependency" in report["issues"][0]


def test_meta_compatibility_check():
    ms = SkillMetaService()
    ms.register_simple(
        skill_id="skill.fetcher",
        name="Data Fetcher",
        output_schema={"properties": {"data": {"type": "string"}}},
    )
    ms.register_simple(
        skill_id="skill.analyzer",
        name="Data Analyzer",
        input_schema={"required": ["data"]},
    )

    report = ms.get_compatibility_report("skill.fetcher", "skill.analyzer")
    assert report["compatible"]  # fetcher outputs "data", analyzer requires "data"


# -- App Binding --------------------------------------------------------------

def test_app_binding():
    binding = AppInstanceBinding(
        app_instance_id="app-001",
        log_config=LogCollectionConfig(level="DEBUG"),
    )
    binding.bind_skill("skill.maoxuan")
    binding.bind_skill("skill.data", SkillBindingConfig(
        skill_id="skill.data",
        enabled=True,
        log_level="WARNING",
    ))

    assert binding.is_bound("skill.maoxuan")
    assert binding.get_log_level("skill.maoxuan") == "DEBUG"  # global default
    assert binding.get_log_level("skill.data") == "WARNING"  # override

    assert "skill.maoxuan" in binding.get_bound_skills()

    binding.unbind_skill("skill.maoxuan")
    assert not binding.is_bound("skill.maoxuan")
