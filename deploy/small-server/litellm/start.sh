#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/compose.yml"
RUNTIME_ENV="${LITELLM_RUNTIME_ENV:-/etc/rainn0coding/litellm.env}"
NETWORK_NAME="rainn0coding-cloud_default"
export LITELLM_RUNTIME_ENV="${RUNTIME_ENV}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "start.sh must run as root" >&2
  exit 1
fi
for required in "${COMPOSE_FILE}" "${RUNTIME_ENV}" "${SCRIPT_DIR}/../../../infrastructure/litellm/config.yaml"; do
  if [[ ! -f "${required}" ]]; then
    echo "Missing required file: ${required}" >&2
    exit 1
  fi
done
if [[ "$(stat -c '%a' "${RUNTIME_ENV}")" != "600" ]]; then
  echo "Runtime environment must have mode 0600" >&2
  exit 1
fi
if ! docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  echo "Required Docker network is missing: ${NETWORK_NAME}" >&2
  exit 1
fi

compose=(docker compose --env-file "${RUNTIME_ENV}" -f "${COMPOSE_FILE}")
"${compose[@]}" config --quiet
"${compose[@]}" pull postgres litellm
"${compose[@]}" up -d postgres

for _ in $(seq 1 40); do
  if [[ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' rainn0coding-litellm-postgres)" == "healthy" ]]; then
    break
  fi
  sleep 3
done
if [[ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' rainn0coding-litellm-postgres)" != "healthy" ]]; then
  echo "LiteLLM PostgreSQL did not become healthy" >&2
  exit 1
fi

"${compose[@]}" up -d litellm
for _ in $(seq 1 50); do
  if [[ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' rainn0coding-litellm)" == "healthy" ]]; then
    break
  fi
  sleep 3
done
python3 "${SCRIPT_DIR}/verify.py" --env "${RUNTIME_ENV}"
