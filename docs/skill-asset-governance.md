# Skill Asset Governance

## Purpose

Define a file-based governance model for skill assets so AgentSystem can distinguish:
- runtime state
- candidate/generated skills
- core system skill assets
- archived skill assets
- test/temp artifacts

This phase intentionally keeps file storage as the persistence backend.

## Directory model

```text
data/
  runtime/
  skill_assets/
    index.json
    core/
    candidates/
    archived/
  temp/
```

## Asset lifecycle

Statuses:
- `draft`
- `candidate`
- `core`
- `deprecated`
- `archived`

Default rule:
- generated skills land in `candidate`
- accepted skills are promoted to `core`

## Asset metadata

Each skill asset directory should contain `metadata.json` with:
- `skill_id`
- `asset_slug`
- `asset_status`
- `asset_origin`
- `runtime_adapter`
- `version`
- `content_maturity`
- `accepted`
- `accepted_at`
- `accepted_by`
- provenance fields such as template/workflow/experience

## Asset index

`data/skill_assets/index.json` provides a fast summary of all discovered assets.

## Consistency requirements

Each governed asset should have:
- `manifest.json`
- `metadata.json`
- input/output/error schemas
- entrypoint file
- `README.md`
- smoke test

Consistency checks must verify index/file/status alignment.
