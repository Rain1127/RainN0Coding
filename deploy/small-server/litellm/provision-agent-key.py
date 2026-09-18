"""Provision restricted runtime keys and a candidate Python environment."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat
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
write_env = _runtime_module.write_env


BASE_URL = "http://127.0.0.1:4000"
BUSINESS_MODELS = ["code-reasoning", "code-structured", "code-lightweight"]
PROVIDER_FIELDS = {
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_API_BASE",
    "DEEPSEEK_REASONING_MODEL",
    "DEEPSEEK_CHAT_MODEL",
    "ZHIPU_API_KEY",
    "ZHIPU_BASE_URL",
    "ZHIPU_FLASH_MODEL",
    "ZHIPUAI_API_KEY",
    "ZHIPUAI_API_BASE",
    "ZHIPUAI_MODEL",
}


def api_request(
    path: str,
    token: str,
    payload: dict | None = None,
    *,
    expect_json: bool = True,
) -> dict | bytes:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        body = response.read()
    if not expect_json:
        return body
    return json.loads(body) if body else {}


def generate_key(master_key: str, alias: str, models: list[str]) -> str:
    response = api_request(
        "/key/generate",
        master_key,
        {
            "key_alias": alias,
            "models": models,
            "metadata": {"owner": "rainn0coding", "purpose": alias},
        },
    )
    if not isinstance(response, dict):
        raise SystemExit(f"LiteLLM returned an invalid response for {alias}")
    key = response.get("key")
    if not isinstance(key, str) or not key:
        raise SystemExit(f"LiteLLM did not return a key for {alias}")
    return key


def verify_restricted_key(agent_key: str) -> None:
    models_payload = api_request("/v1/models", agent_key)
    if not isinstance(models_payload, dict):
        raise SystemExit("Restricted key returned an invalid model list")
    visible_models = {
        item.get("id")
        for item in models_payload.get("data", [])
        if isinstance(item, dict)
    }
    if not set(BUSINESS_MODELS).issubset(visible_models):
        raise SystemExit("Restricted key cannot see every business model alias")

    try:
        api_request(
            "/v1/chat/completions",
            agent_key,
            {
                "model": "code-reasoning-glm",
                "messages": [{"role": "user", "content": "Reply exactly DENIED"}],
                "max_tokens": 1,
            },
        )
    except urllib.error.HTTPError as error:
        if error.code not in {400, 401, 403, 404}:
            raise SystemExit("Unexpected status while checking model restriction") from error
    else:
        raise SystemExit("Restricted key accepted an internal fallback model")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway-env", type=Path, default=Path("/etc/rainn0coding/litellm.env"))
    parser.add_argument("--python-env", type=Path, default=Path("/etc/rainn0coding/python.env"))
    parser.add_argument(
        "--candidate-env",
        type=Path,
        default=Path("/etc/rainn0coding/python.env.litellm-candidate"),
    )
    parser.add_argument(
        "--metrics-token",
        type=Path,
        default=Path("/etc/rainn0coding/litellm-metrics-token"),
    )
    arguments = parser.parse_args()

    gateway = parse_env(arguments.gateway_env)
    python = parse_env(arguments.python_env)
    master_key = gateway.get("LITELLM_MASTER_KEY", "")
    if not master_key:
        raise SystemExit("LITELLM_MASTER_KEY is missing")

    agent_key = generate_key(master_key, "python-agent", BUSINESS_MODELS)
    metrics_key = generate_key(master_key, "prometheus", ["code-lightweight"])
    verify_restricted_key(agent_key)
    api_request(
        "/v1/chat/completions",
        agent_key,
        {
            "model": "code-lightweight",
            "messages": [{"role": "user", "content": "Reply exactly OK"}],
            "temperature": 0,
            "max_tokens": 8,
        },
    )
    api_request("/metrics/", metrics_key, expect_json=False)

    candidate = {key: value for key, value in python.items() if key not in PROVIDER_FIELDS}
    candidate.update(
        {
            "LITELLM_BASE_URL": f"{BASE_URL}/v1",
            "LITELLM_HEALTH_URL": f"{BASE_URL}/health/liveliness",
            "LITELLM_API_KEY": agent_key,
            "LLM_REASONING_MODEL": "code-reasoning",
            "LLM_STRUCTURED_MODEL": "code-structured",
            "LLM_LIGHTWEIGHT_MODEL": "code-lightweight",
        }
    )
    write_env(arguments.candidate_env, candidate)
    python_env_stat = arguments.python_env.stat()
    if hasattr(os, "chown"):
        os.chown(
            arguments.candidate_env,
            python_env_stat.st_uid,
            python_env_stat.st_gid,
        )
    arguments.candidate_env.chmod(stat.S_IMODE(python_env_stat.st_mode))
    arguments.metrics_token.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_token = arguments.metrics_token.with_suffix(".tmp")
    descriptor = os.open(temporary_token, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as handle:
        handle.write(metrics_key + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary_token.chmod(0o640)
    temporary_token.replace(arguments.metrics_token)
    if hasattr(os, "chown"):
        os.chown(arguments.metrics_token, 0, 65534)
    arguments.metrics_token.chmod(0o640)
    print("Restricted agent and metrics keys provisioned; credentials omitted; candidate environment ready.")


if __name__ == "__main__":
    main()
