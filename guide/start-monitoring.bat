@echo off
chcp 65001 >nul
setlocal
title AI Code Mother - Monitoring Stack

set ROOT=%~dp0
set REPO_ROOT=%ROOT%..
set PYTHON_DIR=%REPO_ROOT%\python-agent
set PROMETHEUS_EXE=D:\Program Files\prometheus-3.5.1.windows-amd64\prometheus.exe

echo.
echo ================================================
echo   AI Code Mother Monitoring Stack
echo ================================================
echo.

:: ==================== 1. Python FastAPI ====================
echo [1/3] Starting Python FastAPI ...
tasklist /FI "WINDOWTITLE eq AI-Python-Agent" 2>nul | find /I "python" >nul
if %errorlevel%==0 (
    echo   Python is already running, skipping
) else (
    start "AI-Python-Agent" /MIN cmd /c "cd /d %PYTHON_DIR% && set PYTHONPATH=%PYTHON_DIR% && .venv\Scripts\python.exe server\main.py"
    echo   Python FastAPI started on port 8000
)

:: ==================== 2. Prometheus ====================
echo [2/3] Starting Prometheus ...
curl -s http://localhost:9090/-/healthy >nul 2>&1
if %errorlevel%==0 (
    echo   Prometheus is already running, skipping
) else (
    start "Prometheus" /MIN cmd /c ""%PROMETHEUS_EXE%" --config.file=%REPO_ROOT%\prometheus.yml --web.listen-address=:9090"
    echo   Prometheus started on port 9090
)

:: ==================== 3. Docker monitoring stack ====================
echo [3/3] Starting Grafana / Tempo / OTel Collector ...
taskkill /FI "WINDOWTITLE eq Grafana" /F >nul 2>&1
docker compose -f "%REPO_ROOT%\docker-compose.monitoring.yml" up -d
if %errorlevel%==0 (
    echo   Docker monitoring stack started on ports 3000, 3200, 4318
) else (
    echo   Failed to start Docker monitoring stack
)

:: ==================== Wait for ready ====================
echo.
echo Waiting for services to become ready...
set /a WAIT=0
:wait_loop
    timeout /t 2 /nobreak >nul
    set /a WAIT+=2
    curl -s http://localhost:8000/api/health >nul 2>&1 && set PY_OK=1 || set PY_OK=0
    curl -s http://localhost:9090/-/healthy >nul 2>&1 && set PM_OK=1 || set PM_OK=0
    curl -s http://localhost:3000/api/health >nul 2>&1 && set GF_OK=1 || set GF_OK=0
    if %WAIT% geq 30 goto :timeout
    if %PY_OK%==0 goto :wait_loop
    if %PM_OK%==0 goto :wait_loop
    if %GF_OK%==0 goto :wait_loop
    goto :ready

:timeout
echo   Some services timed out, please check them manually
goto :summary

:ready
echo   All services are ready

:: ==================== Summary ====================
:summary
echo.
echo ================================================
echo   URLs
echo ================================================
echo   Python Agent:  http://localhost:8000
echo   Prometheus:    http://localhost:9090
echo   Grafana:       http://localhost:3000
echo   Tempo:         http://localhost:3200
echo   Collector OTLP: http://localhost:4318/v1/traces
echo.
echo   Grafana dashboards:
echo   - AI Workflow Monitoring
echo   - AI Model Monitoring
echo   - Tempo Trace Explore
echo.
echo Press any key to open Grafana ...
pause >nul
start http://localhost:3000
