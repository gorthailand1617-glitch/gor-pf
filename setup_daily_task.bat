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
powershell -NoProfile -ExecutionPolicy Bypass -Command "$action = New-ScheduledTaskAction -Execute '%PYTHON_PATH%' -Argument 'run_daily_job.py' -WorkingDirectory '%SCRIPT_DIR%'; $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 6:30PM; Register-ScheduledTask -TaskName 'GorPF_DailyMarketJob' -Action $action -Trigger $trigger -Force"

echo.
echo [*] Registering Saturday Weekly Alerts in Windows Task Scheduler...
echo [*] Trigger: Every Saturday at 10:00 (Weekly Portfolio Check)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$action = New-ScheduledTaskAction -Execute '%PYTHON_PATH%' -Argument 'run_daily_job.py --weekly' -WorkingDirectory '%SCRIPT_DIR%'; $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At 10:00AM; Register-ScheduledTask -TaskName 'GorPF_WeeklySaturdayJob' -Action $action -Trigger $trigger -Force"

echo.
echo [SUCCESS] Windows Tasks successfully configured!
echo   1. GorPF_DailyMarketJob: Weekdays 18:30
echo   2. GorPF_WeeklySaturdayJob: Saturday 10:00
echo ==========================================================
