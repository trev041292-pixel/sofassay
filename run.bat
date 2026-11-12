@echo off
setlocal
cd /d "%~dp0"
title WoW Voice Chat

if not exist ".venv\Scripts\python.exe" (
    call setup.bat
    if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" main.py %*
echo.
echo WoW Voice Chat has stopped.
pause
