@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please install Python 3.12 and dependencies using README.md first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run ui/app.py
pause

