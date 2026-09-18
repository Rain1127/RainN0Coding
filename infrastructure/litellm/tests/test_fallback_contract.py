import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[3]
GATEWAY_PYTHON = ROOT / "infrastructure" / "litellm" / ".venv" / "Scripts" / "python.exe"
GATEWAY_CLI = ROOT / "infrastructure" / "litellm" / ".venv" / "Scripts" / "litellm.exe"


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


GATEWAY_PORT, PRIMARY_PORT, FALLBACK_PORT = (_free_port() for _ in range(3))
GATEWAY_URL = f"http://127.0.0.1:{GATEWAY_PORT}"
PRIMARY_URL = f"http://127.0.0.1:{PRIMARY_PORT}"
FALLBACK_URL = f"http://127.0.0.1:{FALLBACK_PORT}"


def _wait_until_ready(url: str, process: subprocess.Popen, timeout_seconds: float = 45) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.fail(f"contract process exited early with code {process.returncode}")
        try:
            response = httpx.get(url, timeout=0.5)
            if response.status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    pytest.fail(f"timed out waiting for {url}")


@pytest.fixture(scope="module", autouse=True)
def contract_stack():
    if not GATEWAY_PYTHON.exists() or not GATEWAY_CLI.exists():
        pytest.fail(
            "missing isolated LiteLLM environment; run "
            "py -3.12 -m venv infrastructure/litellm/.venv and install requirements.txt"
        )

    processes: list[subprocess.Popen] = []
    specs = [
        (
            {"FAKE_PROVIDER_MODE": "fail"},
            [
                sys.executable,
                "-m",
                "uvicorn",
                "infrastructure.litellm.tests.fake_openai_provider:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(PRIMARY_PORT),
                "--log-level",
                "warning",
            ],
            f"{PRIMARY_URL}/health",
        ),
        (
            {"FAKE_PROVIDER_MODE": "success"},
            [
                sys.executable,
                "-m",
                "uvicorn",
                "infrastructure.litellm.tests.fake_openai_provider:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(FALLBACK_PORT),
                "--log-level",
                "warning",
            ],
            f"{FALLBACK_URL}/health",
        ),
        (
            {
                "LITELLM_MASTER_KEY": "sk-contract",
                "LITELLM_MODE": "PRODUCTION",
                "PYTHONUTF8": "1",
                "FAKE_PRIMARY_API_BASE": f"{PRIMARY_URL}/v1",
                "FAKE_FALLBACK_API_BASE": f"{FALLBACK_URL}/v1",
            },
            [
                str(GATEWAY_CLI),
                "--config",
                "infrastructure/litellm/config.contract.yaml",
                "--host",
                "127.0.0.1",
                "--port",
                str(GATEWAY_PORT),
            ],
            f"{GATEWAY_URL}/health/liveliness",
        ),
    ]

    try:
        for overrides, command, readiness_url in specs:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                env=os.environ | overrides,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            processes.append(process)
            _wait_until_ready(readiness_url, process)
        yield
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in reversed(processes):
            if process.poll() is None:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def _reset_counts() -> None:
    for base_url in (PRIMARY_URL, FALLBACK_URL):
        response = httpx.post(f"{base_url}/test/reset", timeout=2)
        response.raise_for_status()


def _request_count(base_url: str) -> int:
    response = httpx.get(f"{base_url}/test/state", timeout=2)
    response.raise_for_status()
    return response.json()["request_count"]


def _completion(content: str) -> httpx.Response:
    return httpx.post(
        f"{GATEWAY_URL}/v1/chat/completions",
        headers={"Authorization": "Bearer sk-contract"},
        json={
            "model": "code-reasoning",
            "messages": [{"role": "user", "content": content}],
        },
        timeout=15,
    )


def test_primary_500_falls_back_without_same_deployment_retry():
    _reset_counts()

    response = _completion("ping")

    response.raise_for_status()
    assert response.json()["choices"][0]["message"]["content"] == "fallback-ok"
    assert _request_count(PRIMARY_URL) == 1
    assert _request_count(FALLBACK_URL) == 1


def test_both_providers_failing_returns_gateway_error():
    _reset_counts()

    response = _completion("fail-all")

    assert response.status_code >= 400
    assert _request_count(PRIMARY_URL) == 1
    assert _request_count(FALLBACK_URL) >= 1


def test_prometheus_exports_dashboard_metric_samples():
    _reset_counts()
    _completion("ping").raise_for_status()
    assert _completion("fail-all").status_code >= 400
    time.sleep(1)

    response = httpx.get(
        f"{GATEWAY_URL}/metrics",
        headers={"Authorization": "Bearer sk-contract"},
        follow_redirects=True,
        timeout=5,
    )

    response.raise_for_status()
    exported_names = sorted(
        set(re.findall(r"^# (?:HELP|TYPE) (litellm_[A-Za-z0-9_:]+)", response.text, re.MULTILINE))
    )
    for sample_name in (
        "litellm_proxy_total_requests_metric_total",
        "litellm_proxy_failed_requests_metric_total",
        "litellm_request_total_latency_metric_bucket",
        "litellm_total_tokens_metric_total",
        "litellm_spend_metric_total",
        "litellm_deployment_successful_fallbacks_total",
    ):
        assert sample_name in response.text, exported_names
