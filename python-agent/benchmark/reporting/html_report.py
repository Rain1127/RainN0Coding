from __future__ import annotations

import json
import re
from pathlib import Path


_TOKEN = "BENCHMARK_DATA_JSON"


def render_html(report: dict, output: str | Path) -> Path:
    """Render a self-contained HTML report from an already-persisted JSON report."""
    template = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
    if template.count(_TOKEN) != 1:
        raise ValueError("HTML report template must contain BENCHMARK_DATA_JSON exactly once")
    # HTML script parsing is case-insensitive; escape every casing of the
    # closing-script prefix while keeping the embedded JSON parseable.
    payload = re.sub(
        r"</",
        lambda match: "<\\/",
        json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False),
        flags=re.IGNORECASE,
    )
    rendered = template.replace(_TOKEN, payload)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    return target
