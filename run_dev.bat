@echo off
setlocal

:: Ensure we run from the project root directory
cd /d "%~dp0"

title GPF Smart Investor AI - Launcher
echo ===================================================
echo   GPF Smart Investor AI - Development Launcher
echo ===================================================
echo Project Directory: %~dp0
echo.

:: 1. Launch Backend Server
if exist "%~dp0.venv\Scripts\python.exe" (
    echo [Backend] Starting Backend API on port 8008 via .venv...
    start "GPF Backend Server (Port 8008)" /D "%~dp0" cmd /k "call .venv\Scripts\activate.bat && python run.py"
    goto :START_FRONTEND
)

if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    echo [Backend] Starting Backend API on port 8008 via local Python 3.14...
    start "GPF Backend Server (Port 8008)" /D "%~dp0" cmd /k ""%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" run.py"
    goto :START_FRONTEND
)

echo [Backend] Starting Backend API on port 8008 via system Python...
start "GPF Backend Server (Port 8008)" /D "%~dp0" cmd /k "python run.py"

:START_FRONTEND
:: 2. Launch Frontend Dev Server
echo [Frontend] Starting Next.js Dev Server on port 3008...
if exist "%~dp0frontend\package.json" (
    start "GPF Frontend Dev (Port 3008)" /D "%~dp0frontend" cmd /k "npm run dev"
) else (
    echo [Error] frontend\package.json not found!
)

:: 3. Wait and open browser
echo.
echo [Browser] Waiting for servers to initialize...
ping 127.0.0.1 -n 4 >nul
echo [Browser] Opening web browser at http://localhost:3008 ...
start http://localhost:3008

echo.
echo ===================================================
echo Services are running in separate terminal windows:
echo - Backend API : http://localhost:8008 (Docs: http://localhost:8008/docs)
echo - Frontend UI : http://localhost:3008
echo ===================================================
echo.
echo Press any key to close this launcher window (servers will continue running).
pause >nul
