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
  echo "Missing ${runtime_file}; copy runtime.env.example and fill secrets." >&2
  exit 1
}

set -a
# shellcheck disable=SC1090
source "$versions_file"
# shellcheck disable=SC1090
source "$runtime_file"
set +a

: "${MYSQL_IMAGE:?MYSQL_IMAGE is required}"
: "${POSTGRES_IMAGE:?POSTGRES_IMAGE is required}"
: "${REDIS_IMAGE:?REDIS_IMAGE is required}"
: "${QDRANT_IMAGE:?QDRANT_IMAGE is required}"
: "${MYSQL_DATABASE:?MYSQL_DATABASE is required}"
: "${MYSQL_USER:?MYSQL_USER is required}"
: "${MYSQL_PASSWORD:?MYSQL_PASSWORD is required}"
: "${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${REDIS_PASSWORD:?REDIS_PASSWORD is required}"

replace_container() {
  local name="$1"
  if docker container inspect "$name" >/dev/null 2>&1; then
    docker rm -f "$name" >/dev/null
  fi
}

wait_healthy() {
  local name="$1"
  local status
  for _ in $(seq 1 60); do
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$name")"
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

preflight_image() {
  local image="$1"
  docker image inspect "$image" >/dev/null 2>&1 \
    || docker pull "$image" >/dev/null
}

for image in "$MYSQL_IMAGE" "$POSTGRES_IMAGE" "$REDIS_IMAGE" "$QDRANT_IMAGE"; do
  preflight_image "$image"
done

"${script_dir}/create-network-and-volumes.sh"

replace_container mysql
docker run -d --name mysql --network rain-network --restart unless-stopped \
  --env MYSQL_DATABASE --env MYSQL_USER --env MYSQL_PASSWORD \
  --env MYSQL_ROOT_PASSWORD \
  --volume rain-mysql:/var/lib/mysql \
  --health-cmd='mysqladmin ping -h 127.0.0.1 -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" --silent' \
  --health-interval=10s --health-timeout=5s --health-retries=12 \
  "$MYSQL_IMAGE" >/dev/null
wait_healthy mysql

replace_container postgres
docker run -d --name postgres --network rain-network --restart unless-stopped \
  --env POSTGRES_DB --env POSTGRES_USER --env POSTGRES_PASSWORD \
  --volume rain-postgres:/var/lib/postgresql/data \
  --health-cmd='pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  --health-interval=10s --health-timeout=5s --health-retries=12 \
  "$POSTGRES_IMAGE" >/dev/null
wait_healthy postgres

replace_container redis
docker run -d --name redis --network rain-network --restart unless-stopped \
  --env REDIS_PASSWORD \
  --volume rain-redis:/data \
  --health-cmd='redis-cli --no-auth-warning -a "$REDIS_PASSWORD" ping | grep -q PONG' \
  --health-interval=10s --health-timeout=5s --health-retries=12 \
  "$REDIS_IMAGE" redis-server --appendonly yes --requirepass "$REDIS_PASSWORD" \
  >/dev/null
wait_healthy redis

replace_container qdrant
docker run -d --name qdrant --network rain-network --restart unless-stopped \
  --volume rain-qdrant:/qdrant/storage \
  --health-cmd="bash -c ':> /dev/tcp/127.0.0.1/6333'" \
  --health-interval=10s --health-timeout=5s --health-retries=12 \
  "$QDRANT_IMAGE" >/dev/null
wait_healthy qdrant

echo "MySQL, PostgreSQL, Redis, and Qdrant are healthy on rain-network."
