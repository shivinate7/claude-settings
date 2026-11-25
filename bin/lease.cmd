@echo off
rem Windows launcher for lease. Same behaviour as bin\lease: it passes every argument and the exit code through.
where python >nul 2>nul
if errorlevel 1 goto usepy
python "%~dp0lease" %*
exit /b %errorlevel%
:usepy
py -3 "%~dp0lease" %*
exit /b %errorlevel%
