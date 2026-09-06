#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
versions_file="${script_dir}/versions.env"
runtime_file="${script_dir}/runtime.env"

[[ -f "$versions_file" ]] || {
  echo "Missing ${versions_file}" >&2
  exit 1
}
[[ -f "$runtime_file" ]] || {
  echo "Missing ${runtime_file}" >&2
  exit 1
}

set -a
# shellcheck disable=SC1090
source "$versions_file"
# shellcheck disable=SC1090
source "$runtime_file"
set +a

: "${CURL_IMAGE:?CURL_IMAGE is required}"
: "${CLOUD_SECRETS_DIR:?CLOUD_SECRETS_DIR is required}"
: "${PUBLIC_HTTP_PORT:?PUBLIC_HTTP_PORT is required}"
: "${LITELLM_MASTER_KEY:?LITELLM_MASTER_KEY is required}"

pass() {
  echo "[PASS] $1"
}

fail() {
  echo "[FAIL] $1" >&2
  exit 1
}

container_status() {
  docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$1"
}

for name in mysql postgres redis qdrant litellm python-agent java-api frontend; do
  docker container inspect "$name" >/dev/null 2>&1 \
    || fail "container ${name} is missing"
  [[ "$(container_status "$name")" == "healthy" ]] \
    || fail "container ${name} is not healthy"
  pass "container ${name} is healthy"
done

for name in tempo otel-collector prometheus grafana; do
  docker container inspect "$name" >/dev/null 2>&1 \
    || fail "container ${name} is missing"
  status="$(container_status "$name")"
  [[ "$status" == "running" || "$status" == "healthy" ]] \
    || fail "container ${name} is not running"
  pass "container ${name} is running"
done

network_get() {
  docker run --rm --network rain-network "$CURL_IMAGE" \
    -fsS --max-time 10 "$@"
}

check_http() {
  local name="$1"
  local url="$2"
  network_get "$url" >/dev/null || fail "${name} endpoint failed"
  pass "${name} endpoint"
}

check_http "LiteLLM liveness" "http://litellm:4000/health/liveliness"
check_http "Python health" "http://python-agent:8000/api/health"
check_http "Java Actuator" "http://java-api:8123/api/actuator/health"
check_http "frontend" "http://frontend/healthz"
check_http "Tempo readiness" "http://tempo:3200/ready"
check_http "OTel Collector health" "http://otel-collector:13133/"
check_http "Prometheus readiness" "http://prometheus:9090/-/ready"
check_http "Grafana health" "http://grafana:3000/api/health"

agent_key="${LITELLM_API_KEY:-}"
if [[ -z "$agent_key" ]]; then
  agent_key_file="${CLOUD_SECRETS_DIR}/litellm_agent_key"
  [[ -s "$agent_key_file" ]] || fail "LiteLLM agent key is missing"
  agent_key="$(<"$agent_key_file")"
fi

models="$(network_get \
  -H "Authorization: Bearer ${agent_key}" \
  http://litellm:4000/v1/models)" \
  || fail "LiteLLM authorized model listing failed"
for model in code-reasoning code-structured code-lightweight; do
  grep -Fq "\"id\":\"${model}\"" <<<"$models" \
    || fail "LiteLLM model listing is missing ${model}"
done
pass "LiteLLM virtual-key model boundary"

metrics="$(network_get \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  http://litellm:4000/metrics/)" \
  || fail "LiteLLM metrics endpoint failed"
grep -Fq "litellm_" <<<"$metrics" \
  || fail "LiteLLM metrics contain no litellm_ families"
pass "LiteLLM protected metrics"

check_prometheus_job() {
  local job="$1"
  local encoded_job
  local response
  encoded_job="$(printf '%s' "$job" | sed 's/ /%20/g')"
  response="$(network_get \
    "http://prometheus:9090/api/v1/query?query=up%7Bjob%3D%22${encoded_job}%22%7D")" \
    || fail "Prometheus query failed for ${job}"
  grep -Fq ',"1"]' <<<"$response" \
    || fail "Prometheus target ${job} is not up"
  pass "Prometheus target ${job} is up"
}

check_prometheus_job RainN0Coding
check_prometheus_job RainN0Coding-python
check_prometheus_job LiteLLM

private_containers=(
  mysql postgres redis qdrant litellm python-agent java-api
  tempo otel-collector prometheus
)
for name in "${private_containers[@]}"; do
  published="$(docker port "$name" 2>/dev/null || true)"
  [[ -z "$published" ]] || fail "${name} unexpectedly publishes a host port"
done
pass "private containers publish no host ports"

frontend_ports="$(docker port frontend 80/tcp 2>/dev/null || true)"
[[ -n "$frontend_ports" ]] || fail "frontend has no public HTTP mapping"
while IFS= read -r mapping; do
  [[ "$mapping" == "0.0.0.0:${PUBLIC_HTTP_PORT}" \
    || "$mapping" == "[::]:${PUBLIC_HTTP_PORT}" ]] \
    || fail "frontend has an unexpected mapping: ${mapping}"
done <<<"$frontend_ports"
pass "frontend public port allowlist"

grafana_ports="$(docker port grafana 3000/tcp 2>/dev/null || true)"
[[ "$grafana_ports" == "127.0.0.1:3001" ]] \
  || fail "Grafana must bind only to 127.0.0.1:3001"
pass "Grafana loopback-only port"

echo "ALL CLOUD HEALTH CHECKS PASSED"
