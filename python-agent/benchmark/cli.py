from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from benchmark.config import SuiteConfig, load_suite
from benchmark.contracts import LoadedCase, RunMetadata
from benchmark.dataset import load_cases
from benchmark.orchestrator import run_cases
from benchmark.redaction import redact_error
from benchmark.reporting.json_report import build_report, write_report
from benchmark.runners.base import RunContext
from config import config


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
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
        write_report(build_report(metadata, results), args.output)
        if any(result.infrastructure_error is not None for result in results):
            return 2
        return 0
    except Exception as exc:
        print(f"benchmark infrastructure error: {redact_error(exc)}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
