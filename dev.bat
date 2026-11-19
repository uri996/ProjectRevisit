@echo off
setlocal
cd /d "%~dp0"
echo.
echo ProjectRevisit - development mode
echo ==================================
if not exist ".venv\Scripts\python.exe" (
  echo Please install Python 3.12 and dependencies using README.md first.
  echo.
  pause
  exit /b 1
)
echo Backend starts first, then Vite with hot reload.
echo The browser opens only after both HTTP checks succeed.
echo Keep this window open. Press Ctrl+C to stop both services.
echo.
".venv\Scripts\python.exe" scripts/launch_windows.py --dev %*
set "RAG_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%RAG_EXIT_CODE%"=="0" echo Startup exited with error code %RAG_EXIT_CODE%. See details above.
pause
exit /b %RAG_EXIT_CODE%
