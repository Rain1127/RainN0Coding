#!/bin/bash

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "Stopping monitoring stack..."
echo

docker compose -f "$ROOT_DIR/docker-compose.monitoring.yml" down

taskkill /FI "WINDOWTITLE eq AI-Python-Agent" /F >/dev/null 2>&1 && echo "  Python stopped" || echo "  Python was not running"
taskkill /FI "WINDOWTITLE eq Prometheus" /F >/dev/null 2>&1 && echo "  Prometheus stopped" || echo "  Prometheus was not running"

echo
echo "Monitoring stack stopped"
