@echo off
rem Windows launcher for claude-p. Same behaviour as bin\claude-p: it passes every argument and the exit code through.
where python >nul 2>nul
if errorlevel 1 goto usepy
python "%~dp0claude-p" %*
exit /b %errorlevel%
:usepy
py -3 "%~dp0claude-p" %*
exit /b %errorlevel%
