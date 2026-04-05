# Executable Allowed Blueprint

Generated candidate executable skill scaffold for `skill.blueprint.exec.allowed`.

- template: `text_transform`
- runtime: `python3` + `json_stdio`
- entrypoint: `main.py`
- asset status: `candidate`

## Input
See `input.schema.json`. Example payload: `{"text": "Hello World"}`

## Output
See `output.schema.json`. Expected primary field: `text`

## Smoke test
Run `pytest tests/test_smoke.py -q` inside this skill directory.
