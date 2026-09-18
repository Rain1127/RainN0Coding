#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_ENV="${LITELLM_RUNTIME_ENV:-/etc/rainn0coding/litellm.env}"
export LITELLM_RUNTIME_ENV="${RUNTIME_ENV}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "rollback.sh must run as root" >&2
  exit 1
fi
if [[ ! -f "${RUNTIME_ENV}" ]]; then
  echo "LiteLLM runtime environment not found; nothing changed" >&2
  exit 0
fi

docker compose --env-file "${RUNTIME_ENV}" -f "${SCRIPT_DIR}/compose.yml" stop litellm postgres
echo "LiteLLM containers stopped. PostgreSQL volume, configuration and backups were preserved."
