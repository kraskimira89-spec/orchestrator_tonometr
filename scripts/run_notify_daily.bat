@echo off
cd /d "%~dp0.."

where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
  py -3 notify_daily.py
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
  python notify_daily.py
  exit /b %ERRORLEVEL%
)

echo ERROR: python not found in PATH. Set full path to python.exe in Task Scheduler.
exit /b 1
