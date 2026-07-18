@echo off
REM Modpack Manager launcher -- double-click this file, or run it from a terminal.
REM On first run it creates a local virtual environment and installs dependencies.
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto run

echo First run: creating the virtual environment and installing dependencies...
echo (needs Python 3.10+ on your PATH)
python -m venv .venv
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q
".venv\Scripts\python.exe" -m pip install -e . -q

:run
echo.
echo Starting Modpack Manager -- your browser will open at http://127.0.0.1:5178
echo Press Ctrl+C in this window to stop.
echo.
".venv\Scripts\python.exe" -m modpack_manager

echo.
echo Modpack Manager has stopped.
pause
