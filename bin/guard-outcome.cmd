@echo off
rem Windows launcher for guard-outcome. Same behaviour as bin\guard-outcome: it passes every argument and the exit code through.
where python >nul 2>nul
if errorlevel 1 goto usepy
python "%~dp0guard-outcome" %*
exit /b %errorlevel%
:usepy
py -3 "%~dp0guard-outcome" %*
exit /b %errorlevel%
