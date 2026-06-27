#!/bin/bash
# AI Code Mother — 监控栈一键停止

echo "停止监控栈..."

# Python FastAPI
taskkill /FI "WINDOWTITLE eq AI-Python-Agent" /F 2>/dev/null && echo "  ✓ Python 已停止" || echo "  - Python 未运行"

# Prometheus
taskkill /FI "WINDOWTITLE eq Prometheus" /F 2>/dev/null && echo "  ✓ Prometheus 已停止" || echo "  - Prometheus 未运行"

# Grafana
taskkill /FI "WINDOWTITLE eq Grafana" /F 2>/dev/null && echo "  ✓ Grafana 已停止" || echo "  - Grafana 未运行"

echo "全部停止"
