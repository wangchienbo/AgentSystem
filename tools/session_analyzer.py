#!/usr/bin/env python3
"""Session Analyzer — analyze user interaction logs to identify optimization opportunities.

Usage:
    python -m tools.session_analyzer --session-id session_123 --analyze
    python -m tools.session_analyzer --export /tmp/sessions.json
"""

import json
import argparse
from pathlib import Path
from typing import Any
from datetime import datetime

DATA_DIR = Path("/root/project/data")

def load_sessions() -> list[dict[str, Any]]:
    """Load all session data from disk."""
    sessions = []
    if not DATA_DIR.exists():
        return sessions
    
    # Load session files
    for session_file in DATA_DIR.glob("session_*.json"):
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
                sessions.append(session_data)
        except Exception as e:
            print(f"Failed to load {session_file}: {e}")
    
    return sessions

def analyze_sessions(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze sessions for optimization opportunities."""
    analysis = {
        "total_sessions": len(sessions),
        "total_messages": 0,
        "avg_messages_per_session": 0,
        "max_turns_reached": 0,
        "error_count": 0,
        "common_patterns": {},
        "optimization_suggestions": [],
    }
    
    total_messages = 0
    max_turns_sessions = []
    error_sessions = []
    
    for session in sessions:
        messages = session.get("messages", [])
        total_messages += len(messages)
        
        # Check for max_turns reached
        for msg in messages:
            content = msg.get("content", "")
            if "Reached max turns" in content:
                max_turns_sessions.append(session.get("session_id", "unknown"))
            
            if "error" in content.lower() or "504" in content:
                error_sessions.append(session.get("session_id", "unknown"))
    
    analysis["total_messages"] = total_messages
    analysis["avg_messages_per_session"] = total_messages / len(sessions) if sessions else 0
    analysis["max_turns_reached"] = len(max_turns_sessions)
    analysis["error_count"] = len(error_sessions)
    
    # Generate suggestions
    if max_turns_sessions:
        analysis["optimization_suggestions"].append(
            f"{len(max_turns_sessions)} sessions reached max_turns - consider strengthening convergence rules"
        )
    
    if error_sessions:
        analysis["optimization_suggestions"].append(
            f"{len(error_sessions)} sessions had errors/504 - investigate network or payload issues"
        )
    
    return analysis

def export_sessions(output_path: str) -> None:
    """Export all sessions to a JSON file."""
    sessions = load_sessions()
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sessions, f, indent=2, ensure_ascii=False)
    print(f"Exported {len(sessions)} sessions to {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Analyze session logs")
    parser.add_argument("--session-id", help="Specific session ID to analyze")
    parser.add_argument("--analyze", action="store_true", help="Run analysis")
    parser.add_argument("--export", help="Export sessions to file")
    
    args = parser.parse_args()
    
    if args.export:
        export_sessions(args.export)
        return
    
    if args.analyze:
        sessions = load_sessions()
        analysis = analyze_sessions(sessions)
        print(json.dumps(analysis, indent=2, ensure_ascii=False))
        return
    
    # Default: show summary
    sessions = load_sessions()
    print(f"Found {len(sessions)} sessions")
    if sessions:
        analysis = analyze_sessions(sessions)
        print(json.dumps(analysis, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
