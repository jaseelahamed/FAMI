@echo off
title PharmaScan AI - Web Application
echo ====================================================================
echo Starting PharmaScan AI Web Server...
echo ====================================================================

set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

:: Open default browser after 2 seconds in background
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:5000"

:: Start Flask server
"%PYTHON_EXE%" server.py
pause
