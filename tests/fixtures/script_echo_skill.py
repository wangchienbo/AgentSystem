#!/usr/bin/env python3
from __future__ import annotations

import json
import sys


def main() -> None:
    payload = json.load(sys.stdin)
    text = payload.get("inputs", {}).get("text", "")
    result = {
        "skill_id": payload.get("skill_id", "skill.script"),
        "status": "completed",
        "output": {
            "echo": text,
            "adapter": "script",
        },
        "error": "",
    }
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
