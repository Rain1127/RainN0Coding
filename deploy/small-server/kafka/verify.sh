#!/bin/bash
set -euo pipefail
topic=${GENERATION_QUEUE_TOPIC:-rain-code-generation-v1}
[[ "$topic" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]{0,248}$ ]] || exit 2
docker inspect --format '{{.State.Health.Status}}' rainn0coding-kafka | grep -qx healthy
for port in 9092 9093; do
  listeners=$(ss -H -lnt "sport = :$port" | awk '{print $4}')
  # JVM may report an IPv4-mapped IPv6 loopback socket; neither is a wildcard.
  case "$listeners" in
    "127.0.0.1:$port"|"[::ffff:127.0.0.1]:$port") ;;
    *) echo "Unexpected listener on $port: $listeners"; exit 1 ;;
  esac
done
docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/kafka/data"}}{{.Name}}{{end}}{{end}}' \
  rainn0coding-kafka | grep -qx rainn0coding_kafka_data
description=$(docker exec -e 'KAFKA_HEAP_OPTS=-Xms32m -Xmx64m' rainn0coding-kafka \
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server 127.0.0.1:9092 --describe --topic "$topic")
printf '%s\n' "$description"
grep -Eq 'PartitionCount: *1[[:space:]]+ReplicationFactor: *1' <<< "$description"
docker inspect --format 'OOMKilled={{.State.OOMKilled}} Restarts={{.RestartCount}} MemoryLimit={{.HostConfig.Memory}}' rainn0coding-kafka
docker inspect --format '{{.State.OOMKilled}}' rainn0coding-kafka | grep -qx false
docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' rainn0coding-kafka
free -m
df -h /var/lib/docker
