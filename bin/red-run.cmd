@echo off
rem Windows launcher for red-run. Same behaviour as bin\red-run: it passes every argument and the exit code through.
where python >nul 2>nul
if errorlevel 1 goto usepy
python "%~dp0red-run" %*
exit /b %errorlevel%
:usepy
py -3 "%~dp0red-run" %*
exit /b %errorlevel%
