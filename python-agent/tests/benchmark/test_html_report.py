from __future__ import annotations

from pathlib import Path

import pytest

from benchmark.reporting.html_report import render_html


pytestmark = pytest.mark.benchmark

def _report() -> dict:
    return {
        "metadata": {"run_id": "run-1", "suite": "pr", "git_sha": "abc"},
        "summary": {"cases": 2, "passed": 1, "case_pass_rate": 0.5, "observations": 2},
        "by_target": {"supervisor": {"cases": 2, "passed": 1, "case_pass_rate": 0.5}},
        "by_category": {},
        "metrics": {"latency_ms": {"p50": 10, "p95": 20}},
        "gate": {"passed": False, "failures": [{"type": "absolute", "metric": "case_pass_rate"}]},
        "results": [{"case_id": "failed-case", "passed": False, "failures": ["wrong route"]}],
    }


def test_html_is_single_file_and_contains_gate_and_failures(tmp_path: Path) -> None:
    output = tmp_path / "report.html"

    render_html(_report(), output)

    html = output.read_text(encoding="utf-8")
    assert "run-1" in html
    assert "failed-case" in html
    assert "wrong route" in html
    assert "https://" not in html
    assert "<script src=" not in html
    for element_id in ("status", "summary", "targets", "metrics", "gate", "interview", "cases", "benchmark-data"):
        assert f'id="{element_id}"' in html
    for element_id in ("benchmark-status", "benchmark-summary", "benchmark-targets", "benchmark-metrics", "benchmark-gate", "benchmark-interview", "benchmark-cases"):
        assert f'id="{element_id}"' not in html
    assert ".grid > *, .card { min-width: 0; }" in html
    assert ".card-value, #status p, pre, code, th, td { overflow-wrap: anywhere; word-break: break-word; white-space: normal; }" in html
    assert '"card-value"' in html
    assert "th:nth-child(2), td:nth-child(2) { white-space: nowrap; width: 1%; }" in html
    assert "td:nth-child(3) { display: block; grid-column: 1 / -1; }" in html
    assert 'aria-labelledby="interview-heading"' in html
    assert '<th scope="col">' in html


def test_html_escapes_script_termination_in_report_data(tmp_path: Path) -> None:
    report = _report()
    payload = "</script><img src=x onerror=alert(1)>"
    report["results"][0]["failures"] = [payload]
    output = tmp_path / "report.html"

    render_html(report, output)

    html = output.read_text(encoding="utf-8")
    assert html.count('id="benchmark-data"') == 1
    assert "<\\/script><img" in html
    assert "</script><img" not in html
    data_start = html.index('type="application/json">') + len('type="application/json">')
    data_end = html.index("</script>", data_start)
    assert "<img src=x onerror=alert(1)>" not in html[:data_start] + html[data_end:]
    assert "node.textContent = text" in html
