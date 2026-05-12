from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


SCALAR_SUM_KEYS = [
    "total_scenarios",
    "planned_total_turns",
    "executed_turn_budget",
    "scenarios_all_ok",
    "scenarios_with_fail",
    "total_turns",
    "total_ok",
    "total_fail",
    "total_errors",
    "total_seconds",
]


def merge_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    if not reports:
        raise ValueError("at least one report is required")
    merged_details: list[dict[str, Any]] = []
    for report in reports:
        details = report.get("details") or []
        merged_details.extend(item for item in details if isinstance(item, dict))
    merged_details.sort(key=lambda item: str(item.get("id") or ""))

    merged: dict[str, Any] = {
        "source_report_count": len(reports),
        "source_report_labels": [report.get("run_id") or report.get("started_at") or f"report-{idx+1}" for idx, report in enumerate(reports)],
        "merge_kind": "bounded_split_after_artifact",
        "details": merged_details,
    }
    exemplar = reports[0]
    for key in [
        "base_url",
        "delay_seconds",
        "timeout_seconds",
        "max_turns_per_scenario",
        "max_consecutive_failures",
    ]:
        if key in exemplar:
            merged[key] = exemplar[key]
    for key in SCALAR_SUM_KEYS:
        merged[key] = sum(int(report.get(key) or 0) for report in reports)
    total_turns = int(merged.get("total_turns") or 0)
    total_ok = int(merged.get("total_ok") or 0)
    total_seconds = float(merged.get("total_seconds") or 0.0)
    merged["pass_rate_pct"] = round((total_ok / total_turns) * 100, 1) if total_turns else 0.0
    merged["avg_turn_seconds"] = round(total_seconds / total_turns, 1) if total_turns else 0.0
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge bounded split 50x20 JSON reports into one artifact")
    parser.add_argument("reports", nargs="+")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    merged = merge_reports([_load_report(Path(path)) for path in args.reports])
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output_path), "total_scenarios": merged["total_scenarios"], "pass_rate_pct": merged["pass_rate_pct"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
