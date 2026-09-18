"""Prepare root-only LiteLLM runtime configuration without exposing secrets."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
from urllib.parse import quote
from datetime import datetime, timezone


POSTGRES_IMAGE = "postgres:17.6-alpine@sha256:ef257d85f76e48da1c64832459b59fcaba1a4dac97bf5d7450c77753542eee94"
LITELLM_IMAGE = "ghcr.io/berriai/litellm:v1.98.0@sha256:20b5044b619055374061a6d5b7b08754cad75aeabbf82ddf4f69cc0cf80ddaf4"
KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, raw_value = line.partition("=")
        key = key.removeprefix("export ").strip()
        if not separator or not KEY_PATTERN.fullmatch(key):
            raise SystemExit(f"Invalid environment entry at {path}:{number}")
        parsed = shlex.split(f"VALUE={raw_value}", posix=True)
        if len(parsed) != 1 or not parsed[0].startswith("VALUE="):
            raise SystemExit(f"Invalid quoted value at {path}:{number}")
        values[key] = parsed[0][len("VALUE=") :]
    return values


def write_env(path: Path, values: dict[str, str]) -> None:
    lines: list[str] = []
    for key, value in values.items():
        if not KEY_PATTERN.fullmatch(key):
            raise ValueError(f"Invalid environment key: {key}")
        if any(character in value for character in "\r\n\0"):
            raise ValueError(f"Multiline value not allowed for {key}")
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key}="{escaped}"\n')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.writelines(lines)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def provider_model(prefix: str, value: str) -> str:
    return value if value.startswith(prefix + "/") else f"{prefix}/{value}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-env", type=Path, default=Path("/etc/rainn0coding/python.env"))
    parser.add_argument("--output", type=Path, default=Path("/etc/rainn0coding/litellm.env"))
    arguments = parser.parse_args()

    if hasattr(os, "geteuid") and os.geteuid() != 0:
        raise SystemExit("prepare-runtime.py must run as root")
    if not arguments.python_env.is_file():
        raise SystemExit(f"Python environment does not exist: {arguments.python_env}")

    python_env = parse_env(arguments.python_env)
    existing = parse_env(arguments.output)
    deepseek_key = python_env.get("DEEPSEEK_API_KEY") or existing.get("DEEPSEEK_API_KEY")
    zhipu_key = (
        python_env.get("ZHIPUAI_API_KEY")
        or python_env.get("ZHIPU_API_KEY")
        or existing.get("ZHIPUAI_API_KEY")
    )
    if not deepseek_key or not zhipu_key:
        raise SystemExit("Both DeepSeek and Zhipu provider keys are required")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = arguments.python_env.with_name(f"{arguments.python_env.name}.pre-litellm-{timestamp}")
    shutil.copy2(arguments.python_env, backup)
    os.chmod(backup, 0o600)

    database_password = existing.get("POSTGRES_PASSWORD") or secrets.token_urlsafe(32)
    postgres_user = existing.get("POSTGRES_USER", "litellm")
    postgres_database = existing.get("POSTGRES_DB", "litellm_gateway")
    database_url = (
        f"postgresql://{quote(postgres_user, safe='')}:{quote(database_password, safe='')}"
        f"@postgres:5432/{quote(postgres_database, safe='')}"
    )
    zhipu_model = (
        python_env.get("ZHIPUAI_MODEL")
        or python_env.get("ZHIPU_FLASH_MODEL")
        or existing.get("ZHIPUAI_MODEL")
        or "glm-4.7-flash"
    )

    runtime = {
        "POSTGRES_IMAGE": POSTGRES_IMAGE,
        "LITELLM_IMAGE": LITELLM_IMAGE,
        "POSTGRES_DB": postgres_database,
        "POSTGRES_USER": postgres_user,
        "POSTGRES_PASSWORD": database_password,
        "DATABASE_URL": database_url,
        "LITELLM_MASTER_KEY": existing.get("LITELLM_MASTER_KEY") or f"sk-{secrets.token_urlsafe(36)}",
        "LITELLM_SALT_KEY": existing.get("LITELLM_SALT_KEY") or secrets.token_urlsafe(36),
        "DEEPSEEK_API_KEY": deepseek_key,
        "DEEPSEEK_API_BASE": python_env.get("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1"),
        "DEEPSEEK_REASONING_MODEL": provider_model(
            "deepseek",
            python_env.get("DEEPSEEK_REASONING_MODEL", "deepseek-v4-pro"),
        ),
        "DEEPSEEK_CHAT_MODEL": provider_model(
            "deepseek",
            python_env.get("DEEPSEEK_CHAT_MODEL", "deepseek-chat"),
        ),
        "ZHIPUAI_API_KEY": zhipu_key,
        "ZHIPUAI_API_BASE": (
            python_env.get("ZHIPUAI_API_BASE")
            or python_env.get("ZHIPU_BASE_URL")
            or "https://open.bigmodel.cn/api/paas/v4"
        ),
        "ZHIPUAI_MODEL": provider_model("zai", zhipu_model),
        "REDIS_HOST": "rainn0coding-redis",
        "REDIS_PORT": python_env.get("REDIS_PORT", "6379"),
        "REDIS_PASSWORD": python_env.get("REDIS_PASSWORD", ""),
        "LITELLM_MODE": "PRODUCTION",
    }
    write_env(arguments.output, runtime)
    print(f"LiteLLM runtime prepared; credentials omitted; Python backup: {backup}")


if __name__ == "__main__":
    main()
