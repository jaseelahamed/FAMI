@echo off
title Pharmaceutical Label Validator
echo Starting Medicine Label Validation System...
set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"

if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

if "%~1"=="" (
    "%PYTHON_EXE%" app.py --demo
) else (
    "%PYTHON_EXE%" app.py %*
)

echo.
pause
