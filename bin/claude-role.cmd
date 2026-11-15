@echo off
rem Windows launcher for claude-role. Same behaviour as bin\claude-role: it passes every argument and the exit code through.
rem The first python on PATH that is not under WindowsApps runs it: the WindowsApps alias exits 9009 when no Store python is installed.
rem With none left, py -3 runs it.
set "CLAUDE_ROLE_PY="
for /f "usebackq delims=" %%P in (`where python 2^>nul ^| findstr /v /i WindowsApps`) do if not defined CLAUDE_ROLE_PY set "CLAUDE_ROLE_PY=%%P"
if defined CLAUDE_ROLE_PY goto usepython
py -3 "%~dp0claude-role" %*
exit /b %errorlevel%
:usepython
"%CLAUDE_ROLE_PY%" "%~dp0claude-role" %*
exit /b %errorlevel%
