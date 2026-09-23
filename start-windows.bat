@echo off
rem Windows: double-click this file.
rem First run installs everything into a .venv folder (5-10 min, needs internet).
cd /d "%~dp0"

".venv\Scripts\python.exe" -c "import pylandstats, rasterio, jupyterlab" 2>nul
if not errorlevel 1 goto run

echo == First-time setup: installing required software (5-10 minutes) ==
if exist .venv rmdir /s /q .venv
py -3.12 -m venv .venv 2>nul || py -3.13 -m venv .venv 2>nul || python -m venv .venv 2>nul
".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info[:2] not in [(3, 12), (3, 13)])" 2>nul
if errorlevel 1 (
  echo.
  echo ERROR: Python 3.12 was not found.
  echo Install it from https://www.python.org/downloads/ ^(see README.md, Step 1^), then try again.
  if exist .venv rmdir /s /q .venv
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip && ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo ERROR: installation failed. See "Troubleshooting" in README.md.
  pause
  exit /b 1
)

:run
echo == Opening the notebook in your web browser. Keep this window open while you work. ==
".venv\Scripts\python.exe" src\start.py
pause
