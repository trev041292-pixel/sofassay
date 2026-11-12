@echo off
setlocal
cd /d "%~dp0"
title SofaSay - setup

set "PYTHON="
for /f "delims=" %%P in ('py -3.12 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON=%%P"
if not defined PYTHON if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYTHON if exist "%ProgramFiles%\Python312\python.exe" set "PYTHON=%ProgramFiles%\Python312\python.exe"

if not defined PYTHON (
    echo.
    echo Python 3.12 was not found.
    where winget >nul 2>nul
    if errorlevel 1 goto :nopython
    choice /c YN /n /m "Install Python 3.12 automatically now? [Y/N] "
    if errorlevel 2 goto :nopython
    echo Installing Python 3.12...
    winget install --id Python.Python.3.12 -e --source winget --scope user --accept-package-agreements --accept-source-agreements
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    if defined PYTHON goto :python_ready
    echo.
    echo Python was installed, but this window cannot find it yet.
    echo Close this window, then run setup.bat again.
    pause
    exit /b 1
)

:python_ready
echo Using Python: "%PYTHON%"
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python environment...
    "%PYTHON%" -m venv .venv
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
echo Setup complete. Opening the control panel...
start "" ".venv\Scripts\pythonw.exe" control_panel.py
echo Press Start in the control panel, then switch to World of Warcraft.
timeout /t 3 >nul
exit /b 0

:fail
echo.
echo Setup failed. Read the error above.
pause
exit /b 1

:nopython
echo.
echo Python 3.12 is required.
echo Install it from https://www.python.org/downloads/
echo Make sure the "py launcher" option is enabled, then run setup.bat again.
start "" "https://www.python.org/downloads/"
pause
exit /b 1
