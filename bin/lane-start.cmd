@echo off
rem Windows launcher for lane-start. Same behaviour as bin\lane-start: it passes every argument and the exit code through.
rem The first python on PATH that is not under WindowsApps runs it: the WindowsApps alias exits 9009 when no Store python is installed.
rem With none left, py -3 runs it.
set "LANE_START_PY="
for /f "usebackq delims=" %%P in (`where python 2^>nul ^| findstr /v /i WindowsApps`) do if not defined LANE_START_PY set "LANE_START_PY=%%P"
if defined LANE_START_PY goto usepython
py -3 "%~dp0lane-start" %*
exit /b %errorlevel%
:usepython
"%LANE_START_PY%" "%~dp0lane-start" %*
exit /b %errorlevel%
