# 2026-04-11: Meta-App Orchestrator — LLM Design Layer for App Creation

## Motivation
User direction: app creation should go through meta-app (LLM design layer) first, then deterministic assembly. Also integrated maoxuan-skill as a strategic thinking tool within the system.

## Architecture

```
User Request (AppCreationFromMetaAppRequest)
  → POST /apps/from-meta-app
    → MetaAppCreationOrchestrator
      → MetaAppBootstrapService (LLM-powered design)
        → Produces AppControlSkillResult
      → SkillFactoryService (deterministic assembly)
        → Produces AppBlueprint
      → AppInstallerService (optional)
        → Installs and runs the app
```

## Changes

### 1. New Model (app/models/app_meta_app.py)
- `AppCreationFromMetaAppRequest` with fields: app_name, goal, app_kind, complexity, user_id, trigger, scope, context, auto_install, workflow_inputs

### 2. New Orchestrator (app/services/meta_app/orchestrator.py)
- `MetaAppCreationOrchestrator` bridges LLM design layer with deterministic assembly
- `AppCreationOrchestrationResult` returns both control_plan and blueprint

### 3. New API Endpoint (app/api/main.py)
- `POST /apps/from-meta-app` — create app through meta-app design layer
- Supports optional auto_install flag

### 4. Runtime Wiring (app/bootstrap/runtime.py)
- Instantiates MetaAppCreationOrchestrator with meta_app_bootstrap + skill_factory

### 5. Maoxuan-Skill Integration
- Added as system.maoxuan built-in skill
- MaoxuanSkillService calls LLM with Mao Zedong thinking framework
- 7 mental models + 10 decision heuristics available

## Commits
- `b70d0ae` — Add LLM-powered app control skill generation to system.meta_app
- `ea73ee1` — Wire system.meta_app as LLM design layer for app creation
