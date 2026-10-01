@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

title Ghost Trail - Setup and Run

echo.
echo ================================================
echo             GHOST TRAIL SETUP
echo ================================================
echo.

REM ------------------------------------------------
REM 1. Check Python
REM ------------------------------------------------
where py >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set "PYTHON=python"
    ) else (
        echo [ERROR] Python 3 was not found.
        echo Install Python 3.10+ and make sure it is on PATH.
        pause
        exit /b 1
    )
)

echo [OK] Python found.

REM ------------------------------------------------
REM 2. Check Node / npm
REM ------------------------------------------------
where npm >nul 2>&1
if not %errorlevel%==0 (
    echo [ERROR] npm was not found.
    echo Install Node.js LTS and make sure npm is on PATH.
    pause
    exit /b 1
)

echo [OK] npm found.

REM ------------------------------------------------
REM 3. Install Python dependencies
REM ------------------------------------------------
echo.
echo [1/4] Installing Python dependencies...
%PYTHON% -m pip install -r requirements.txt
if not %errorlevel%==0 (
    echo.
    echo [ERROR] Python dependency installation failed.
    echo Check your internet connection and the error above.
    pause
    exit /b 1
)

echo [OK] Python dependencies installed.
REM Verify torchreid's Google Drive downloader dependency is present.
%PYTHON% -c "import gdown" >nul 2>&1
if not %errorlevel%==0 (
    echo [ERROR] gdown is missing. Re-run setup so the updated requirements are installed.
    pause
    exit /b 1
)
echo [OK] gdown available.

REM Verify torchreid's TensorBoard dependency is present.
%PYTHON% -c "import tensorboard" >nul 2>&1
if not %errorlevel%==0 (
    echo [ERROR] tensorboard is missing. Re-run setup so the updated requirements are installed.
    pause
    exit /b 1
)
echo [OK] tensorboard available.

REM ------------------------------------------------
REM 4. Install frontend dependencies
REM ------------------------------------------------
echo.
echo [2/4] Installing frontend dependencies...
cd dashboard
call npm install
if not %errorlevel%==0 (
    echo.
    echo [ERROR] npm dependency installation failed.
    echo If npm appears stuck, check your network or npm registry.
    echo You can try: npm cache clean --force
    cd ..
    pause
    exit /b 1
)

echo [OK] Frontend dependencies installed.

REM ------------------------------------------------
REM 5. Build React dashboard
REM ------------------------------------------------
echo.
echo [3/4] Building dashboard...
call npm run build
if not %errorlevel%==0 (
    echo.
    echo [ERROR] Dashboard build failed.
    cd ..
    pause
    exit /b 1
)

cd ..
echo [OK] Dashboard build complete.

REM ------------------------------------------------
REM 6. Start FastAPI
REM ------------------------------------------------
echo.
echo [4/4] Starting Ghost Trail...
echo.
echo Dashboard: http://127.0.0.1:8765
echo Press Ctrl+C in the server window to stop Ghost Trail.
echo.

start "Ghost Trail" cmd /k "%PYTHON% sentinel_app.py"

echo.
echo Ghost Trail is starting. The application will open the browser when
echo FastAPI and the AI pipeline are ready.
echo.

exit /b 0
