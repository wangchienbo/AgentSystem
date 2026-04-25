#!/usr/bin/env python3
"""Session Analyzer — analyze session + telemetry logs for optimization opportunities.

Usage:
    python -m tools.session_analyzer --analyze
    python -m tools.session_analyzer --analyze --user-id 123
    python -m tools.session_analyzer --analyze --session-id session_123
    python -m tools.session_analyzer --export /tmp/sessions.json
"""

import json
import argparse
from pathlib import Path
from typing import Any

DATA_DIR = Path("/root/project/data")
RUNTIME_DIR = Path("/root/project/AgentSystem/data/runtime")


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_sessions() -> list[dict[str, Any]]:
    sessions = []
    if not DATA_DIR.exists():
        return sessions
    for session_file in DATA_DIR.glob("session_*.json"):
        try:
            sessions.append(json.loads(session_file.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"Failed to load {session_file}: {e}")
    return sessions


def load_telemetry() -> dict[str, Any]:
    base = RUNTIME_DIR if RUNTIME_DIR.exists() else DATA_DIR
    return {
        "interactions": _load_json(base / "telemetry_interactions.json", {}),
        "steps": _load_json(base / "telemetry_steps.json", {}),
        "feedback": _load_json(base / "telemetry_feedback.json", {}),
        "version_bindings": _load_json(base / "telemetry_version_bindings.json", {}),
    }


def analyze_sessions(sessions: list[dict[str, Any]], telemetry: dict[str, Any], user_id: str | None = None, session_id: str | None = None) -> dict[str, Any]:
    analysis = {
        "total_sessions": 0,
        "total_messages": 0,
        "avg_messages_per_session": 0,
        "max_turns_reached": 0,
        "error_count": 0,
        "telemetry_interactions": 0,
        "telemetry_steps": 0,
        "user_id": user_id,
        "session_id": session_id,
        "optimization_suggestions": [],
    }

    filtered_sessions = []
    for session in sessions:
        sid = session.get("session_id")
        uid = session.get("user_id")
        if user_id and str(uid) != str(user_id):
            continue
        if session_id and sid != session_id:
            continue
        filtered_sessions.append(session)

    total_messages = 0
    max_turns_sessions = []
    error_sessions = []

    for session in filtered_sessions:
        messages = session.get("messages", [])
        total_messages += len(messages)
        for msg in messages:
            content = str(msg.get("content", ""))
            if "Reached max turns" in content:
                max_turns_sessions.append(session.get("session_id", "unknown"))
            if "error" in content.lower() or "504" in content:
                error_sessions.append(session.get("session_id", "unknown"))

    interactions = list(telemetry.get("interactions", {}).values())
    steps_map = telemetry.get("steps", {})

    if user_id:
        interactions = [x for x in interactions if str(x.get("user_id")) == str(user_id)]
    if session_id:
        interactions = [x for x in interactions if x.get("session_id") == session_id]

    relevant_interaction_ids = {x.get("interaction_id") for x in interactions}
    step_count = 0
    for iid, steps in steps_map.items():
        if iid in relevant_interaction_ids:
            step_count += len(steps)

    if step_count == 0 and (user_id or session_id):
        for iid, steps in steps_map.items():
            for step in steps:
                summary = step.get("payload_summary", {}) or {}
                if user_id and str(summary.get("user_id")) != str(user_id):
                    continue
                if session_id and summary.get("session_id") != session_id:
                    continue
                step_count += 1

    analysis["total_sessions"] = len(filtered_sessions)
    analysis["total_messages"] = total_messages
    analysis["avg_messages_per_session"] = total_messages / len(filtered_sessions) if filtered_sessions else 0
    analysis["max_turns_reached"] = len(max_turns_sessions)
    analysis["error_count"] = len(error_sessions)
    analysis["telemetry_interactions"] = len(interactions)
    analysis["telemetry_steps"] = step_count

    failed_interactions = [x for x in interactions if not x.get("success", True)]
    if failed_interactions:
        analysis["optimization_suggestions"].append(
            f"{len(failed_interactions)} telemetry interactions failed, prioritize replay + prompt/tooling optimization"
        )
    if len(interactions) == 0:
        analysis["optimization_suggestions"].append(
            "No telemetry interactions captured yet, verify LightBrain telemetry hook is active"
        )
    if step_count == 0 and len(interactions) > 0:
        analysis["optimization_suggestions"].append(
            "Interactions exist but no telemetry steps recorded, verify ToolCallingEngine step telemetry hook"
        )
    if max_turns_sessions:
        analysis["optimization_suggestions"].append(
            f"{len(max_turns_sessions)} sessions reached max_turns, inspect convergence rules"
        )
    if error_sessions:
        analysis["optimization_suggestions"].append(
            f"{len(error_sessions)} sessions had errors/504, inspect provider/network stability"
        )

    return analysis


def export_sessions(output_path: str) -> None:
    payload = {
        "sessions": load_sessions(),
        "telemetry": load_telemetry(),
    }
    Path(output_path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exported analysis payload to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Analyze session + telemetry logs")
    parser.add_argument("--session-id", help="Specific session ID to analyze")
    parser.add_argument("--user-id", help="Specific user ID to analyze")
    parser.add_argument("--analyze", action="store_true", help="Run analysis")
    parser.add_argument("--export", help="Export sessions + telemetry to file")
    args = parser.parse_args()

    if args.export:
        export_sessions(args.export)
        return

    sessions = load_sessions()
    telemetry = load_telemetry()
    if args.analyze or True:
        analysis = analyze_sessions(sessions, telemetry, user_id=args.user_id, session_id=args.session_id)
        print(json.dumps(analysis, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
