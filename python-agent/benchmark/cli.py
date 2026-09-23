from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from benchmark.config import SuiteConfig, load_suite
from benchmark.contracts import BenchmarkReport, LoadedCase, RunMetadata
from benchmark.dataset import load_cases
from benchmark.baseline import compatibility_key, load_compatible, promote
from benchmark.gates import evaluate_gate
from benchmark.orchestrator import run_cases
from benchmark.redaction import redact_error
from benchmark.reporting.json_report import build_report, read_report, write_report
from benchmark.runners.base import RunContext
from config import config
import yaml


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _prompt_fingerprint(root: Path) -> str:
    fixed_paths = [root / "llm_factory.py", root / "workflow" / "autogen_discussion.py", root / "rag" / "ragas_evaluator.py"]
    for path in fixed_paths:
        if not path.is_file():
            raise ValueError(f"required prompt file is missing: {path.relative_to(root).as_posix()}")
    paths = sorted(
        list((root / "agents").glob("*_agent.py")) + fixed_paths,
        key=lambda path: path.as_posix(),
    )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _dataset_fingerprint(cases: Sequence[LoadedCase]) -> str:
    digest = hashlib.sha256()
    for loaded in sorted(cases, key=lambda item: item.case.id):
        digest.update(_canonical_json(loaded.case.model_dump(mode="json")))
        digest.update(b"\0")
        if loaded.record_path is not None:
            digest.update(loaded.record_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _load_cases(suite: SuiteConfig, suite_dir: Path) -> list[LoadedCase]:
    asset_root = suite_dir.parent
    cases: list[LoadedCase] = []
    for configured_root in suite.dataset_roots:
        root = (suite_dir / configured_root).resolve()
        if root.exists():
            cases.extend(load_cases(root, asset_root=asset_root))
    if not cases:
        raise ValueError("suite contains no benchmark cases from existing dataset roots")
    ids = [item.case.id for item in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate benchmark case id across suite dataset roots")
    disallowed = sorted({item.case.execution.mode for item in cases} - set(suite.allowed_modes))
    if disallowed:
        raise ValueError(f"suite contains disallowed modes: {disallowed}")
    return cases


def _git_sha() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, encoding="utf-8").strip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="benchmark")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--suite", required=True)
    run = commands.add_parser("run")
    run.add_argument("--suite", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--git-sha")
    run.add_argument("--record-dir", default="benchmarks/records/runs")
    compare = commands.add_parser("compare")
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--policy", required=True)
    baseline = commands.add_parser("baseline")
    baseline_commands = baseline.add_subparsers(dest="baseline_command", required=True)
    promote_command = baseline_commands.add_parser("promote")
    promote_command.add_argument("--report", required=True)
    promote_command.add_argument("--baseline-dir", required=True)
    return parser


def _read_report(path: str | Path) -> BenchmarkReport:
    try:
        return read_report(path)
    except Exception as exc:
        raise ValueError(f"invalid benchmark report {path}: {exc}") from exc


def _load_policy(path: str | Path) -> dict:
    try:
        policy = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid benchmark policy {path}: {exc}") from exc
    if not isinstance(policy, dict):
        raise ValueError("benchmark policy must contain a top-level object")
    return policy


def _write_report_atomic(report: BenchmarkReport, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        write_report(report, temporary)
        os.replace(temporary, destination)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "compare":
            candidate = _read_report(args.candidate)
            baseline = _read_report(args.baseline)
            if compatibility_key(candidate) != compatibility_key(baseline):
                raise ValueError("candidate and baseline compatibility keys do not match")
            gate = evaluate_gate(candidate, baseline, _load_policy(args.policy))
            _write_report_atomic(candidate.model_copy(update={"gate": gate}), args.candidate)
            return 0 if gate["passed"] else 1
        if args.command == "baseline":
            target = promote(_read_report(args.report), args.baseline_dir)
            print(target)
            return 0
        suite, suite_dir = load_suite(args.suite)
        cases = _load_cases(suite, suite_dir)
        if args.command == "validate":
            print(f"validated {len(cases)} benchmark cases for suite {suite.name}")
            return 0

        started_at = datetime.now(timezone.utc).isoformat()
        run_id = uuid4().hex
        metadata = RunMetadata(
            run_id=run_id,
            suite=suite.name,
            git_sha=args.git_sha or _git_sha(),
            dataset_versions=sorted({item.case.dataset_version for item in cases}),
            dataset_fingerprint=_dataset_fingerprint(cases),
            prompt_fingerprint=_prompt_fingerprint(Path(__file__).resolve().parent.parent),
            model_aliases=dict(config.LLM_MODEL_ALIASES),
            offline=suite.offline,
            started_at=started_at,
        )
        results = run_cases(cases, RunContext(run_id=run_id, offline=suite.offline, record_dir=Path(args.record_dir)))
        report = build_report(metadata, results)
        policy = _load_policy((suite_dir / suite.policy).resolve())
        baseline = load_compatible(report, (suite_dir / suite.baseline_dir).resolve())
        gate = evaluate_gate(report, baseline, policy)
        write_report(report.model_copy(update={"gate": gate}), args.output)
        if any(result.infrastructure_error is not None for result in results):
            return 2
        return 0 if gate["passed"] else 1
    except Exception as exc:
        print(f"benchmark infrastructure error: {redact_error(exc)}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
