"""Verify the private LiteLLM deployment without displaying credentials."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request


_runtime_spec = importlib.util.spec_from_file_location(
    "litellm_prepare_runtime", Path(__file__).with_name("prepare-runtime.py")
)
if _runtime_spec is None or _runtime_spec.loader is None:
    raise RuntimeError("Unable to load LiteLLM runtime helpers")
_runtime_module = importlib.util.module_from_spec(_runtime_spec)
_runtime_spec.loader.exec_module(_runtime_module)
parse_env = _runtime_module.parse_env


BASE_URL = "http://127.0.0.1:4000"
REQUIRED_MODELS = {"code-reasoning", "code-structured", "code-lightweight"}


def container_state(name: str) -> tuple[str, str | None]:
    raw = subprocess.check_output(
        ["docker", "inspect", "--format", "{{json .State}}", name], text=True
    )
    state = json.loads(raw)
    health = state.get("Health", {}).get("Status")
    return state.get("Status", "unknown"), health


def request(path: str, token: str, expect_json: bool = False) -> object:
    http_request = urllib.request.Request(
        f"{BASE_URL}{path}", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(http_request, timeout=10) as response:
        body = response.read()
    return json.loads(body) if expect_json else body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", type=Path, default=Path("/etc/rainn0coding/litellm.env"))
    arguments = parser.parse_args()
    runtime = parse_env(arguments.env)
    master_key = runtime.get("LITELLM_MASTER_KEY", "")
    if not master_key:
        raise SystemExit("LITELLM_MASTER_KEY is missing")

    postgres_status, postgres_health = container_state("rainn0coding-litellm-postgres")
    gateway_status, gateway_health = container_state("rainn0coding-litellm")
    if (postgres_status, postgres_health) != ("running", "healthy"):
        raise SystemExit("LiteLLM PostgreSQL container is not healthy")
    if (gateway_status, gateway_health) != ("running", "healthy"):
        raise SystemExit("LiteLLM gateway container is not healthy")

    published = subprocess.check_output(
        ["docker", "port", "rainn0coding-litellm", "4000/tcp"], text=True
    ).strip()
    if published != "127.0.0.1:4000":
        raise SystemExit(f"Unexpected LiteLLM port binding: {published or 'none'}")

    last_error: Exception | None = None
    for _ in range(12):
        try:
            request("/health/liveliness", master_key)
            models_payload = request("/v1/models", master_key, expect_json=True)
            request("/metrics/", master_key)
            break
        except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(2)
    else:
        raise SystemExit(f"LiteLLM HTTP verification failed: {type(last_error).__name__}")

    model_ids = {
        item.get("id")
        for item in models_payload.get("data", [])
        if isinstance(item, dict)
    }
    missing = REQUIRED_MODELS - model_ids
    if missing:
        raise SystemExit(f"Missing LiteLLM business aliases: {sorted(missing)}")
    print("LiteLLM verification passed: containers healthy, private port, models and metrics available.")


if __name__ == "__main__":
    main()
