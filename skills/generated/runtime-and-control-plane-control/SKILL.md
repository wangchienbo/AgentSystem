---
name: runtime-and-control-plane-control
description: Structural subordinate skill for AgentSystem runtime-and-control-plane. Use for work on runtime host, scheduler, supervisor, interaction gateway, operator-facing control surfaces, and adjacent runtime/control orchestration boundaries.
---

# Runtime and Control Plane Control

Structural subordinate skill for the `runtime-and-control-plane` domain in AgentSystem.

## Scope
Owns focused work related to runtime host behavior, scheduler/supervisor flows, interaction/control-plane routing surfaces, and adjacent operator-facing runtime control concerns.

## Entry conditions
Use this skill when the requested work is primarily inside runtime/control orchestration and does not require broad cross-domain restructuring.
Escalate back to `agentsystem-master-control` when changes substantially impact platform-core contracts, telemetry-governance policy, or broad system-wide boundaries.

## Owned focus
- app/bootstrap
- runtime host / scheduler / supervisor related services
- interaction/control-plane routing surfaces under app/api and app/services where runtime/control responsibility is primary

## Operating rules
- prefer runtime/control-plane context first
- escalate if platform-core contract changes or telemetry/governance impacts become central
- update project control artifacts when runtime/control interfaces materially shift
