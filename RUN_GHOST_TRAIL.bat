@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Ghost Trail - Hackathon Launcher

echo.
echo ================================================
echo              GHOST TRAIL
echo        ADVANCED HACKATHON BUILD
echo ================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python was not found in PATH.
  echo Install Python 3.10+ and reopen this file.
  pause
  exit /b 1
)
where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Node.js/npm was not found in PATH.
  echo Install Node.js LTS and reopen this file.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating Python virtual environment...
  python -m venv .venv
  if errorlevel 1 goto :error
)

call ".venv\Scripts\activate.bat"

echo [2/3] Installing/verifying Python dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [3/3] Building dashboard...
cd dashboard
if not exist node_modules call npm install
if errorlevel 1 goto :error_dashboard
call npm run build
if errorlevel 1 goto :error_dashboard
cd ..

echo.
echo Starting Ghost Trail...
echo Dashboard: http://127.0.0.1:8765
echo.
python sentinel_app.py
exit /b 0

:error_dashboard
cd ..
:error
echo.
echo [ERROR] Ghost Trail could not start. Read the error above.
pause
exit /b 1
