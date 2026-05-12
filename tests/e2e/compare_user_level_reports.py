from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _scenario_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    details = report.get("details") or []
    return {
        str(item.get("id")): item
        for item in details
        if isinstance(item, dict) and item.get("id")
    }


def compare_reports(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_scenarios = _scenario_map(before)
    after_scenarios = _scenario_map(after)
    all_ids = sorted(set(before_scenarios) | set(after_scenarios))

    improved: list[str] = []
    regressed: list[str] = []
    unchanged: list[str] = []
    added: list[str] = []
    removed: list[str] = []
    scenario_deltas: list[dict[str, Any]] = []

    for scenario_id in all_ids:
        before_item = before_scenarios.get(scenario_id)
        after_item = after_scenarios.get(scenario_id)
        if before_item is None and after_item is not None:
            added.append(scenario_id)
            continue
        if before_item is not None and after_item is None:
            removed.append(scenario_id)
            continue
        assert before_item is not None and after_item is not None
        before_verdict = str(before_item.get("verdict") or "unknown")
        after_verdict = str(after_item.get("verdict") or "unknown")
        before_ok = int(before_item.get("ok") or 0)
        after_ok = int(after_item.get("ok") or 0)
        before_fail = int(before_item.get("fail") or 0)
        after_fail = int(after_item.get("fail") or 0)
        before_errors = int(before_item.get("errors") or 0)
        after_errors = int(after_item.get("errors") or 0)
        changed = (
            before_verdict != after_verdict
            or before_ok != after_ok
            or before_fail != after_fail
            or before_errors != after_errors
        )
        if not changed:
            unchanged.append(scenario_id)
            continue
        delta = {
            "id": scenario_id,
            "before_verdict": before_verdict,
            "after_verdict": after_verdict,
            "before_ok": before_ok,
            "after_ok": after_ok,
            "before_fail": before_fail,
            "after_fail": after_fail,
            "before_errors": before_errors,
            "after_errors": after_errors,
            "before_history_expectation_ok": before_item.get("history_expectation_ok"),
            "after_history_expectation_ok": after_item.get("history_expectation_ok"),
        }
        score = (after_ok - before_ok) - (after_fail - before_fail) - (after_errors - before_errors)
        if score > 0 or (before_verdict != "passed" and after_verdict == "passed"):
            improved.append(scenario_id)
        elif score < 0 or (before_verdict == "passed" and after_verdict != "passed"):
            regressed.append(scenario_id)
        else:
            unchanged.append(scenario_id)
        scenario_deltas.append(delta)

    before_total = int(before.get("total_ok") or 0) + int(before.get("total_fail") or 0) + int(before.get("total_errors") or 0)
    after_total = int(after.get("total_ok") or 0) + int(after.get("total_fail") or 0) + int(after.get("total_errors") or 0)
    before_pass_rate = float(before.get("pass_rate_pct") or 0.0)
    after_pass_rate = float(after.get("pass_rate_pct") or 0.0)

    return {
        "before_report_label": before.get("run_id") or before.get("started_at") or "before",
        "after_report_label": after.get("run_id") or after.get("started_at") or "after",
        "before_total_turns": before_total,
        "after_total_turns": after_total,
        "before_pass_rate_pct": before_pass_rate,
        "after_pass_rate_pct": after_pass_rate,
        "pass_rate_delta_pct": round(after_pass_rate - before_pass_rate, 1),
        "before_scenarios_all_ok": int(before.get("scenarios_all_ok") or 0),
        "after_scenarios_all_ok": int(after.get("scenarios_all_ok") or 0),
        "scenario_full_pass_delta": int(after.get("scenarios_all_ok") or 0) - int(before.get("scenarios_all_ok") or 0),
        "improved_scenarios": improved,
        "regressed_scenarios": regressed,
        "unchanged_scenarios": unchanged,
        "added_scenarios": added,
        "removed_scenarios": removed,
        "scenario_deltas": scenario_deltas,
        "comparison_status": "regression_detected" if regressed else "ok",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare pre/post migration 50x20 JSON reports")
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    comparison = compare_reports(_load_report(Path(args.before)), _load_report(Path(args.after)))
    text = json.dumps(comparison, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
