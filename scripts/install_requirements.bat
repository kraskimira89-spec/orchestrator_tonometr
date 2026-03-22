@echo off
REM Extended pip timeout for slow PyPI; see requirements.txt comment.
cd /d "%~dp0.."

where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
  py -3 -m pip install -r requirements.txt --default-timeout 120 --retries 10
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
  python -m pip install -r requirements.txt --default-timeout 120 --retries 10
  exit /b %ERRORLEVEL%
)

echo ERROR: python not found in PATH.
exit /b 1
