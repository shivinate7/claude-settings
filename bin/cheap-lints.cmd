@echo off
rem Windows launcher for cheap-lints. Same behaviour as bin\cheap-lints: it passes every argument and the exit code through.
where python >nul 2>nul
if errorlevel 1 goto usepy
python "%~dp0cheap-lints" %*
exit /b %errorlevel%
:usepy
py -3 "%~dp0cheap-lints" %*
exit /b %errorlevel%
