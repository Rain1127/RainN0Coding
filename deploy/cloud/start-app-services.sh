#!/usr/bin/env bash
set -Eeuo pipefail

applications_only=false
release_override=""
while (($#)); do
  case "$1" in
    --applications-only)
      applications_only=true
      shift
      ;;
    --release)
      [[ $# -ge 2 ]] || {
        echo "--release requires a value." >&2
        exit 2
      }
      release_override="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
versions_file="${script_dir}/versions.env"
runtime_file="${script_dir}/runtime.env"

[[ -f "$versions_file" ]] || {
  echo "Missing ${versions_file}" >&2
  exit 1
}
[[ -f "$runtime_file" ]] || {
  echo "Missing ${runtime_file}; copy runtime.env.example and fill secrets." >&2
  exit 1
}

set -a
# shellcheck disable=SC1090
source "$versions_file"
# shellcheck disable=SC1090
source "$runtime_file"
set +a

if [[ -n "$release_override" ]]; then
  APP_RELEASE="$release_override"
fi

: "${APP_RELEASE:?APP_RELEASE is required}"
: "${PUBLIC_ORIGIN:?PUBLIC_ORIGIN is required}"
: "${PUBLIC_HTTP_PORT:?PUBLIC_HTTP_PORT is required}"
: "${CLOUD_SECRETS_DIR:?CLOUD_SECRETS_DIR is required}"
: "${LITELLM_IMAGE:?LITELLM_IMAGE is required}"
: "${LITELLM_MASTER_KEY:?LITELLM_MASTER_KEY is required}"
: "${DEEPSEEK_API_KEY:?DEEPSEEK_API_KEY is required}"
: "${DEEPSEEK_API_BASE:?DEEPSEEK_API_BASE is required}"
: "${DEEPSEEK_REASONING_MODEL:?DEEPSEEK_REASONING_MODEL is required}"
: "${DEEPSEEK_CHAT_MODEL:?DEEPSEEK_CHAT_MODEL is required}"
: "${ZHIPUAI_API_KEY:?ZHIPUAI_API_KEY is required}"
: "${ZHIPUAI_API_BASE:?ZHIPUAI_API_BASE is required}"
: "${ZHIPUAI_MODEL:?ZHIPUAI_MODEL is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${MYSQL_DATABASE:?MYSQL_DATABASE is required}"
: "${MYSQL_USER:?MYSQL_USER is required}"
: "${MYSQL_PASSWORD:?MYSQL_PASSWORD is required}"
: "${REDIS_PASSWORD:?REDIS_PASSWORD is required}"
: "${PYTHON_AI_INTERNAL_TOKEN:?PYTHON_AI_INTERNAL_TOKEN is required}"
: "${JAVA_XMS:?JAVA_XMS is required}"
: "${JAVA_XMX:?JAVA_XMX is required}"
: "${PYTHON_WORKERS:?PYTHON_WORKERS is required}"

[[ "$APP_RELEASE" =~ ^[A-Za-z0-9._-]+$ ]] || {
  echo "APP_RELEASE contains unsupported characters." >&2
  exit 1
}
[[ "$PUBLIC_HTTP_PORT" =~ ^[0-9]+$ ]] || {
  echo "PUBLIC_HTTP_PORT must be numeric." >&2
  exit 1
}
[[ "$PUBLIC_ORIGIN" != *".invalid"* ]] || {
  echo "Replace the example PUBLIC_ORIGIN before deployment." >&2
  exit 1
}

replace_container() {
  local name="$1"
  if docker container inspect "$name" >/dev/null 2>&1; then
    docker rm -f "$name" >/dev/null
  fi
}

container_status() {
  docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$1"
}

wait_healthy() {
  local name="$1"
  local status
  for _ in $(seq 1 90); do
    status="$(container_status "$name")"
    if [[ "$status" == "healthy" ]]; then
      echo "${name} is healthy."
      return 0
    fi
    if [[ "$status" == "exited" || "$status" == "dead" ]]; then
      docker logs --tail 50 "$name" >&2 || true
      return 1
    fi
    sleep 2
  done
  echo "Timed out waiting for ${name} health." >&2
  docker logs --tail 50 "$name" >&2 || true
  return 1
}

require_healthy() {
  local name="$1"
  if ! docker container inspect "$name" >/dev/null 2>&1; then
    echo "Required container ${name} does not exist." >&2
    exit 1
  fi
  if [[ "$(container_status "$name")" != "healthy" ]]; then
    echo "Required container ${name} is not healthy." >&2
    exit 1
  fi
}

preflight_image() {
  local image="$1"
  docker image inspect "$image" >/dev/null 2>&1 \
    || docker pull "$image" >/dev/null
}

urlencode() {
  local raw="$1"
  local encoded=""
  local char
  local index
  for ((index = 0; index < ${#raw}; index++)); do
    char="${raw:index:1}"
    case "$char" in
      [a-zA-Z0-9.~_-]) encoded+="$char" ;;
      *) printf -v encoded '%s%%%02X' "$encoded" "'$char" ;;
    esac
  done
  printf '%s' "$encoded"
}

for dependency in mysql postgres redis qdrant; do
  require_healthy "$dependency"
done

frontend_image="rain/frontend:${APP_RELEASE}"
java_image="rain/java-api:${APP_RELEASE}"
python_image="rain/python-agent:${APP_RELEASE}"
for image in "$frontend_image" "$java_image" "$python_image"; do
  docker image inspect "$image" >/dev/null 2>&1 || {
    echo "Required application image is missing: ${image}" >&2
    exit 1
  }
done
if [[ "$applications_only" == false ]]; then
  preflight_image "$LITELLM_IMAGE"
fi

if [[ "$applications_only" == false ]]; then
  postgres_password_encoded="$(urlencode "$POSTGRES_PASSWORD")"
  database_url="postgresql://${POSTGRES_USER}:${postgres_password_encoded}@postgres:5432/${POSTGRES_DB}"

  replace_container litellm
  docker run -d --name litellm --network rain-network --restart unless-stopped \
    --env LITELLM_MASTER_KEY --env DEEPSEEK_API_KEY \
    --env DEEPSEEK_API_BASE --env DEEPSEEK_REASONING_MODEL \
    --env DEEPSEEK_CHAT_MODEL --env ZHIPUAI_API_KEY \
    --env ZHIPUAI_API_BASE --env ZHIPUAI_MODEL \
    --env REDIS_PASSWORD --env REDIS_HOST=redis --env REDIS_PORT=6379 \
    --env DATABASE_URL="$database_url" \
    --volume "${script_dir}/../../infrastructure/litellm/config.yaml:/app/config.yaml:ro" \
    --health-cmd='python -c "import urllib.request; urllib.request.urlopen(\"http://127.0.0.1:4000/health/liveliness\", timeout=3)"' \
    --health-interval=10s --health-timeout=5s --health-retries=18 \
    "$LITELLM_IMAGE" --config /app/config.yaml --port 4000 >/dev/null
  wait_healthy litellm
else
  require_healthy litellm
fi

provision_agent_key() {
  docker exec litellm python -c '
import json
import os
import urllib.request

body = json.dumps({
    "key_alias": "python-agent",
    "models": ["code-reasoning", "code-structured", "code-lightweight"],
    "rpm_limit": 20,
    "tpm_limit": 200000,
    "max_budget": 10,
    "budget_duration": "30d",
}).encode()
request = urllib.request.Request(
    "http://127.0.0.1:4000/key/generate",
    data=body,
    headers={
        "Authorization": "Bearer " + os.environ["LITELLM_MASTER_KEY"],
        "Content-Type": "application/json",
    },
)
with urllib.request.urlopen(request, timeout=20) as response:
    print(json.load(response)["key"], end="")
')'
}

persist_agent_key() {
  install -d -m 700 "$CLOUD_SECRETS_DIR"
  umask 077
  printf '%s' "$LITELLM_API_KEY" >"$agent_key_file"
  chmod 600 "$agent_key_file"
}

validate_agent_key() {
  docker exec \
    --env LITELLM_AGENT_KEY="$LITELLM_API_KEY" \
    litellm python -c '
import json
import os
import urllib.request

request = urllib.request.Request(
    "http://127.0.0.1:4000/v1/models",
    headers={"Authorization": "Bearer " + os.environ["LITELLM_AGENT_KEY"]},
)
with urllib.request.urlopen(request, timeout=10) as response:
    models = {item["id"] for item in json.load(response).get("data", [])}
required = {"code-reasoning", "code-structured", "code-lightweight"}
raise SystemExit(0 if required <= models else 1)
' >/dev/null
}

agent_key_file="${CLOUD_SECRETS_DIR}/litellm_agent_key"
runtime_agent_key="${LITELLM_API_KEY:-}"
if [[ -z "$runtime_agent_key" ]]; then
  if [[ -s "$agent_key_file" ]]; then
    LITELLM_API_KEY="$(<"$agent_key_file")"
  else
    [[ "$applications_only" == false ]] || {
      echo "Missing ${agent_key_file}; run a full application start first." >&2
      exit 1
    }
    LITELLM_API_KEY="$(provision_agent_key)"
    [[ "$LITELLM_API_KEY" == sk-* ]] || {
      echo "LiteLLM returned an invalid service key." >&2
      exit 1
    }
    persist_agent_key
    echo "Provisioned the python-agent virtual key in ${agent_key_file}."
  fi
fi

if ! validate_agent_key; then
  if [[ "$applications_only" == true || -n "$runtime_agent_key" ]]; then
    echo "The configured LiteLLM agent key is invalid or missing model access." >&2
    exit 1
  fi
  LITELLM_API_KEY="$(provision_agent_key)"
  [[ "$LITELLM_API_KEY" == sk-* ]] || {
    echo "LiteLLM returned an invalid replacement service key." >&2
    exit 1
  }
  persist_agent_key
  validate_agent_key || {
    echo "The replacement LiteLLM agent key failed validation." >&2
    exit 1
  }
  echo "Replaced a stale python-agent virtual key."
fi
export LITELLM_API_KEY

replace_container python-agent
docker run -d --name python-agent --network rain-network --restart unless-stopped \
  --env LITELLM_API_KEY \
  --env INTERNAL_API_TOKEN="$PYTHON_AI_INTERNAL_TOKEN" \
  --env APP_ENV=production --env INTERNAL_API_ALLOW_MISSING_TOKEN=false \
  --env LITELLM_BASE_URL=http://litellm:4000/v1 \
  --env LITELLM_HEALTH_URL=http://litellm:4000/health/liveliness \
  --env LLM_REASONING_MODEL --env LLM_STRUCTURED_MODEL \
  --env LLM_LIGHTWEIGHT_MODEL \
  --env REDIS_HOST=redis --env REDIS_PORT=6379 --env REDIS_PASSWORD \
  --env QDRANT_URL=http://qdrant:6333 --env QDRANT_API_KEY \
  --env VECTOR_DB_PROVIDER=qdrant --env LOCAL_EMBEDDING_ENABLED \
  --env AGENT_MAX_CONCURRENT_REQUESTS \
  --env OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://otel-collector:4318/v1/traces \
  --env CODE_OUTPUT_DIR=/data/code-output \
  --env SQLITE_DB_PATH=/data/code-output/.rag/exact_search.db \
  --volume rain-code-output:/data/code-output \
  "$python_image" uvicorn server.main:app --host 0.0.0.0 --port 8000 \
  --workers "$PYTHON_WORKERS" >/dev/null
wait_healthy python-agent

replace_container java-api
docker run -d --name java-api --network rain-network --restart unless-stopped \
  --env SPRING_PROFILES_ACTIVE=production \
  --env MYSQL_URL="jdbc:mysql://mysql:3306/${MYSQL_DATABASE}" \
  --env MYSQL_USERNAME="$MYSQL_USER" --env MYSQL_PASSWORD \
  --env REDIS_HOST=redis --env REDIS_PORT=6379 --env REDIS_PASSWORD \
  --env PYTHON_AI_BASE_URL=http://python-agent:8000 \
  --env PYTHON_AI_INTERNAL_TOKEN \
  --env APP_CORS_ALLOWED_ORIGIN_PATTERNS="$PUBLIC_ORIGIN" \
  --env APP_DEPLOY_HOST="${PUBLIC_ORIGIN%/}/api/static" \
  --env OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://otel-collector:4318/v1/traces \
  --env JAVA_TOOL_OPTIONS="-Xms${JAVA_XMS} -Xmx${JAVA_XMX}" \
  --volume rain-code-output:/app/tmp \
  "$java_image" >/dev/null
wait_healthy java-api

replace_container frontend
docker run -d --name frontend --network rain-network --restart unless-stopped \
  --publish "${PUBLIC_HTTP_PORT}:80" \
  "$frontend_image" >/dev/null
wait_healthy frontend

echo "LiteLLM, Python, Java, and frontend are healthy."
