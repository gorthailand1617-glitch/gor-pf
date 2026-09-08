@echo off
title GPF-SmartInvestor-AI Cloud Deployment
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy_gcp.ps1"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Execution encountered an issue.
    pause
)
