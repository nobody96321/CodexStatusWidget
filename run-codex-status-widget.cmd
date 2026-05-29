@echo off
setlocal

set "APP_DIR=%~dp0"
set "APP_EXE=%APP_DIR%CodexStatusWidget.exe"
set "PYTHONPATH=%APP_DIR%src;%PYTHONPATH%"

if exist "%APP_EXE%" (
  start "" "%APP_EXE%" %*
  exit /b 0
)

where pyw >nul 2>nul
if %errorlevel%==0 (
  start "" pyw -3 -m codex_status_widget %*
  exit /b 0
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw -m codex_status_widget %*
  exit /b 0
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m codex_status_widget %*
  exit /b %errorlevel%
)

where python >nul 2>nul
if %errorlevel%==0 (
  python -m codex_status_widget %*
  exit /b %errorlevel%
)

echo CodexStatusWidget.exe was not found, and Python was not found either.
echo Install Python 3 with PySide6, or download the Windows release package.
pause
exit /b 1
