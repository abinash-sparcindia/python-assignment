@echo off
cd /d "%~dp0"
call "%~dp0upload.cmd" %*
exit /b %ERRORLEVEL%
