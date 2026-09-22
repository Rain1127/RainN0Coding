from __future__ import annotations

import json
from pathlib import Path

from benchmark.cli import main


SUITE = "benchmarks/suites/pr.yaml"


def test_validate_pr_suite_prints_validated(capsys) -> None:
    assert main(["validate", "--suite", SUITE]) == 0
    assert "validated" in capsys.readouterr().out.lower()


def test_run_pr_suite_writes_report_metadata_and_raw_records(tmp_path: Path) -> None:
    output = tmp_path / "pr-result.json"
    record_dir = tmp_path / "records"

    assert main([
        "run", "--suite", SUITE, "--output", str(output), "--git-sha", "test-sha",
        "--record-dir", str(record_dir),
    ]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["metadata"]["git_sha"] == "test-sha"
    assert report["summary"]["cases"] == 6
    assert len(list(record_dir.glob("*/*.json"))) == 6
