@echo off
chcp 65001 >nul
setlocal
title Stop Monitoring Stack

set ROOT=%~dp0

echo Stopping monitoring stack...
echo.

docker compose -f "%ROOT%docker-compose.monitoring.yml" down

taskkill /FI "WINDOWTITLE eq AI-Python-Agent" /F >nul 2>&1 && echo   Python stopped || echo   Python was not running
taskkill /FI "WINDOWTITLE eq Prometheus" /F >nul 2>&1 && echo   Prometheus stopped || echo   Prometheus was not running

echo.
echo Monitoring stack stopped
pause
