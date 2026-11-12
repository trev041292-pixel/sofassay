@echo off
setlocal
cd /d "%~dp0"
title WoW Voice Chat - setup

py -3.12 -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python 3.12 was not found.
    echo Install it from https://www.python.org/downloads/ and run this again.
    echo Make sure the "py launcher" option is enabled during installation.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python environment...
    py -3.12 -m venv .venv
    if errorlevel 1 goto :fail
)

echo Installing packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo Downloading the speech model (about 500 MB, first time only)...
".venv\Scripts\python.exe" -c "from faster_whisper import WhisperModel; WhisperModel('small.en', device='cpu', compute_type='int8'); print('Speech model ready.')"
if errorlevel 1 goto :fail

echo.
echo Creating a desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -File "make_shortcut.ps1"

echo.
echo Opening the setup window (game folder, microphone, talk button)...
".venv\Scripts\python.exe" main.py --setup
if errorlevel 1 goto :fail

echo.
echo Setup complete. Double-click the "WoW Voice Chat" shortcut on your desktop.
echo (Use run.bat if you prefer a console window.)
pause
exit /b 0

:fail
echo.
echo Setup failed. Read the error above.
pause
exit /b 1
