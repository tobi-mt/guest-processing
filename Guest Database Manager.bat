@echo off
setlocal enabledelayedexpansion

REM Guest Database Manager - Windows Launcher
REM This script launches the Guest Database Manager Streamlit application

title Guest Database Manager

echo ==========================================
echo    Guest Database Manager - Launcher
echo ==========================================
echo.

REM Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo [INFO] Starting Guest Database Manager...
echo [INFO] Project directory: %SCRIPT_DIR%
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo [ERROR] Please install Python 3.8 or later
    pause
    exit /b 1
)

REM Check if Hatch is available
hatch --version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Hatch is not installed. Installing Hatch...
    pip install hatch
    if errorlevel 1 (
        echo [ERROR] Failed to install Hatch
        pause
        exit /b 1
    )
)

REM Function to find an available port (starting from 8501)
set "AVAILABLE_PORT=8501"
set "MAX_PORT=8550"

:find_port
netstat -an | find ":%AVAILABLE_PORT% " >nul 2>&1
if not errorlevel 1 (
    set /a AVAILABLE_PORT+=1
    if !AVAILABLE_PORT! leq %MAX_PORT% goto find_port
    set "AVAILABLE_PORT=8501"
    echo [WARNING] All ports in range are busy. Using default port 8501.
) else (
    echo [INFO] Using port: !AVAILABLE_PORT!
)

REM Set up the Hatch environment if it doesn't exist
echo [INFO] Setting up Python environment...
if not exist ".hatch\envs\default" (
    echo [INFO] Creating Hatch environment for the first time...
    hatch env create
    if errorlevel 1 (
        echo [ERROR] Failed to create Hatch environment
        pause
        exit /b 1
    )
) else (
    echo [INFO] Hatch environment already exists
)

REM Install/update dependencies
echo [INFO] Ensuring dependencies are up to date...
hatch dep show requirements >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Updating dependencies...
    hatch env create --force
)

echo [INFO] Launching Guest Database Manager...
echo.
echo ==========================================
echo Application is starting...
echo The web interface will open automatically
echo Press Ctrl+C to stop the application
echo ==========================================
echo.

REM Launch the Streamlit app
hatch run streamlit run src/guest_database_manager/app.py --server.port=!AVAILABLE_PORT! --server.headless=false --browser.gatherUsageStats=false

REM If we get here, the app has stopped
echo.
echo [INFO] Guest Database Manager has stopped.
echo [INFO] Thank you for using Guest Database Manager!
echo.

REM Keep the command prompt open
pause
