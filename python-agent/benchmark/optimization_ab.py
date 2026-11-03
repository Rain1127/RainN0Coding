"""Repeated live workflow evaluation, with and without verified repair experience.

python -m benchmark.optimization_ab --output reports/optimization-ab.json --repeats 3
Use --probe-only to check infrastructure without spending model calls.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4
import httpx
import yaml
from config import config


async def evaluate(output: Path, repeats: int, probe_only: bool) -> int:
    source = Path(__file__).resolve().parents[1] / "benchmarks/optimization/tasks-v1.yaml"
    dataset = yaml.safe_load(source.read_text(encoding="utf-8"))
    report = {"execution": "live_full_workflow", "dataset_version": dataset["dataset_version"],
              "dataset_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "repeats": repeats, "observations": [], "infrastructure_error": None,
              "quality_improvement": None, "token_improvement": None, "cost_improvement": None}
    output.parent.mkdir(parents=True, exist_ok=True)
    base = config.LITELLM_BASE_URL.rstrip("/").removesuffix("/v1")
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(base + "/health/readiness", headers={"Authorization": "Bearer " + config.LITELLM_API_KEY})
            response.raise_for_status()
    except Exception as exc:
        report["infrastructure_error"] = type(exc).__name__
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2
    if not probe_only:
        from workflow.code_gen_workflow import run_workflow_async
        from workflow.resilience import finalize_state
        from benchmark.cli import _git_sha, _source_manifest
        report.update(git_sha=_git_sha(), source_manifest=_source_manifest(), model_aliases=config.LLM_MODEL_ALIASES)
        original = config.REPAIR_EXPERIENCE_ENABLED
        writes = config.FEEDBACK_WRITES_ENABLED
        config.FEEDBACK_WRITES_ENABLED = False
        try:
            for repeat in range(repeats):
                for enabled in (False, True) if repeat % 2 == 0 else (True, False):
                    config.REPAIR_EXPERIENCE_ENABLED = enabled
                    for case in dataset["cases"]:
                        started = time.monotonic()
                        state = {}
                        async for state in run_workflow_async(case["request"], "optimization-ab", uuid4().hex, case["code_gen_type"]):
                            pass
                        final = state.get("final_result") or finalize_state(state)["final_result"]
                        report["observations"].append({"case": case["id"], "repeat": repeat, "experience_enabled": enabled,
                            "status": final["status"], "build_status": final.get("build_status"),
                            "runtime": final.get("runtime_result"), "repair_count": final.get("build_repair_count"),
                            "budget": final.get("budget"), "elapsed_seconds": time.monotonic() - started})
        finally:
            config.REPAIR_EXPERIENCE_ENABLED = original
            config.FEEDBACK_WRITES_ENABLED = writes
        import statistics
        report["summary"] = {}
        for enabled in (False, True):
            observations = [o for o in report["observations"] if o["experience_enabled"] == enabled]
            tokens = [(o.get("budget") or {}).get("tokens") for o in observations]
            report["summary"]["experience_on" if enabled else "experience_off"] = {
                "observations": len(observations),
                "accepted_rate": sum(o["status"] in ("success", "degraded_success") for o in observations) / len(observations),
                "elapsed_median_seconds": statistics.median(o["elapsed_seconds"] for o in observations),
                "mean_tokens": statistics.mean(tokens) if all(isinstance(t, (float, int)) for t in tokens) else None,
                "mean_repairs": statistics.mean(o["repair_count"] for o in observations),
            }
    from benchmark.redaction import redact
    output.write_text(json.dumps(redact(report), ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3, choices=range(2, 6))
    parser.add_argument("--probe-only", action="store_true")
    args = parser.parse_args()
    return asyncio.run(evaluate(args.output, args.repeats, args.probe_only))


if __name__ == "__main__":
    raise SystemExit(main())
