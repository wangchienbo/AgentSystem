---
name: platform-core-control
description: Structural subordinate skill for AgentSystem platform-core. Use for work on core app-os substrate, contracts, registry, lifecycle, runtime persistence, standard interfaces, and closely owned platform-core boundaries.
---

# Platform Core Control

Structural subordinate skill for the `platform-core` domain in AgentSystem.

## Scope
Owns focused work related to the core app-os substrate, core contracts, registry/lifecycle foundations, persistence boundaries, and standard platform interfaces.

## Entry conditions
Use this skill when the requested work is primarily inside platform-core and does not require broad cross-domain restructuring.
Escalate back to `agentsystem-master-control` when changes substantially impact multiple project domains or alter domain boundaries.

## Owned focus
- app/core
- app/models
- core registry/lifecycle contract surfaces
- persistence-adjacent platform definitions when primarily platform-core scoped

## Operating rules
- prefer local platform-core context before loading other domains
- escalate if runtime/control-plane, telemetry/governance, or generated-skill toolchain changes become first-order concerns
- update project control artifacts when owned boundaries or dependencies materially shift
