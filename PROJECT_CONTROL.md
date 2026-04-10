# PROJECT_CONTROL.md

## Purpose

This file is the routing anchor for AgentSystem's project master control skill.
Its first job is to register and locate the master control skill for project-scoped governance work.

## Registered master control skill

- Skill id: `agentsystem-master-control`
- Skill path: `/root/project/AgentSystem/skills/generated/agentsystem-master-control/SKILL.md`
- Governed scope: the full AgentSystem repository at `/root/project/AgentSystem`

## When to enter the master control skill first

Enter the master control skill before proceeding when the request involves any of the following:
- project-level planning, restructuring, or roadmap shaping
- architecture or boundary decisions across apps, services, or subsystems
- deciding whether work belongs to project, app, domain, or module scope
- creating, revising, merging, or retiring subordinate skills
- updating project governance, control-plane artifacts, or structural ownership
- cross-module or cross-app impact analysis
- deciding what context should be loaded for a non-trivial project change

Do not require the master control skill for an obviously small, local, single-file change with clear narrow scope.

## Entry model

Outer agents or fresh sessions should read this file first to discover and route into the master control skill.
The master control skill may consult this file for consistency or recovery checks, but does not rely on it to locate itself during normal operation.

## Control-plane artifacts

The master control skill governs and maintains these project control artifacts:
- `/root/project/AgentSystem/control-plane/project-map.yaml`
- `/root/project/AgentSystem/control-plane/modules/`
- `/root/project/AgentSystem/control-plane/interfaces/`
- `/root/project/AgentSystem/control-plane/tasks/`

## Minimal routing rules

- Prefer anchor-guided routing over direct whole-repo loading.
- Prefer project/app/module scoped context over broad repository context.
- Structural work should pass through the master control layer before implementation proceeds.
- Critical project governance state must be kept in durable files, not only in chat history.

## Recovery rule

If the registered master control skill or control-plane artifacts are missing or inconsistent, repair the minimum required control skeleton before continuing structural governance work.
