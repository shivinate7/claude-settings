@echo off
rem Windows launcher for the merge tool. Same behaviour as bin\merge: it starts that shim and passes
rem every argument and the exit code through. Plan: plans/shared-merge-tool.md.
where python >nul 2>nul
if errorlevel 1 goto usepy
python "%~dp0merge" %*
exit /b %errorlevel%
:usepy
py -3 "%~dp0merge" %*
exit /b %errorlevel%
