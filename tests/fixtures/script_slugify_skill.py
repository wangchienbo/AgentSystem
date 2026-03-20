#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
import unicodedata


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower()
    replaced = re.sub(r"[^a-z0-9]+", "-", lowered)
    compact = re.sub(r"-+", "-", replaced).strip("-")
    return compact


def main() -> None:
    payload = json.load(sys.stdin)
    inputs = payload.get("inputs", {})
    text = inputs.get("text", "")
    slug = slugify(text)
    result = {
        "skill_id": payload.get("skill_id", "skill.text.slugify"),
        "status": "completed",
        "output": {
            "source_text": text,
            "slug": slug,
            "length": len(slug),
            "adapter": "script",
        },
        "error": "",
    }
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
