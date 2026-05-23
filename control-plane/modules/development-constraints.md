# Development Constraints Control (开发约束控制)

> **类别**: structural subordinate skill  
> **作用域**: development-constraints  
> **版本**: recursive-init-v2

## Purpose

This subordinate skill governs the development constraints that the AI model must follow when writing or modifying AgentSystem code. It is loaded before any code generation task to prevent architectural drift.

## Source

Primary constraint file: `docs/development-constraints.md`

## Core Rules (loaded every time)

### 1. Architecture
- App is first-class citizen. User commands → Workflow → App lifecycle.
- Deterministic first. LLM only for semantics, generation, diagnosis.
- Data separated: app data / runtime state / metadata / skill assets.
- Intelligence invocation requires: need + policy + budget + confirmation.

### 2. Skill Layering
- System skills → `app/services/system_skills/` (required_runtime, local-first, no default intelligence)
- Builder skills → build_only, may use intelligence
- All skill calls through `system.skill_runtime` — no direct skill-to-skill calls.
- New skills: manifest.json + metadata.json + contracts + entrypoint + smoke test.

### 3. App Design
- Blueprint → Install → Runtime → Persist
- Blueprint must have: goal, roles, tasks, workflows, required_modules/skills, storage_plan, runtime_policy.
- Apps isolated. Cross-app communication via event bus only.

### 4. Context Reading (large files)
- **Never** read > 50KB file in full. Use grep/head/tail or read_file with line ranges.
- Read directory/index first, then target specific files.
- L0 (working set) loaded every time. L1 selective. L2 by reference only.

### 5. Code Structure
| Function | Location |
|----------|----------|
| System skills | `app/services/system_skills/` |
| Business services | `app/services/` |
| Models | `app/models/` |
| API routes | `app/api/` |
| Runtime core | `app/runtime/` |
| Orchestration | `app/orchestration/` |
| Tests | `tests/` |

### 6. Prohibitions
- ❌ LLM calls in core services (must go through Skill layer)
- ❌ Cross-module direct imports of internals
- ❌ Business logic in API handlers (must be in service layer)
- ❌ Hardcoded paths (use `resolve_runtime_paths()`)
- ❌ Skip bootstrap to instantiate services
- ❌ Add to platform core what can be a Skill
- ❌ Read > 50KB files in full (use retrieval)

## Before Any Code Change

1. Read `docs/system-relationship-map.md` for impact analysis
2. Read this module file for constraints
3. Check relevant docs per the "改什么读什么" table
4. Write tests before merging
5. Update system-relationship-map.md if module boundaries change

## Related Files

- `docs/development-constraints.md` — full constraint specification
- `docs/skill-design-principles.md` — skill design principles
- `docs/skill-asset-governance.md` — skill asset governance
- `docs/code-structure.md` — code structure map
- `docs/system-relationship-map.md` — system relationship graph
