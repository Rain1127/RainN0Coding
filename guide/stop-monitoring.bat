@echo off
chcp 65001 >nul
title 停止监控栈

echo 停止 AI Code Mother 监控栈...
echo.

taskkill /FI "WINDOWTITLE eq AI-Python-Agent" /F 2>nul && echo   ✓ Python 已停止 || echo   - Python 未运行
taskkill /FI "WINDOWTITLE eq Prometheus" /F 2>nul     && echo   ✓ Prometheus 已停止 || echo   - Prometheus 未运行
taskkill /FI "WINDOWTITLE eq Grafana" /F 2>nul        && echo   ✓ Grafana 已停止 || echo   - Grafana 未运行

echo.
echo 全部停止完毕
pause
