@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Create a virtual environment first. See README.md.
  pause
  exit /b 1
)
.venv\Scripts\python.exe run.py
pause
