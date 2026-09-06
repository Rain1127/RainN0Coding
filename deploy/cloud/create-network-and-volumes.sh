#!/usr/bin/env bash
set -Eeuo pipefail

docker network inspect rain-network >/dev/null 2>&1 \
  || docker network create rain-network >/dev/null

volumes=(
  rain-mysql
  rain-postgres
  rain-redis
  rain-qdrant
  rain-code-output
  rain-prometheus
  rain-grafana
  rain-tempo
)

for volume in "${volumes[@]}"; do
  docker volume inspect "$volume" >/dev/null 2>&1 \
    || docker volume create "$volume" >/dev/null
done

echo "Docker network and named volumes are ready."
