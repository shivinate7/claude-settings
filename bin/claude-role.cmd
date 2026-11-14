@echo off
rem Windows launcher for claude-role. Same behaviour as bin\claude-role: it passes every argument and the exit code through.
where python >nul 2>nul
if errorlevel 1 goto usepy
python "%~dp0claude-role" %*
exit /b %errorlevel%
:usepy
py -3 "%~dp0claude-role" %*
exit /b %errorlevel%
