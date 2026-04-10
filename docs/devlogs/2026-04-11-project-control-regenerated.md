# 2026-04-11 Project control regenerated

## Summary
Regenerated AgentSystem project control artifacts from scratch using the new control-skill-factory direction.

## What changed
- created fresh `PROJECT_CONTROL.md` as the routing anchor for the master control skill
- created fresh minimal control-plane skeleton under `control-plane/`
- created first generated master control skill under `skills/generated/agentsystem-master-control/`
- encoded foundational subordinate capabilities directly inside the master control skill:
  - project-manager
  - app-manager
  - context-assembler
  - skill-governor
  - control-plane-maintainer

## Design direction
- anchor first responsibility: register and locate the master control skill
- master control skill is the project's internal control layer, not the outer assistant persona
- structural governance should route through the master control layer before implementation proceeds
- persistent subordinate skills should only be created when scope evidence is strong enough

## Notes
No prior in-repo `PROJECT_CONTROL.md`, `control-plane/`, or generated master-control skill was found in the current checkout before regeneration.
