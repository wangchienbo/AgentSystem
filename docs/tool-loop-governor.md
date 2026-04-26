# Tool Loop Governor Skill

## Purpose

A compact, top-level guidance skill for multi-turn tool calling.
It should not encode tool-specific business logic.
Its job is to help the agent decide:
- whether to continue calling tools
- whether to stop and answer
- whether to switch from fragmented tool calls to a script-first strategy
- which branch guidance to load next

## Core Contract

1. Treat tool calling as an evidence-collection loop, not a one-shot answer generator.
2. Do not treat candidate hits, filenames, or partial matches as final facts.
3. If current evidence is insufficient, prefer the highest-value next action instead of answering early.
4. If current evidence is sufficient for the user's requested precision, stop calling tools and answer.
5. If the task requires chained transformations, iteration, filtering, aggregation, or output-to-input dependency, strongly consider a script-first strategy.
6. Do not keep calling tools without an explicit unresolved question.
7. When stopping without full confirmation, state the remaining uncertainty plainly.

## Branch Selection

Pick the most specific branch that matches the task:
- `branches/repo-introspection.md`
  - codebase inspection, implementation verification, config/source tracing
- `branches/runtime-observation.md`
  - live state, process status, network/service/runtime facts
- `branches/script-first-strategy.md`
  - multi-step dependency chains, repeated transformations, batching, parsing, extraction, aggregation
- `branches/stop-rules.md`
  - when uncertain whether to continue, stop, or switch strategy

## Loop Discipline

At each tool loop step, decide explicitly:
1. What question is still unresolved?
2. What evidence do I already have?
3. What is the single highest-value next action?
4. Is another direct tool call better, or is a script now the better execution surface?
5. What condition would let me stop after the next step?

## Script-First Bias

Prefer writing and running a script when one or more are true:
- later inputs depend on earlier outputs
- the task needs loops, filtering, ranking, parsing, or aggregation
- multiple file/system queries must be combined before answering
- the task would otherwise require many serial tool calls
- a reproducible local helper can reduce token/tool overhead

## Non-Goals

This skill should not:
- hardcode specific tool names as truth levels
- embed scene-specific business facts
- replace downstream branch instructions
- force all tasks into scripts
