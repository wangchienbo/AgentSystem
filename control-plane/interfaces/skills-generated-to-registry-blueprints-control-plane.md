# Interface: skills-generated -> registry-blueprints-control-plane

## Purpose
Connect generated skill/app assembly behavior with blueprint validation, registry registration, install posture, and release/control-plane governance.

## Provides
- generated skill and generated app assembly outputs
- blueprint-ready and registry-relevant artifacts

## Consumes
- blueprint validation behavior
- registry registration and release governance behavior

## Contract
- generated app outputs must stay compatible with blueprint validation and registry control-plane expectations
- new app design meta-skill capabilities should declare where they hand off to registry-facing blueprint/install/release surfaces

## Compatibility Notes
- if app-skill-factory or app-control generation enters the system, its outputs should be routed through this contract instead of bypassing registry/blueprint governance

## Risks
- uncontrolled app generation can silently bypass blueprint or release governance expectations
