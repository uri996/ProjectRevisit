@echo off
setlocal
cd /d "%~dp0"
echo.
echo ProjectRevisit - local mode
echo ==================================
if not exist ".venv\Scripts\python.exe" (
  echo Please install Python 3.12 and dependencies using README.md first.
  echo.
  pause
  exit /b 1
)
echo Open: http://127.0.0.1:8501
echo Keep this window open. Press Ctrl+C to stop.
echo.
".venv\Scripts\python.exe" scripts/launch_windows.py
set "RAG_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%RAG_EXIT_CODE%"=="0" echo Startup exited with error code %RAG_EXIT_CODE%. See details above.
pause
exit /b %RAG_EXIT_CODE%
