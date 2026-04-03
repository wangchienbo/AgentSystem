# Review runtime practice for workspace assistant app refinement

Generated executable skill scaffold for `skill.suggested.practice.review.for.bp.workspace.assistant.app.refine.exec.user`.

- template: `text_transform`
- runtime: `python3` + `json_stdio`
- entrypoint: `main.py`

## Input
See `input.schema.json`. Example payload: `{"text": "Hello World"}`

## Output
See `output.schema.json`. Expected primary field: `text`

## Smoke test
Run `pytest tests/test_smoke.py -q` inside this skill directory.
