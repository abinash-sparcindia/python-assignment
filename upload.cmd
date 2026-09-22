@echo off
setlocal
cd /d "%~dp0"
set "DATABASE_URL="
if not exist ".venv\Scripts\python.exe" (
  echo The project environment is not set up. Ask an engineer to install it, then try again.
  exit /b 1
)
if "%~1"=="" (
  echo Usage: upload path\to\survey.csv
  exit /b 1
)
".venv\Scripts\python.exe" -m utility_assets.cli %*
exit /b %ERRORLEVEL%
