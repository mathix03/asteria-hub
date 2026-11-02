@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute d'abord : py -3 -m venv .venv
  echo Puis : .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)
".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
