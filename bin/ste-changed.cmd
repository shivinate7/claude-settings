@echo off
rem Windows launcher for ste-changed. Same behaviour as bin\ste-changed: it passes every argument and the exit code through.
where python >nul 2>nul
if errorlevel 1 goto usepy
python "%~dp0ste-changed" %*
exit /b %errorlevel%
:usepy
py -3 "%~dp0ste-changed" %*
exit /b %errorlevel%
