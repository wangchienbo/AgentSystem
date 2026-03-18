# System Skills Service Layout

This directory groups the default platform/system-skill service implementations.

Current modules:
- `app_config.py` — per-app deterministic configuration surface
- `state_audit.py` — runtime state and audit event services
- `context.py` — shared app-context skill surface

Related bootstrap/wiring:
- `app/services/system_skill_registry.py` — built-in skill metadata/manifest registration
- `app/bootstrap/skills.py` — built-in handler assembly and runtime registration
- `app/bootstrap/runtime.py` — service graph construction
