#!/bin/bash
set -euo pipefail
directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
topic=${GENERATION_QUEUE_TOPIC:-rain-code-generation-v1}
[[ "$topic" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]{0,248}$ ]] || { echo 'Invalid topic'; exit 2; }
command -v docker >/dev/null
docker compose -f "$directory/compose.yml" config --quiet
if ! docker container inspect rainn0coding-kafka >/dev/null 2>&1; then
  available_kib=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
  (( available_kib >= 1228800 )) || { echo 'Need at least 1200 MiB available memory before first Kafka start'; exit 1; }
  if ss -H -lnt '( sport = :9092 or sport = :9093 )' | grep -q .; then
    echo 'Ports 9092/9093 already in use; inspect before deployment'; exit 1
  fi
fi
free_mib=$(df -Pm /var/lib/docker | awk 'NR==2 {print $4}')
(( free_mib >= 4096 )) || { echo 'Need at least 4 GiB free Docker disk space'; exit 1; }
docker compose -f "$directory/compose.yml" pull kafka
docker compose -f "$directory/compose.yml" up -d --wait --wait-timeout 180 kafka
docker exec -e 'KAFKA_HEAP_OPTS=-Xms32m -Xmx64m' rainn0coding-kafka \
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server 127.0.0.1:9092 \
  --create --if-not-exists --topic "$topic" --partitions 1 --replication-factor 1 \
  --config retention.ms=604800000 --config retention.bytes=268435456 \
  --config segment.bytes=16777216 --config segment.ms=3600000 --config min.insync.replicas=1
GENERATION_QUEUE_TOPIC="$topic" bash "$directory/verify.sh"
printf 'Kafka ready. Apply the queue SQL migration before enabling the Java queue.\n'
