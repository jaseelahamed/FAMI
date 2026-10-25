@echo off
title Pharmaceutical Medicine Label Validator - Production Server (Waitress)
color 0A

echo ===============================================================================
echo   STARTING PHARMACEUTICAL LABEL SCANNER (PRODUCTION MODE - WAITRESS)
echo ===============================================================================
echo.

cd /d "%~dp0"

echo [1/2] Verifying Python environment...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH!
    pause
    exit /b 1
)

echo [2/2] Launching Multi-Threaded Production WSGI Server on http://0.0.0.0:5000 ...
echo Press Ctrl+C to stop the server.
echo.
python -m waitress --listen=0.0.0.0:5000 wsgi:app

pause
