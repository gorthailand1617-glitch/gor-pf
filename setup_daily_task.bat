@echo off
setlocal
echo ==========================================================
echo   GPF Smart Investor AI - Setup Windows Daily Task
echo ==========================================================
echo.

set SCRIPT_DIR=%~dp0
set PYTHON_PATH=%SCRIPT_DIR%.venv\Scripts\python.exe
set JOB_PATH=%SCRIPT_DIR%run_daily_job.py
set TASK_NAME=GorPF_DailyMarketJob

echo [*] Registering Daily Market Job in Windows Task Scheduler...
echo [*] Trigger: Monday - Friday at 18:30 (Market Close Daily Briefing)
echo.

schtasks /create /tn "%TASK_NAME%" /tr "\"%PYTHON_PATH%\" \"%JOB_PATH%\"" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 18:30 /f

if %ERRORLEVEL% equ 0 (
    echo.
    echo [SUCCESS] Task "%TASK_NAME%" successfully created!
    echo It will execute run_daily_job.py automatically every weekday at 18:30.
) else (
    echo.
    echo [WARNING] Failed to register scheduled task. Please run as Administrator if needed.
)

echo ==========================================================
