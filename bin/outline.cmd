@echo off
rem Windows launcher for outline. Same behaviour as bin\outline: it passes every argument and the exit code through.
where python >nul 2>nul
if errorlevel 1 goto usepy
python "%~dp0outline" %*
exit /b %errorlevel%
:usepy
py -3 "%~dp0outline" %*
exit /b %errorlevel%
