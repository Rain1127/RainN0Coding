#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../.." && pwd)"
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

: "${PROMETHEUS_IMAGE:?PROMETHEUS_IMAGE is required}"
: "${GRAFANA_IMAGE:?GRAFANA_IMAGE is required}"
: "${OTEL_IMAGE:?OTEL_IMAGE is required}"
: "${TEMPO_IMAGE:?TEMPO_IMAGE is required}"
: "${CURL_IMAGE:?CURL_IMAGE is required}"
: "${CLOUD_SECRETS_DIR:?CLOUD_SECRETS_DIR is required}"
: "${LITELLM_MASTER_KEY:?LITELLM_MASTER_KEY is required}"
: "${GRAFANA_ADMIN_USER:?GRAFANA_ADMIN_USER is required}"
: "${GRAFANA_ADMIN_PASSWORD:?GRAFANA_ADMIN_PASSWORD is required}"

[[ "$GRAFANA_ADMIN_PASSWORD" != "admin" ]] || {
  echo "GRAFANA_ADMIN_PASSWORD must not be admin." >&2
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

wait_running() {
  local name="$1"
  local status
  for _ in $(seq 1 30); do
    status="$(container_status "$name")"
    if [[ "$status" == "running" || "$status" == "healthy" ]]; then
      return 0
    fi
    if [[ "$status" == "exited" || "$status" == "dead" ]]; then
      docker logs --tail 50 "$name" >&2 || true
      return 1
    fi
    sleep 2
  done
  return 1
}

wait_http() {
  local name="$1"
  local url="$2"
  for _ in $(seq 1 45); do
    if docker run --rm --network rain-network "$CURL_IMAGE" \
      -fsS --max-time 5 "$url" >/dev/null 2>&1; then
      echo "${name} is ready."
      return 0
    fi
    sleep 2
  done
  echo "Timed out waiting for ${name}: ${url}" >&2
  docker logs --tail 50 "$name" >&2 || true
  return 1
}

preflight_image() {
  local image="$1"
  docker image inspect "$image" >/dev/null 2>&1 \
    || docker pull "$image" >/dev/null
}

for image in \
  "$PROMETHEUS_IMAGE" "$GRAFANA_IMAGE" "$OTEL_IMAGE" \
  "$TEMPO_IMAGE" "$CURL_IMAGE"; do
  preflight_image "$image"
done

for dependency in litellm python-agent java-api frontend; do
  require_healthy "$dependency"
done

install -d -m 700 "$CLOUD_SECRETS_DIR"
metrics_token_file="${CLOUD_SECRETS_DIR}/litellm_metrics_token"
umask 077
printf '%s' "$LITELLM_MASTER_KEY" >"$metrics_token_file"
# The parent directory is mode 700; world-readability is limited to the
# read-only bind mount needed by Prometheus' non-root container user.
chmod 644 "$metrics_token_file"

replace_container tempo
docker run -d --name tempo --network rain-network --restart unless-stopped \
  --volume "${script_dir}/tempo.yml:/etc/tempo.yml:ro" \
  --volume rain-tempo:/var/tempo \
  "$TEMPO_IMAGE" -config.file=/etc/tempo.yml >/dev/null
wait_running tempo
wait_http tempo http://tempo:3200/ready

replace_container otel-collector
docker run -d --name otel-collector --network rain-network \
  --restart unless-stopped \
  --volume "${script_dir}/otel-collector-config.yml:/etc/otelcol-contrib/config.yaml:ro" \
  "$OTEL_IMAGE" --config=/etc/otelcol-contrib/config.yaml >/dev/null
wait_running otel-collector
wait_http otel-collector http://otel-collector:13133/

replace_container prometheus
docker run -d --name prometheus --network rain-network --restart unless-stopped \
  --volume "${script_dir}/prometheus.yml:/etc/prometheus/prometheus.yml:ro" \
  --volume "${metrics_token_file}:/etc/prometheus/secrets/litellm_metrics_token:ro" \
  --volume rain-prometheus:/prometheus \
  "$PROMETHEUS_IMAGE" \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/prometheus \
  --storage.tsdb.retention.time=30d >/dev/null
wait_running prometheus
wait_http prometheus http://prometheus:9090/-/ready

replace_container grafana
docker run -d --name grafana --network rain-network --restart unless-stopped \
  --env GF_SECURITY_ADMIN_USER="$GRAFANA_ADMIN_USER" \
  --env GF_SECURITY_ADMIN_PASSWORD="$GRAFANA_ADMIN_PASSWORD" \
  --env GF_USERS_ALLOW_SIGN_UP=false \
  --env GF_ANALYTICS_REPORTING_ENABLED=false \
  --env PROMETHEUS_URL=http://prometheus:9090 \
  --volume "${repo_root}/grafana/datasources:/etc/grafana/provisioning/datasources:ro" \
  --volume "${repo_root}/grafana/dashboards:/etc/grafana/provisioning/dashboards:ro" \
  --volume rain-grafana:/var/lib/grafana \
  --publish 127.0.0.1:3001:3000 \
  "$GRAFANA_IMAGE" >/dev/null
wait_running grafana
wait_http grafana http://grafana:3000/api/health

echo "Prometheus, Grafana, Tempo, and the OTel Collector are ready."
