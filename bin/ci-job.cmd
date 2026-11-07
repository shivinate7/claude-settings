@echo off
rem Windows launcher for ci-job. Same behaviour as bin\ci-job: it passes every argument and the exit code through.
where python >nul 2>nul
if errorlevel 1 goto usepy
python "%~dp0ci-job" %*
exit /b %errorlevel%
:usepy
py -3 "%~dp0ci-job" %*
exit /b %errorlevel%
