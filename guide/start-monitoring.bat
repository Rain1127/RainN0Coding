@echo off
chcp 65001 >nul
title AI Code Mother - 一键启动监控栈

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║     AI Code Mother — 监控栈一键启动                    ║
echo ╚══════════════════════════════════════════════════════╝
echo.

set ROOT=%~dp0
set PYTHON_DIR=%ROOT%python-agent
set PROMETHEUS_EXE=D:\Program Files\prometheus-3.5.1.windows-amd64\prometheus.exe
set GRAFANA_EXE=D:\Program Files\GrafanaLabs\grafana\bin\grafana-server.exe
set GRAFANA_HOME=D:\Program Files\GrafanaLabs\grafana

:: ==================== 1. Python FastAPI ====================
echo [1/3] 启动 Python FastAPI ...
tasklist /FI "WINDOWTITLE eq python*" 2>nul | find /I "python" >nul
if %errorlevel%==0 (
    echo   ⚠ Python 进程已在运行，跳过
) else (
    start "AI-Python-Agent" /MIN cmd /c "cd /d %PYTHON_DIR% && set PYTHONPATH=%PYTHON_DIR% && .venv\Scripts\python.exe server\main.py"
    echo   ✓ Python FastAPI 已启动 (端口 8000)
)

:: ==================== 2. Prometheus ====================
echo [2/3] 启动 Prometheus ...
curl -s http://localhost:9090/-/healthy >nul 2>&1
if %errorlevel%==0 (
    echo   ⚠ Prometheus 已在运行，跳过
) else (
    start "Prometheus" /MIN cmd /c ""%PROMETHEUS_EXE%" --config.file=%ROOT%prometheus.yml --web.listen-address=:9090"
    echo   ✓ Prometheus 已启动 (端口 9090)
)

:: ==================== 3. Grafana ====================
echo [3/3] 启动 Grafana ...
curl -s http://localhost:3000/api/health >nul 2>&1
if %errorlevel%==0 (
    echo   ⚠ Grafana 已在运行，跳过
) else (
    start "Grafana" /MIN cmd /c ""%GRAFANA_EXE%" --homepath "%GRAFANA_HOME%" --config "%GRAFANA_HOME%\conf\defaults.ini""
    echo   ✓ Grafana 已启动 (端口 3000)
)

:: ==================== 等待就绪 ====================
echo.
echo ⏳ 等待服务就绪...
set /a WAIT=0
:wait_loop
    timeout /t 2 /nobreak >nul
    set /a WAIT+=2
    curl -s http://localhost:8000/api/health >nul 2>&1 && set PY_OK=1 || set PY_OK=0
    curl -s http://localhost:9090/-/healthy   >nul 2>&1 && set PM_OK=1 || set PM_OK=0
    curl -s http://localhost:3000/api/health  >nul 2>&1 && set GF_OK=1 || set GF_OK=0
    if %WAIT% geq 30 goto :timeout
    if %PY_OK%==0 goto :wait_loop
    if %PM_OK%==0 goto :wait_loop
    if %GF_OK%==0 goto :wait_loop
    goto :ready

:timeout
echo   ⚠ 部分服务启动超时，请手动检查
goto :summary

:ready
echo   ✓ 全部服务就绪

:: ==================== 汇总 ====================
:summary
echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║  服务地址                                            ║
echo ╠══════════════════════════════════════════════════════╣
echo ║  Python Agent:  http://localhost:8000                ║
echo ║  Prometheus:   http://localhost:9090                ║
echo ║  Grafana:      http://localhost:3000                ║
echo ║                 admin / admin123                     ║
echo ╠══════════════════════════════════════════════════════╣
echo ║  Grafana 大盘:                                       ║
echo ║  • AI Workflow Monitoring (Python 工作流)            ║
echo ║  • AI模型监控看板 (Java LLM 指标)                     ║
echo ╚══════════════════════════════════════════════════════╝
echo.
echo 按任意键打开 Grafana ...
pause >nul
start http://localhost:3000
