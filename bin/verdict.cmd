@echo off
rem Windows launcher for verdict. Same behaviour as bin\verdict: it passes every argument and the exit code through.
where python >nul 2>nul
if errorlevel 1 goto usepy
python "%~dp0verdict" %*
exit /b %errorlevel%
:usepy
py -3 "%~dp0verdict" %*
exit /b %errorlevel%
