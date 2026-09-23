@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Law Summary

echo =============================================
echo   Law Summary - Windows launcher
echo =============================================
echo.

set "PYTHON_CMD="
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3.12"

if not defined PYTHON_CMD (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo [ERROR] Python was not found.
    echo Install Python 3.12 and run this file again.
    echo Download: https://www.python.org/downloads/windows/
    goto failed
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating Python environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto failed
)

echo [2/3] Checking and installing packages...
".venv\Scripts\python.exe" -m pip install -r requirements-web.txt
if errorlevel 1 goto failed

echo.
echo [3/3] Starting the web app. Your browser should open shortly.
echo Close this window to stop the app.
echo.
".venv\Scripts\python.exe" start_web.py
if errorlevel 1 goto failed
goto done

:failed
echo.
echo Startup failed. Review the error message above.
echo Internet access is needed the first time packages are installed.
echo.
pause
exit /b 1

:done
endlocal
