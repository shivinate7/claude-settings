# A PowerShell call operator in a script block may deny as a detached launch

- **What.** Lane fan-code-guard-2 reports that a PowerShell call operator (`&`) inside a script block denies as `detached-launch` on main. Unmeasured here: `detached_launch_hit` returns '' for `powershell -c "& { Start-Process foo }"`, `& { foo }` and `pwsh -Command "& {sleep 1}"` (read 11:40 CST Nov 12), so the deny may come from another path. Reproduce first. Harm if real: a harmless PowerShell command is refused and the session routes around the guard. Source: lane fan-code-guard-2, through triage 11:19 CST Nov 12.
- **Where.** `hooks/guard_kill.py`: `detached_launch_hit` (line 612), `bare_background_hit` (line 590); called from `hooks/guard.py` line 4457.
- **Decision.** none.
- **Retire.** Find the form that denies, make the guard read it as a call, not a job. A case for it in `hooks/test_guard.py`, red on the current code first, expects an allow.
