from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_list_skills_exposes_builtin_origin() -> None:
    response = client.get("/skills")
    assert response.status_code == 200
    system_app_config = next(item for item in response.json() if item["skill_id"] == "system.app_config")
    assert system_app_config["origin"] == "builtin"


def test_create_script_skill_via_api_and_smoke_execute() -> None:
    response = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.script.generated",
            "name": "Generated Script Skill",
            "description": "generated through api",
            "adapter_kind": "script",
            "command": ["python3", "tests/fixtures/script_echo_skill.py"],
            "tags": ["generated", "script"],
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "echo": {"type": "string"},
                        "adapter": {"type": "string"},
                    },
                    "required": ["echo", "adapter"],
                    "additionalProperties": True,
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
            },
            "smoke_test_inputs": {"text": "hello-generated"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["skill_id"] == "skill.script.generated"
    assert payload["runtime_adapter"] == "script"
    assert payload["smoke_test"]["status"] == "completed"
    assert payload["smoke_test"]["output"]["echo"] == "hello-generated"

    list_response = client.get("/skills")
    assert list_response.status_code == 200
    listed = next(item for item in list_response.json() if item["skill_id"] == "skill.script.generated")
    assert listed["origin"] == "generated"

    detail_response = client.get("/skills/skill.script.generated")
    assert detail_response.status_code == 200
    assert detail_response.json()["origin"] == "generated"


def test_create_app_blueprint_from_generated_skills_via_api() -> None:
    create_skill = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.script.for.app",
            "name": "Generated Script App Skill",
            "description": "used by generated app blueprint",
            "adapter_kind": "script",
            "command": ["python3", "tests/fixtures/script_echo_skill.py"],
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "echo": {"type": "string"},
                        "adapter": {"type": "string"},
                    },
                    "required": ["echo", "adapter"],
                    "additionalProperties": True,
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
            },
            "smoke_test_inputs": {"text": "app-skill"},
        },
    )
    assert create_skill.status_code == 200

    response = client.post(
        "/apps/from-skills",
        json={
            "blueprint_id": "bp.generated.skill.app",
            "name": "Generated Skill App",
            "goal": "assemble an app from generated skills",
            "skill_ids": ["skill.script.for.app"],
            "workflow_id": "wf.generated.skill.app",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["blueprint"]["id"] == "bp.generated.skill.app"
    assert payload["blueprint"]["runtime_policy"]["execution_mode"] == "service"
    assert payload["blueprint"]["tasks"][0]["id"] == "task.run_generated_workflow"
    assert {view["id"] for view in payload["blueprint"]["views"]} == {"generated.overview", "generated.run", "generated.activity"}
    assert payload["result"]["required_skills"] == ["skill.script.for.app"]
    assert payload["result"]["created_steps"] == ["skill.1"]

    blueprints = client.get("/registry/apps")
    assert blueprints.status_code == 200
    assert any(item["blueprint_id"] == "bp.generated.skill.app" for item in blueprints.json())


def test_create_install_and_run_app_from_generated_skills_via_api() -> None:
    create_skill = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.script.install.run",
            "name": "Generated Install Run Skill",
            "description": "used by install-run flow",
            "adapter_kind": "script",
            "command": ["python3", "tests/fixtures/script_echo_skill.py"],
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "echo": {"type": "string"},
                        "adapter": {"type": "string"},
                    },
                    "required": ["echo", "adapter"],
                    "additionalProperties": True,
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
            },
            "smoke_test_inputs": {"text": "run-skill"},
        },
    )
    assert create_skill.status_code == 200

    response = client.post(
        "/apps/from-skills/install-run",
        json={
            "blueprint_id": "bp.generated.install.run",
            "name": "Generated Install Run App",
            "goal": "install and execute generated skill app",
            "skill_ids": ["skill.script.install.run"],
            "workflow_id": "wf.generated.install.run",
            "user_id": "generated-user",
            "step_inputs": {
                "skill.1": {"text": "installed-run"}
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["install"]["blueprint_id"] == "bp.generated.install.run"
    assert payload["execution"]["status"] == "completed"
    assert payload["execution"]["steps"][0]["status"] == "completed"
    assert payload["execution"]["steps"][0]["output"]["adapter"] == "script"


def test_create_multi_step_generated_app_with_step_mappings() -> None:
    create_slugify = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.text.slugify.chain",
            "name": "Text Slugify Chain Skill",
            "description": "normalize human titles into stable slugs",
            "adapter_kind": "script",
            "command": ["python3", "tests/fixtures/script_slugify_skill.py"],
            "tags": ["text", "normalization", "real-skill"],
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "source_text": {"type": "string"},
                        "slug": {"type": "string"},
                        "length": {"type": "integer"},
                        "adapter": {"type": "string"},
                    },
                    "required": ["source_text", "slug", "length", "adapter"],
                    "additionalProperties": True,
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
            },
            "smoke_test_inputs": {"text": "Hello, Agent System 2026!"},
        },
    )
    assert create_slugify.status_code == 200

    create_normalize = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.object.normalize_keys.chain",
            "name": "Normalize Object Keys Chain Skill",
            "description": "normalize object keys into stable keys",
            "adapter_kind": "callable",
            "generation_operation": "normalize_object_keys",
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {"payload": {"type": "object"}},
                    "required": ["payload"],
                    "additionalProperties": False,
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "normalized": {"type": "object"},
                        "top_level_keys": {"type": "array", "items": {"type": "string"}},
                        "adapter": {"type": "string"},
                    },
                    "required": ["normalized", "top_level_keys", "adapter"],
                    "additionalProperties": True,
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
            },
            "smoke_test_inputs": {"payload": {"Display Name": "Agent System"}},
        },
    )
    assert create_normalize.status_code == 200

    response = client.post(
        "/apps/from-skills/install-run",
        json={
            "blueprint_id": "bp.generated.multi.step",
            "name": "Generated Multi Step App",
            "goal": "chain generated skills through explicit mappings",
            "skill_ids": ["skill.text.slugify.chain", "skill.object.normalize_keys.chain"],
            "workflow_id": "wf.generated.multi.step",
            "user_id": "multi-step-user",
            "step_inputs": {
                "skill.1": {"text": "A Better App OS, For Real"}
            },
            "step_mappings": {
                "skill.2": [
                    {"from_step": "skill.1", "field": "slug", "target_field": "payload.Generated Slug"},
                    {"from_inputs": "title", "target_field": "payload.Source Title"}
                ]
            },
            "workflow_inputs": {
                "title": "A Better App OS, For Real"
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["blueprint"]["runtime_policy"]["execution_mode"] == "pipeline"
    assert payload["blueprint"]["runtime_policy"]["idle_strategy"] == "suspend"
    assert len(payload["blueprint"]["tasks"]) == 1
    assert len(payload["blueprint"]["views"]) == 3
    assert payload["execution"]["status"] == "completed"
    assert payload["execution"]["steps"][0]["output"]["slug"] == "a-better-app-os-for-real"
    assert payload["execution"]["steps"][1]["output"]["normalized"]["generated_slug"] == "a-better-app-os-for-real"
    assert payload["execution"]["steps"][1]["output"]["normalized"]["source_title"] == "A Better App OS, For Real"


def test_create_multi_step_generated_app_with_transform_and_default_mapping() -> None:
    create_slugify = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.text.slugify.transform",
            "name": "Text Slugify Transform Skill",
            "adapter_kind": "script",
            "command": ["python3", "tests/fixtures/script_slugify_skill.py"],
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "source_text": {"type": "string"},
                        "slug": {"type": "string"},
                        "length": {"type": "integer"},
                        "adapter": {"type": "string"},
                    },
                    "required": ["source_text", "slug", "length", "adapter"],
                    "additionalProperties": True,
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
            },
            "smoke_test_inputs": {"text": "Hello Transform"},
        },
    )
    assert create_slugify.status_code == 200

    create_normalize = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.object.normalize_keys.transform",
            "name": "Normalize Object Keys Transform Skill",
            "adapter_kind": "callable",
            "generation_operation": "normalize_object_keys",
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {
                        "payload": {"type": "object"}
                    },
                    "required": ["payload"],
                    "additionalProperties": False,
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "normalized": {"type": "object"},
                        "top_level_keys": {"type": "array", "items": {"type": "string"}},
                        "adapter": {"type": "string"},
                    },
                    "required": ["normalized", "top_level_keys", "adapter"],
                    "additionalProperties": True,
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
            },
            "smoke_test_inputs": {"payload": {"Display Name": "Agent System", "Mode": "default", "Priority": 1}},
        },
    )
    assert create_normalize.status_code == 200

    response = client.post(
        "/apps/from-skills/install-run",
        json={
            "blueprint_id": "bp.generated.transform.default",
            "name": "Generated Transform Default App",
            "goal": "apply transform and default mappings during generated app assembly",
            "skill_ids": ["skill.text.slugify.transform", "skill.object.normalize_keys.transform"],
            "workflow_id": "wf.generated.transform.default",
            "user_id": "transform-user",
            "step_inputs": {
                "skill.1": {"text": "A Better App OS, For Real"}
            },
            "step_mappings": {
                "skill.2": [
                    {"from_step": "skill.1", "field": "slug", "target_field": "payload.Generated Slug", "transform": "uppercase"},
                    {"from_inputs": "mode", "target_field": "payload.Mode", "transform": "lowercase", "default_value": "standard"},
                    {"target_field": "payload.Priority", "default_value": 7}
                ]
            },
            "workflow_inputs": {
                "mode": "FAST"
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution"]["status"] == "completed"
    normalized = payload["execution"]["steps"][1]["output"]["normalized"]
    assert normalized["generated_slug"] == "A-BETTER-APP-OS-FOR-REAL"
    assert normalized["mode"] == "fast"
    assert normalized["priority"] == 7


def test_generated_app_returns_mapping_suggestions_for_safe_schema_matches() -> None:
    create_producer = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.producer.suggest",
            "name": "Suggest Producer",
            "adapter_kind": "script",
            "command": ["python3", "tests/fixtures/script_slugify_skill.py"],
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string"},
                        "source_text": {"type": "string"},
                        "length": {"type": "integer"},
                        "adapter": {"type": "string"}
                    },
                    "required": ["slug", "source_text", "length", "adapter"],
                    "additionalProperties": True
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False
                }
            },
            "smoke_test_inputs": {"text": "Hello Suggest"}
        }
    )
    assert create_producer.status_code == 200

    create_consumer = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.consumer.suggest",
            "name": "Suggest Consumer",
            "adapter_kind": "callable",
            "generation_operation": "normalize_object_keys",
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string"},
                        "source_text": {"type": "string"},
                        "missing_field": {"type": "string"}
                    },
                    "required": ["slug", "source_text", "missing_field"],
                    "additionalProperties": False
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "normalized": {"type": "object"},
                        "top_level_keys": {"type": "array", "items": {"type": "string"}},
                        "adapter": {"type": "string"}
                    },
                    "required": ["normalized", "top_level_keys", "adapter"],
                    "additionalProperties": True
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False
                }
            },
            "smoke_test_inputs": {"slug": "x", "source_text": "y", "missing_field": "z"}
        }
    )
    assert create_consumer.status_code == 200

    response = client.post(
        "/apps/from-skills",
        json={
            "blueprint_id": "bp.generated.suggest",
            "name": "Generated Suggest App",
            "goal": "return mapping suggestions",
            "skill_ids": ["skill.producer.suggest", "skill.consumer.suggest"],
            "workflow_id": "wf.generated.suggest"
        }
    )
    assert response.status_code == 200
    payload = response.json()["result"]
    suggested = payload["suggested_mappings"]
    assert any(item["target_field"] == "slug" and item["field"] == "slug" for item in suggested)
    assert any(item["target_field"] == "source_text" and item["field"] == "source_text" for item in suggested)
    assert payload["unresolved_inputs"]["skill.2"] == ["missing_field"]


def test_generated_app_auto_applies_high_confidence_suggestions_on_install_run() -> None:
    create_producer = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.producer.auto",
            "name": "Auto Producer",
            "adapter_kind": "script",
            "command": ["python3", "tests/fixtures/script_slugify_skill.py"],
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string"},
                        "source_text": {"type": "string"},
                        "length": {"type": "integer"},
                        "adapter": {"type": "string"}
                    },
                    "required": ["slug", "source_text", "length", "adapter"],
                    "additionalProperties": True
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False
                }
            },
            "smoke_test_inputs": {"text": "Hello Auto"}
        }
    )
    assert create_producer.status_code == 200

    create_consumer = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.consumer.auto",
            "name": "Auto Consumer",
            "adapter_kind": "callable",
            "generation_operation": "echo_object_keys",
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string"},
                        "source_text": {"type": "string"}
                    },
                    "required": ["slug", "source_text"],
                    "additionalProperties": False
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "echoed": {"type": "object"},
                        "top_level_keys": {"type": "array", "items": {"type": "string"}},
                        "adapter": {"type": "string"}
                    },
                    "required": ["echoed", "top_level_keys", "adapter"],
                    "additionalProperties": True
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False
                }
            },
            "smoke_test_inputs": {"slug": "x", "source_text": "y"}
        }
    )
    assert create_consumer.status_code == 200

    response = client.post(
        "/apps/from-skills/install-run",
        json={
            "blueprint_id": "bp.generated.auto.apply",
            "name": "Generated Auto Apply App",
            "goal": "auto apply safe suggestions",
            "skill_ids": ["skill.producer.auto", "skill.consumer.auto"],
            "workflow_id": "wf.generated.auto.apply",
            "user_id": "auto-user",
            "step_inputs": {
                "skill.1": {"text": "A Better App OS, For Real"}
            }
        }
    )
    assert response.status_code == 200
    payload = response.json()
    echoed = payload["execution"]["steps"][1]["output"]["echoed"]
    assert echoed["slug"] == "a-better-app-os-for-real"
    assert echoed["source_text"] == "A Better App OS, For Real"
    assert any(item["target_field"] == "slug" and item["confidence"] == "high" for item in payload["result"]["suggested_mappings"])


def test_create_real_slugify_skill_and_run_generated_app() -> None:
    create_skill = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.text.slugify",
            "name": "Text Slugify Skill",
            "description": "normalize human titles into stable slugs",
            "adapter_kind": "script",
            "command": ["python3", "tests/fixtures/script_slugify_skill.py"],
            "tags": ["text", "normalization", "real-skill"],
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "source_text": {"type": "string"},
                        "slug": {"type": "string"},
                        "length": {"type": "integer"},
                        "adapter": {"type": "string"},
                    },
                    "required": ["source_text", "slug", "length", "adapter"],
                    "additionalProperties": True,
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
            },
            "smoke_test_inputs": {"text": "Hello, Agent System 2026!"},
        },
    )
    assert create_skill.status_code == 200
    create_payload = create_skill.json()
    assert create_payload["smoke_test"]["status"] == "completed"
    assert create_payload["smoke_test"]["output"]["slug"] == "hello-agent-system-2026"
    assert create_payload["smoke_test"]["output"]["adapter"] == "script"

    response = client.post(
        "/apps/from-skills/install-run",
        json={
            "blueprint_id": "bp.text.slugify.app",
            "name": "Text Slugify App",
            "goal": "turn user-facing titles into storage-safe slugs",
            "skill_ids": ["skill.text.slugify"],
            "workflow_id": "wf.text.slugify.app",
            "user_id": "slug-user",
            "step_inputs": {
                "skill.1": {"text": "A Better App OS, For Real"}
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["install"]["blueprint_id"] == "bp.text.slugify.app"
    assert payload["execution"]["status"] == "completed"
    assert payload["execution"]["steps"][0]["output"]["slug"] == "a-better-app-os-for-real"
    assert payload["execution"]["steps"][0]["output"]["length"] == len("a-better-app-os-for-real")
