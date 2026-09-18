#!/bin/bash
set -euo pipefail
# No topic, volume or database deletion. Do not stop before task reconciliation.
test "${QUEUE_DRAIN_VERIFIED:-}" = yes || {
  echo 'First stop submissions/claims, reconcile all active tasks, then set QUEUE_DRAIN_VERIFIED=yes.'
  exit 2
}
directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
docker compose -f "$directory/compose.yml" stop kafka
printf 'Kafka stopped; persistent volume and topics retained.\n'
