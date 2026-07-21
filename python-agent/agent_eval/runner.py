"""CLI and API entry point for offline Agent Golden Trajectory evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent_eval.adapters import execute_supervisor
from agent_eval.dataset import load_cases
from agent_eval.evaluator import evaluate_case
from agent_eval.reporting import build_report


def _read_records(records_path: str | Path | None) -> dict[str, dict[str, Any]]:
    if records_path is None:
        return {}
    raw = json.loads(Path(records_path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("records JSON must be an object keyed by Golden case id")
    return raw


def _record_output(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, float]]:
    if "output" not in record:
        return record, {}
    output = record["output"]
    metrics = record.get("metrics", {})
    if not isinstance(output, dict) or not isinstance(metrics, dict):
        raise ValueError("record envelope requires object values for output and metrics")
    return output, {name: float(value) for name, value in metrics.items() if isinstance(value, (int, float)) and not isinstance(value, bool)}


def evaluate_dataset(dataset_path: str | Path, agent: str | None = None, records_path: str | Path | None = None) -> dict:
    records = _read_records(records_path)
    results = []
    ignored = {Path(records_path)} if records_path is not None else set()
    for case in load_cases(dataset_path, ignored):
        if agent and case.agent != agent:
            continue
        if case.agent == "supervisor" and case.id not in records:
            actual_output = execute_supervisor(case)
            observed_metrics = {}
        elif case.id in records:
            actual_output, observed_metrics = _record_output(records[case.id])
        else:
            raise ValueError(f"missing saved output record for LLM-backed case: {case.id}")
        results.append(evaluate_case(case, actual_output, observed_metrics))
    return build_report(results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline Agent Golden Trajectory evaluation")
    parser.add_argument("--dataset", required=True, help="Golden case directory")
    parser.add_argument("--agent", help="Optional agent filter")
    parser.add_argument("--records", help="JSON object of saved outputs keyed by case id")
    parser.add_argument("--output", help="Report JSON path; stdout when omitted")
    args = parser.parse_args()
    report = evaluate_dataset(args.dataset, args.agent, args.records)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
